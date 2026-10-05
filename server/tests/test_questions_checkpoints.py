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

import pytest

from lampway_server.agent.providers.base import Text, ToolCall

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
