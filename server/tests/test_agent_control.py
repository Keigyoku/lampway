"""agent.cancel and agent.input (session_ops.py, turn_transport.start_input_stream)."""

import uuid

from lampway_server.agent.providers.base import Text, ToolCall

from .test_agent_turn import events_of


def test_cancel_during_a_running_script_ends_the_turn_as_cancelled(fake, provider):
    provider.script.append([ToolCall(id="c1", name="run_blender_python", arguments={"script": "import time"})])
    provider.script.append([Text("never reached")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id = str(uuid.uuid4())
        command_id = fake.command(ws, "chat", fake.chat_payload("do something slow", session_id))
        # Wait for the script request, then cancel instead of answering it.
        frames = []
        while not frames or frames[-1].get("method") != "blender.execute_script":
            frames.append(ws.receive_json())
        script_request_id = frames[-1]["id"]
        fake.command(ws, "cancel", {"session_id": session_id})
        cancel_request_id = fake.last_request_id
        # The cancel reply and the turn's end race; wait for both.
        while not (any(f.get("method") == "agent.turn.ended" for f in frames)
                   and any(f.get("id") == cancel_request_id for f in frames)):
            frames.append(ws.receive_json())
        cancel_reply = next(f for f in frames if f.get("id") == cancel_request_id)
        assert "result" in cancel_reply
        payloads = [e["event"] for e in events_of(frames, command_id)]
        assert payloads[-1] == {"type": "turn_end", "status": "cancelled", "run_id": payloads[0]["run_id"]}
        # A late script reply must not break the socket.
        ws.send_json({"jsonrpc": "2.0", "id": script_request_id, "result": {"success": True}})
        rid = fake.request(ws, "agent.status", {"session_ids": [session_id]})
        status = ws.receive_json()
        assert status["id"] == rid
        assert status["result"]["turns"][session_id]["status"] == "ended"
    # The model was never called a second time.
    assert len(provider.requests) == 1


def test_input_runs_a_turn_with_the_answer_as_the_user_message(fake, provider):
    provider.script.append([Text("Which colour?")])
    provider.script.append([Text("Red it is.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id = str(uuid.uuid4())
        c1 = fake.command(ws, "chat", fake.chat_payload("paint the cube", session_id))
        fake.run_turn(ws, c1, on_script=lambda p: {"success": True})
        c2 = fake.command(ws, "input", {"session_id": session_id, "action": "respond", "text": "red",
                                        "rules": {}, "folder_context": {}})
        frames = fake.run_turn(ws, c2, on_script=lambda p: {"success": True})
    started = next(f for f in frames if f.get("method") == "agent.turn.started")
    assert started["params"]["turn_id"] == c2
    assert provider.requests[1].messages[-1].text() == "red"
    assert [m.role for m in provider.requests[1].messages] == ["user", "assistant", "user"]


def test_chat_without_a_session_id_is_invalid_params(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "agent.chat", {"command_id": "x", "payload": {"message": "hi"}})
        reply = ws.receive_json()
    assert reply["id"] == rid and reply["error"]["code"] == -32602
