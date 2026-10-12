"""agent.chat turns as the client consumes them (turn_events.py, turn_transport.py,
queue_processor.py, slot_processor.py, connection_manager.on_script_execute)."""

import json
import uuid

import pytest

from lampway_server.agent.providers.base import Text, ToolCall

CUBE_SCRIPT = "import bpy\nbpy.ops.mesh.primitive_cube_add()\n"


def events_of(frames, turn_id):
    return [f["params"] for f in frames
            if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == turn_id]


def index_of(frames, predicate):
    return next(i for i, f in enumerate(frames) if predicate(f))


@pytest.fixture
def cube_script(provider):
    provider.script.append([Text("Adding a cube."),
                            ToolCall(id="call_1", name="run_blender_python",
                                     arguments={"script": CUBE_SCRIPT})])
    provider.script.append([Text("Done: the cube is in the scene.")])
    return provider


def start_chat(fake, ws, message, session_id=None):
    session_id = session_id or str(uuid.uuid4())
    command_id = fake.command(ws, "chat", fake.chat_payload(message, session_id))
    return session_id, command_id


def test_a_chat_turn_streams_in_the_order_the_client_requires(fake, cube_script):
    fake.login()
    executed = []

    def on_script(params):
        executed.append(params)
        return fake.execute_script_result(params["script"], output="", created=["Cube"])

    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id, command_id = start_chat(fake, ws, "Add a cube")
        frames = fake.run_turn(ws, command_id, on_script=on_script)

    # The admission receipt: not completion (turn_transport.py:96-110).
    receipt = next(f for f in frames if f.get("id") and "result" in f and f["result"].get("state"))
    assert receipt["result"]["state"] == "pending"

    # turn.started must carry turn_id == command_id and arrive BEFORE command.result
    # (turn_events.py:253 `expected = tid in _commands`; :233 pops on command.result).
    started = index_of(frames, lambda f: f.get("method") == "agent.turn.started")
    assert frames[started]["params"]["turn_id"] == command_id
    assert frames[started]["params"]["session_id"] == session_id
    assert frames[started]["params"]["run_id"]
    result_at = index_of(frames, lambda f: f.get("method") == "agent.command.result")
    assert started < result_at
    assert frames[result_at]["params"] == {**frames[result_at]["params"], "session_id": session_id,
                                           "command_id": command_id, "ok": True}

    # blender.execute_script came after turn.started (the client refuses scripts
    # outside an active turn: connection_manager.py:342-348) and carried the tool's script.
    script_at = index_of(frames, lambda f: f.get("method") == "blender.execute_script")
    assert started < script_at
    params = frames[script_at]["params"]
    assert params["script"] == CUBE_SCRIPT
    assert params["tool_name"] == "run_blender_python"
    assert params["session_id"] == session_id
    assert params["agent_ctx"]["chat_session_id"] == session_id
    assert params["agent_ctx"]["turn_id"] == command_id
    assert params["agent_ctx"]["call_id"] == "call_1"
    assert len(executed) == 1

    # seq restarts at 0 and is contiguous (turn_events.py:289-301).
    events = events_of(frames, command_id)
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(events)))
    assert all(e["session_id"] == session_id for e in events)
    payloads = [e["event"] for e in events]
    assert payloads[0]["type"] == "run_status" and payloads[0]["status"] == "in_progress"
    assert payloads[-1]["type"] == "turn_end" and payloads[-1]["status"] == "completed"
    assert payloads[-1]["run_id"] == frames[started]["params"]["run_id"]

    # The slot stream: every non-typed event has a bubble_id; the final answer landed as content.
    slots = [p for p in payloads if "bubble_id" in p]
    assert slots
    content = "".join((p.get("content") or {}).get("append", "") for p in slots)
    content_sets = [p["content"]["set"] for p in slots if "set" in (p.get("content") or {})]
    assert "Done: the cube is in the scene." in content or any(
        "Done: the cube is in the scene." in s for s in content_sets)
    # A loader was shown and then hidden (one spinner, always: slot_processor.py:312-317).
    loaders = [p["loader"]["visible"] for p in slots if "loader" in p]
    assert loaders and loaders[0] is True and loaders[-1] is False
    # The tool call is visible as a step row (steps_format.apply_steps_to_bubble).
    steps = [p["steps"] for p in slots if "steps" in p]
    assert any("run_blender_python" in json.dumps(s) for s in steps)

    # turn.ended carries the last seq (turn_events.py:279).
    ended = next(f for f in frames if f.get("method") == "agent.turn.ended")
    assert ended["params"] == {"session_id": session_id, "turn_id": command_id, "last_seq": seqs[-1]}

    # The provider saw the tool result on its second call.
    second = cube_script.requests[1]
    assert second.messages[-1].role == "user"
    tool_results = [part for part in second.messages[-1].content if part.get("type") == "tool_result"]
    assert tool_results and tool_results[0]["tool_call_id"] == "call_1"
    assert "Cube" in tool_results[0]["content"]


def test_a_failed_script_is_reported_to_the_model_not_swallowed(fake, provider):
    provider.script.append([ToolCall(id="c1", name="run_blender_python", arguments={"script": "boom("})])
    provider.script.append([Text("The script failed; I will not retry.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, command_id = start_chat(fake, ws, "run bad code")
        frames = fake.run_turn(ws, command_id, on_script=lambda p: fake.execute_script_result(
            p["script"], success=False, error="SyntaxError: unexpected EOF"))
    tool_results = [part for part in provider.requests[1].messages[-1].content if part.get("type") == "tool_result"]
    assert tool_results[0]["is_error"] is True
    assert "SyntaxError" in tool_results[0]["content"]
    assert events_of(frames, command_id)[-1]["event"]["status"] == "completed"


def test_mock_agent_failure_runs_client_response_logging_with_real_rpc_id(fake, provider, monkeypatch, caplog, request):
    """F20: drive an agent turn through the actual client response pump."""
    import importlib
    import logging
    from pathlib import Path
    import sys
    from types import ModuleType, SimpleNamespace

    scripts = Path(__file__).resolve().parents[2] / "src/scripts"
    # Load pure client transport modules without registering Blender UI.
    for name in ("mixar", "mixar.config", "mixar.modules", "mixar.modules.common",
                 "mixar.modules.common.agent_execution"):
        package = ModuleType(name)
        package.__path__ = [str(scripts / name.replace(".", "/"))]
        monkeypatch.setitem(sys.modules, name, package)
    logging_adapter = ModuleType("mixar.config.logging_config")
    logging_adapter.get_logger = logging.getLogger
    monkeypatch.setitem(sys.modules, logging_adapter.__name__, logging_adapter)
    dossier = ModuleType("mixar.modules.common.scenes_log")
    dossier.slog = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, dossier.__name__, dossier)
    names = ("mixar.modules.common.agent_execution.pump",
             "mixar.modules.common.agent_execution.request",
             "mixar.modules.common.agent_execution.diagnostics")
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    request.addfinalizer(lambda: [sys.modules.pop(name, None) for name in names])
    pump = importlib.import_module(names[0])
    Request = importlib.import_module(names[1]).ExecutionRequest
    caplog.set_level(logging.WARNING, logger=pump.logger.name)
    provider.script.extend([[ToolCall(id="f20_failure", name="run_blender_python",
                                     arguments={"script": "boom("})],
                            [Text("The executor refused the script.")]])
    fake.login()
    frames = []
    rpc_id = None
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, command_id = start_chat(fake, ws, "run the invalid fixture")
        def reply(request_id, result):
            ws.send_json({"jsonrpc": "2.0", "id": request_id, "result": result})
            return True
        client = SimpleNamespace(is_connected=True, queue_response=reply)
        for _ in range(500):
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("method") == "blender.execute_script":
                rpc_id = frame["id"]
                p = frame["params"]
                req = Request(rpc_id, p["script"], tool_name=p["tool_name"],
                              session_id=p["session_id"], agent_ctx=p["agent_ctx"])
                result = fake.execute_script_result(p["script"], success=False,
                                                    error="SyntaxError: unexpected EOF")
                assert pump.respond(client, req, result)
                assert not pump.respond(client, req, result), "replies/logs must not duplicate"
            if frame.get("method") == "agent.turn.ended":
                break
        else:
            pytest.fail("agent turn did not end")
    logs = [r.getMessage() for r in caplog.records if r.name == pump.logger.name]
    assert len(logs) == 1 and rpc_id in logs[0]
    assert "run_blender_python" in logs[0] and "SyntaxError: unexpected EOF" in logs[0]
    result = provider.requests[1].messages[-1].content[0]
    assert result["is_error"] is True and "SyntaxError" in result["content"]
    assert events_of(frames, command_id)[-1]["event"]["status"] == "completed"


def test_scene_summary_tool_runs_the_fixed_listing_script(fake, provider):
    provider.script.append([ToolCall(id="s1", name="scene_summary", arguments={})])
    provider.script.append([Text("The scene has one object.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, command_id = start_chat(fake, ws, "what is in the scene?")
        frames = fake.run_turn(ws, command_id, on_script=lambda p: fake.execute_script_result(
            p["script"], output='{"objects": [{"name": "Cube", "type": "MESH"}], "materials": []}'))
    script = next(f for f in frames if f.get("method") == "blender.execute_script")["params"]
    assert script["tool_name"] == "scene_summary"
    assert "bpy.context.scene.objects" in script["script"] and "_o.material_slots" in script["script"]
    assert "__RESULT__" in script["script"]  # executor.py:429-431 flattens the __RESULT__ variable
    tool_results = [part for part in provider.requests[1].messages[-1].content if part.get("type") == "tool_result"]
    assert "Cube" in tool_results[0]["content"]


def test_the_provider_receives_the_user_message_and_our_tool_definitions(fake, provider):
    provider.script.append([Text("Hello.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, command_id = start_chat(fake, ws, "hi there")
        fake.run_turn(ws, command_id, on_script=lambda p: {"success": True})
    request = provider.requests[0]
    assert request.messages[-1].role == "user" and "hi there" in request.messages[-1].text()
    assert {"run_blender_python", "scene_summary", "lampway_qa_candidates"} <= {t.name for t in request.tools}
    assert request.system


def test_attach_replays_events_after_the_cursor_and_status_describes_the_turn(fake, cube_script):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id, command_id = start_chat(fake, ws, "Add a cube")
        frames = fake.run_turn(ws, command_id, on_script=lambda p: {"success": True})
        events = events_of(frames, command_id)
        last_seq = events[-1]["seq"]

        rid = fake.request(ws, "agent.attach", {"session_id": session_id, "turn_id": command_id,
                                                "after_seq": 1})
        replayed, ended_again, reply = [], [], None
        while reply is None:
            frame = ws.receive_json()
            if frame.get("id") == rid:
                reply = frame
            elif frame.get("method") == "agent.turn.event":
                replayed.append(frame["params"])
            elif frame.get("method") == "agent.turn.ended":
                ended_again.append(frame["params"])
            else:
                raise AssertionError(f"unexpected frame during attach: {frame!r}")
        assert reply["result"].get("status") != "unavailable" and "code" not in reply["result"]
        assert [e["seq"] for e in replayed] == list(range(2, last_seq + 1))
        assert [e["event"] for e in replayed] == [e["event"] for e in events[2:]]
        # The ended marker is re-sent too, so a client that missed it settles (turn_events.py:276-281).
        assert ended_again == [{"session_id": session_id, "turn_id": command_id, "last_seq": last_seq}]

        rid = fake.request(ws, "agent.status", {"session_ids": [session_id]})
        status = ws.receive_json()
        info = status["result"]["turns"][session_id]
        assert info["turn_id"] == command_id and info["replay_available"] is True
        assert info["status"] == "ended" and info["active"] is False and info["last_seq"] == last_seq

        rid = fake.request(ws, "agent.request_status", {"command_id": command_id})
        state = ws.receive_json()
        assert state["id"] == rid
        assert state["result"] == {"state": "complete", "result": {**state["result"]["result"], "ok": True}}

        rid = fake.request(ws, "agent.attach", {"session_id": session_id, "turn_id": "never-existed",
                                                "after_seq": -1})
        reply = ws.receive_json()
        assert reply["id"] == rid and reply["result"]["status"] == "unavailable"


def test_status_for_an_unknown_session_is_an_empty_turns_map(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "agent.status", {"session_ids": ["nope"]})
        reply = ws.receive_json()
    assert reply["id"] == rid and reply["result"] == {"turns": {}}


def test_a_second_message_in_the_same_session_carries_the_history(fake, provider):
    provider.script.append([Text("First answer.")])
    provider.script.append([Text("Second answer.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id, c1 = start_chat(fake, ws, "first")
        fake.run_turn(ws, c1, on_script=lambda p: {"success": True})
        _, c2 = start_chat(fake, ws, "second", session_id=session_id)
        fake.run_turn(ws, c2, on_script=lambda p: {"success": True})
    history = [(m.role, m.text()) for m in provider.requests[1].messages]
    assert history == [("user", history[0][1]), ("assistant", "First answer."), ("user", history[2][1])]
    assert "first" in history[0][1] and "second" in history[2][1]


# Scribble marks (specs/mixar_docs/scribble_marks.md): the Client's agent.chat payload carries ``mark_context`` (scribble_mark/core/payload.build_payload,
# after serialize); the server restates it deterministically as prose beside the user's words: which object was circled, where on the ground a placement was
# pointed, or that a sketch was drawn and what it crosses. Shapes below are build_payload's own keys.
MARKS = {"v": 1, "surface": "view3d", "intent": "point", "intent_source": "auto", "views": {"mark_cam_1": {}}, "marks": [
    {"id": 1, "view": "mark_cam_1", "gesture": "circle", "closed": True, "stroke_count": 1, "region": {"bbox": [0.1, 0.1, 0.3, 0.3], "polygon": [], "anchor": None},
     "resolved": {"hit": True, "objects": [{"name": "alpha_cube", "partial": True, "object_fraction": 0.4}, {"name": "floor"}], "point": [1.0, 2.0, 0.5]}},
    {"id": 2, "view": "mark_cam_1", "gesture": "point", "closed": False, "stroke_count": 1, "region": {"bbox": [0.6, 0.6, 0.6, 0.6], "polygon": [], "anchor": [0.6, 0.6]},
     "resolved": {"hit": False, "plane": True, "point": [3.0, -1.0, 0.0]}}]}


def test_marks_are_described_as_object_names_and_world_points():
    from lampway_server.agent import marks_context as MC
    text = MC.describe(MARKS)
    assert "Mark 1: the user circled `alpha_cube`" in text and "about 40% of it" in text and "`floor`" in text and "(1, 2, 0.5)" in text, text
    assert "Mark 2: the user tapped an empty spot on the ground plane at world (3, -1, 0)" in text, text
    sketch = dict(MARKS, intent="sketch", sketch={"stroke_count": 3, "world_bbox": {"size": [2.0, 1.0, 0.0], "center": [0.5, 0.5, 0.0]}})
    sk = MC.describe(sketch)
    assert "DREW A SKETCH" in sk and "3 strokes" in sk and "2.0 m by 1.0 m" in sk and "crosses existing objects: `alpha_cube`, `floor`" in sk, sk
    assert MC.describe(None) == "" and MC.describe({"marks": []}) == "" and MC.describe("junk") == ""


def test_marks_are_in_the_model_context(fake, provider):
    provider.script.append([Text("Making it red.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        payload = fake.chat_payload("make this red", str(uuid.uuid4()))
        payload["mark_context"] = MARKS
        command_id = fake.command(ws, "chat", payload)
        fake.run_turn(ws, command_id, on_script=lambda p: {"success": True})
    text = provider.requests[0].messages[-1].text()
    assert "make this red" in text and "the user circled `alpha_cube`" in text, text
