"""agent.cancel and agent.input (session_ops.py, turn_transport.start_input_stream), on the unit's Hermes pane (the scripted serve,
docs/reports/agent-modes-spec.md A2, A5) with the Lampway client's own frames against the real server."""

import asyncio
import json
import uuid

import pytest

from .serve_support import chat, final_text, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)


def test_cancel_during_a_running_script_ends_the_turn_as_cancelled_and_stops_the_panes_turn(stack):
    async def scenario(serve, units, island, front):
        island.hold_scripts = True                                       # Blender is slow: the script call waits
        serve.scripts.append([("mcp", "run_blender_python", {"script": "import time"}), ("say", "never reached")])
        session_id = str(uuid.uuid4())
        command_id, _ = await chat(island, "do something slow", session_id)
        await island.wait(lambda f: f.get("method") == "blender.execute_script")
        _, rid = await island.command("agent.cancel", {"session_id": session_id})
        reply = await island.reply(rid)
        await island.ended(command_id)
        # A late script reply must not break the socket.
        await island.ws.send(json.dumps({"jsonrpc": "2.0", "id": island.held[0], "result": {"success": True}}))
        status = await island.reply(await island.send("agent.status", {"session_ids": [session_id]}))
        for _ in range(200):
            if not front.links[session_id].running:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        return session_id, reply, island.events(command_id), status, [m for m, _ in serve.calls], front.links[session_id].running, \
            json.dumps(serve.only().history)

    session_id, reply, payloads, status, methods, running, everything = run(stack, scenario)
    assert reply["result"]["result"]["ok"] is True
    assert payloads[-1] == {"type": "turn_end", "status": "cancelled", "run_id": payloads[0]["run_id"]}
    assert status["result"]["turns"][session_id]["status"] == "ended"
    assert "session.interrupt" in methods and running is False, "Hermes's turn was interrupted"
    assert "never reached" not in everything, "the rest of the pane's turn never ran: Hermes kept no reply"


def test_an_input_with_no_pending_question_is_a_plain_message_in_its_own_turn(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Which colour?")])
        serve.scripts.append([("say", "Red it is.")])
        session_id = str(uuid.uuid4())
        c1, _ = await chat(island, "paint the cube", session_id)
        await island.ended(c1)
        c2, _ = await island.command("agent.input", {"session_id": session_id, "action": "respond", "text": "red",
                                                     "rules": {}, "folder_context": {}})
        await island.ended(c2)
        return c2, island.started(), [(p["session_id"], p["text"]) for m, p in serve.calls if m == "prompt.submit"], island.events(c2)

    c2, started, prompts, events = run(stack, scenario)
    assert started[-1]["turn_id"] == c2
    assert len(prompts) == 2 and prompts[1][0] == prompts[0][0] and prompts[1][1].rstrip().endswith("red")
    assert final_text(events) == "Red it is."


def test_a_new_message_while_the_panes_question_waits_is_its_answer_and_a_late_answer_is_a_plain_message(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("clarify", "Round or square?", ["Round", "Square"]), ("say", "Forget the table, then.")])
        session_id = str(uuid.uuid4())
        cid, _ = await chat(island, "make a table", session_id)
        await island.ended(cid)
        question = next(e for e in island.events(cid) if e.get("interrupt_id"))
        moved_on, _ = await chat(island, "actually make a lamp", session_id)
        await island.ended(moved_on)
        serve.scripts.append([("say", "plain")])
        late, _ = await island.command("agent.input", {"session_id": session_id, "action": "respond", "text": "Round",
                                                       "interrupt_id": question["interrupt_id"]})
        await island.ended(late)
        return serve.only().answers, island.events(moved_on), [p["text"] for m, p in serve.calls if m == "prompt.submit"], \
            stack.app.state.agent.sessions[session_id].pending_question

    answers, moved_on, prompts, pending = run(stack, scenario)
    assert answers == [("clarify", {"answer": "actually make a lamp"})], "the new message answered the waiting question"
    assert final_text(moved_on) == "Forget the table, then."
    assert len(prompts) == 2 and prompts[-1].rstrip().endswith("Round"), "the old question is closed: answering it now is a new prompt"
    assert pending is None


def test_chat_without_a_session_id_is_invalid_params(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "agent.chat", {"command_id": "x", "payload": {"message": "hi"}})
        reply = ws.receive_json()
    assert reply["id"] == rid and reply["error"]["code"] == -32602
