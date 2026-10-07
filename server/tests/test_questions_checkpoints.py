"""Two documented agent features the server did not have (docs: "Questions and planning", "Go back with checkpoints").

Questions: the model calls ``ask_user(question, options)``; the turn ends with a bubble that carries the question, the
choices as ``actions``, ``input_type: "choice"`` and an ``interrupt_id``; the client answers with ``agent.input``
{action: respond, text, answers, interrupt_id} (composer_send.py / turn_transport.start_input_stream), and the model
continues with the answer as the tool's result. Plan Mode is the client's ``plan_required`` flag on agent.chat: the
system prompt then tells the model to lay the plan out and ask before touching the scene.

Checkpoints: ``agent.checkpoint.mark {session_id, request_id}`` bookmarks the conversation, ``agent.checkpoint.rewind
{session_id, request_id}`` forgets everything after the bookmark; the reply is {ok, has_conversation}, and
``has_conversation: false`` tells the client to start a new session (checkpoint_backend.py:55-85, turn_checkpoints.py).
"""

import json

import pytest

from lampway_server.agent.providers.base import Text, ToolCall

from .test_swarm_v3 import played  # noqa: F401  (Lampway's herdr, played, with Mode 1's adapter played)

pytestmark = pytest.mark.anyio


def _reply(ws, request_id):
    for _ in range(50):
        frame = ws.receive_json()
        if frame.get("id") == request_id:
            return frame["result"]
    raise AssertionError(f"no reply to {request_id}")


def _slots(frames):
    return [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event" and "bubble_id" in f["params"]["event"]]


def test_ask_user_ends_the_turn_with_a_choice_and_the_answer_resumes_the_model(fake, provider):
    provider.script = [
        [Text("One question first."), ToolCall(id="q1", name="ask_user", arguments={
            "question": "Round or square table?", "options": ["Round", "Square"]})],
        [Text("Round it is.")],
    ]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("make a table", "s1"))
        frames = fake.run_turn(ws, cmd, on_script=lambda p: fake.execute_script_result(p["script"]))
        question = [s for s in _slots(frames) if s.get("input_type")]
        assert question, _slots(frames)
        q = question[-1]
        assert q["input_type"] == "choice" and q["interrupt_id"]
        assert [a["value"] for a in q["actions"]] == ["Round", "Square"]
        assert "Round or square table?" in q["content"]["set"]
        answer = fake.command(ws, "input", {"session_id": "s1", "action": "respond", "text": "Round", "answers": ["Round"],
                                             "interrupt_id": q["interrupt_id"]})
        frames = fake.run_turn(ws, answer, on_script=lambda p: fake.execute_script_result(p["script"]))
    final = [s for s in _slots(frames) if s.get("content", {}).get("set")]
    assert final and final[-1]["content"]["set"] == "Round it is."
    last = provider.requests[-1].messages
    assert last[-1].content[0]["type"] == "tool_result" and last[-1].content[0]["tool_call_id"] == "q1"
    assert last[-1].content[0]["content"] == "Round"
    assert any(t.name == "ask_user" for t in provider.requests[0].tools)


def test_an_input_with_no_pending_question_is_a_plain_message(fake, provider):
    provider.script = [[Text("hello")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "input", {"session_id": "s2", "action": "respond", "text": "hi"})
        fake.run_turn(ws, cmd, on_script=lambda p: {})
    assert provider.requests[-1].messages[-1].text() == "hi"


def test_plan_mode_is_the_clients_plan_required_flag(fake, provider):
    provider.script = [[Text("plan")], [Text("go")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        payload = fake.chat_payload("build a chair", "s3")
        cmd = fake.command(ws, "chat", payload)                       # plan_required: True in the fake client
        fake.run_turn(ws, cmd, on_script=lambda p: {})
        payload["plan_required"] = False
        cmd = fake.command(ws, "chat", payload)
        fake.run_turn(ws, cmd, on_script=lambda p: {})
    assert "Plan Mode" in provider.requests[0].system and "ask_user" in provider.requests[0].system
    assert "Plan Mode" not in provider.requests[1].system


def test_checkpoint_mark_then_rewind_forgets_the_turns_after_it(fake, provider):
    provider.script = [[Text("one")], [Text("two")], [Text("three")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("first", "s4"))
        fake.run_turn(ws, cmd, on_script=lambda p: {})
        marked = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                         {"command_id": "c1", "payload": {"session_id": "s4", "request_id": "r1"}}))
        assert marked == {"ok": True, "has_conversation": True}
        cmd = fake.command(ws, "chat", fake.chat_payload("second", "s4"))
        fake.run_turn(ws, cmd, on_script=lambda p: {})
        rewound = _reply(ws, fake.request(ws, "agent.checkpoint.rewind",
                                          {"command_id": "c2", "payload": {"session_id": "s4", "request_id": "r1"}}))
        assert rewound == {"ok": True, "has_conversation": True}
        cmd = fake.command(ws, "chat", fake.chat_payload("third", "s4"))
        fake.run_turn(ws, cmd, on_script=lambda p: {})
        unknown = _reply(ws, fake.request(ws, "agent.checkpoint.rewind",
                                          {"command_id": "c3", "payload": {"session_id": "s4", "request_id": "nope"}}))
        assert unknown == {"ok": True, "has_conversation": False}
    texts = [m.text() for m in provider.requests[-1].messages if m.role == "user"]
    assert texts == ["first", "third"], "the second turn was forgotten by the rewind"


def test_a_mark_on_an_unknown_session_has_no_conversation(fake, provider):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        reply = _reply(ws, fake.request(ws, "agent.checkpoint.mark",
                                        {"command_id": "c9", "payload": {"session_id": "never", "request_id": "r"}}))
    assert reply == {"ok": True, "has_conversation": False}


# O17 (specs/mixar_docs/agent_plan_questions.md): batched questions, the real client's answer shapes, Retry failed tasks, Plan Mode.
BATCH = [{"question": "Table shape?", "options": ["Round", "Square"]},
         {"question": "Material?", "options": ["Oak", "Steel", "Glass"]},
         {"question": "Seats?", "options": ["4", "6"]}]


def _ask_batch(fake, ws, session_id, questions=BATCH):
    cmd = fake.command(ws, "chat", fake.chat_payload("make a table", session_id))
    frames = fake.run_turn(ws, cmd, on_script=lambda p: fake.execute_script_result(p["script"]))
    return frames, [s for s in _slots(frames) if s.get("input_type")]


def test_batch_question_is_one_input_required_event(fake, provider):
    provider.script = [[Text("Three things first."), ToolCall(id="qb", name="ask_user", arguments={"questions": BATCH})]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        frames, asked = _ask_batch(fake, ws, "b1")
    assert len(asked) == 1, asked
    q = asked[0]
    # the client's batched_choice.store_batch keeps the wizard only for its own is_valid_batch shape; the first card is drawn from content + actions
    assert q["questions"] == BATCH and q["input_type"] == "choice" and q["interrupt_id"], q
    assert "Table shape?" in q["content"]["set"] and [a["value"] for a in q["actions"]] == ["Round", "Square", "abort"], q


def test_batch_answers_resume_once(fake, provider):
    provider.script = [[ToolCall(id="qb", name="ask_user", arguments={"questions": BATCH})], [Text("A round oak table for six.")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, asked = _ask_batch(fake, ws, "b2")
        iid = asked[0]["interrupt_id"]
        fake.command(ws, "input", {"session_id": "b2", "action": "submit", "text": "", "answers": {"Table shape?": "Round"},
                                              "interrupt_id": iid})
        refused = _reply(ws, fake.last_request_id)
        assert refused.get("state") == "complete" and refused["result"]["ok"] is False and "Material?" in refused["result"]["message"], refused
        assert len(provider.requests) == 1, "a partial answer map must not resume the model"
        full = {"Table shape?": "Round", "Material?": "Oak", "Seats?": "6"}       # chat_special_ops: action 'submit', the complete map, the interrupt id
        cmd = fake.command(ws, "input", {"session_id": "b2", "action": "submit", "text": "", "answers": full, "interrupt_id": iid})
        fake.run_turn(ws, cmd, on_script=lambda p: fake.execute_script_result(p["script"]))
    assert len(provider.requests) == 2, "all answers return together: one model resume"
    result = provider.requests[-1].messages[-1].content[0]
    assert result["type"] == "tool_result" and result["tool_call_id"] == "qb" and json.loads(result["content"]) == full, result


def test_a_batch_outside_two_to_four_or_without_options_is_refused_to_the_model(fake, provider):
    provider.script = [[ToolCall(id="q5", name="ask_user", arguments={"questions": BATCH + BATCH[:2]})],
                       [ToolCall(id="q0", name="ask_user", arguments={"questions": [{"question": "Colour?"}, {"question": "Size?", "options": ["S"]}]})],
                       [Text("ok")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        frames, asked = _ask_batch(fake, ws, "b3")
    assert asked == [], "a refused batch is not shown"
    results = [m.content[0] for r in provider.requests[1:] for m in r.messages[-1:] if m.content and m.content[0].get("type") == "tool_result"]
    assert results[0]["is_error"] and "a batch is 2 to 4 questions: ask one at a time otherwise" in results[0]["content"], results
    assert results[1]["is_error"] and "options" in results[1]["content"], results


def test_a_choice_click_from_the_client_answers_with_the_clicked_value(fake, provider):
    """The real client's click on a choice card sends agent.input {action: <the option's value>, text: ''} (chat_special_ops generic dispatch), not text."""
    provider.script = [[ToolCall(id="q1", name="ask_user", arguments={"question": "Round or square?", "options": ["Round", "Square"]})], [Text("ok")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("make a table", "c1"))
        fake.run_turn(ws, cmd, on_script=lambda p: {})
        cmd = fake.command(ws, "input", {"session_id": "c1", "action": "Square", "text": ""})
        fake.run_turn(ws, cmd, on_script=lambda p: {})
    assert provider.requests[-1].messages[-1].content[0]["content"] == "Square"


def test_cancel_on_a_batch_ends_the_turn_without_calling_the_model(fake, provider):
    provider.script = [[ToolCall(id="qb", name="ask_user", arguments={"questions": BATCH})], [Text("never")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _ask_batch(fake, ws, "b4")
        cmd = fake.command(ws, "input", {"session_id": "b4", "action": "abort", "text": ""})
        frames = fake.run_turn(ws, cmd, on_script=lambda p: {})
    assert len(provider.requests) == 1, "Cancel must not call the model again"
    assert any("cancel" in (s.get("content", {}).get("set") or "").lower() for s in _slots(frames)), _slots(frames)


def test_plan_mode_changes_nothing_before_approval(fake, provider):
    provider.script = [[Text("Plan: 1. add a cube."), ToolCall(id="qp", name="ask_user", arguments={"question": "Approve this plan?", "options": ["Approve", "Revise"]}),
                        ToolCall(id="eager", name="run_blender_python", arguments={"script": "import bpy\nbpy.ops.mesh.primitive_cube_add()\n"})],
                       [Text("unreached")]]
    fake.login()
    ran = []
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("add a cube", "p1"))          # plan_required: True
        frames = fake.run_turn(ws, cmd, on_script=lambda p: ran.append(p) or fake.execute_script_result(p["script"]))
    assert ran == [] and not [f for f in frames if f.get("method") == "blender.execute_script"], "nothing runs in the scene before the plan is approved"
    assert "Plan Mode" in provider.requests[0].system


def test_retry_failed_tasks_reruns_only_failed(settings, played):
    """The swarm's workers think in panes (spec S1, A5); Mode 1's adapter is played here until it is built (test_swarm_v3)."""
    from starlette.testclient import TestClient

    from lampway_server.agent.providers.mock import ScriptedProvider
    from lampway_server.app import create_app

    from .fake_client import FakeMixarClient
    from .fake_harness import FakeFleet, new_session
    from .test_swarm_v3 import PanePlayer, marker_play, tasks

    cockpit, herdr = played

    def play(swarm_id, worker_id):
        if swarm_id == "sw1" and worker_id == "worker-2":
            return [("exit",)]                                         # the harness quits: worker-2 of the first swarm fails
        return marker_play(swarm_id, worker_id)
    main = ScriptedProvider([[ToolCall(id="s1", name="swarm_start", arguments={"tasks": tasks("a", "b", "c")})],
                             [ToolCall(id="s2", name="swarm_collect", arguments={"swarm_id": "sw1"})],
                             [Text("Two of three finished.")],
                             [Text("The retried task finished.")]])
    app = create_app(settings, provider=main, cockpit=cockpit)
    from lampway_server import capabilities as CAP
    CAP.ACTIVE.set("swarm", enabled=True, by="user")             # the swarm is off until the user switches it on (spec E2, Q8)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        with PanePlayer(http, cockpit, herdr, play), fake.connect_ws() as ws:
            fake.handshake(ws)
            session_id = new_session()
            cmd = fake.command(ws, "chat", fake.chat_payload("QA three pieces", session_id))
            frames = fleet.drive(ws, cmd)
            chips = [e for e in (f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event")
                     if any(a.get("value") == "retry_failed_tasks" for a in e.get("actions") or [])]
            assert chips and "input_type" not in chips[-1], "the post-turn Retry failed tasks chip (turn_actions: buttons, no paused input)"
            spawned_before = sum(1 for m, p in fleet.requests if m == "agent.sandbox_control" and p.get("action") == "spawn")
            fleet.frames = []
            cmd = fake.command(ws, "chat", fake.chat_payload("continue", session_id))   # parked_resume.CONTINUE_MESSAGE
            frames = fleet.drive(ws, cmd)
        fleet.close()
    spawns = [p for m, p in fleet.requests if m == "agent.sandbox_control" and p.get("action") == "spawn"]
    assert spawned_before == 3 and len(spawns) - spawned_before == 1, "Retry spawns exactly the one failed task"
    todos = [e["todo"] for e in (f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event") if "todo" in e]
    assert todos and [r["text"].split(":")[0] for r in todos[-1]] == ["b"] and todos[-1][0]["status"] == "DONE", todos[-1]
    assert main.requests[-1].messages[-1].content[0]["type"] == "tool_result", "the model is told what the retry did"
