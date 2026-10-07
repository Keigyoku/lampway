"""agent.chat turns as the client consumes them (turn_events.py, turn_transport.py, queue_processor.py, slot_processor.py,
connection_manager.on_script_execute). Mode 1 runs only on Hermes (docs/reports/agent-modes-spec.md A5): the turn is the unit's
Hermes pane's, played by the scripted serve (``serve_support.FakeServe``), and the island is the Lampway client's own frames against
the real server on a real port. A tool the pane calls reaches Blender through Lampway's MCP endpoint (A3)."""

import json
import uuid

import httpx
import pytest

from .serve_support import chat, final_text, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)
CUBE_SCRIPT = "import bpy\nbpy.ops.mesh.primitive_cube_add()\n"


def events_of(frames, turn_id):
    return [f["params"] for f in frames
            if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == turn_id]


def index_of(frames, predicate):
    return next(i for i, f in enumerate(frames) if predicate(f))


def created_cube(params):
    return {"success": True, "created_objects": ["Cube"]}


def test_a_chat_turn_streams_in_the_order_the_client_requires(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Adding a cube."), ("mcp", "run_blender_python", {"script": CUBE_SCRIPT}),
                              ("say", "Done: the cube is in the scene.")])
        session_id = str(uuid.uuid4())
        command_id, rid = await chat(island, "Add a cube", session_id)
        await island.ended(command_id)
        return session_id, command_id, rid, list(island.frames), island.scripts, serve.mcp_results

    session_id, command_id, rid, frames, executed, results = run(stack, scenario, on_script=created_cube)

    # The admission receipt: not completion (turn_transport.py:96-110).
    receipt = next(f for f in frames if f.get("id") == rid)
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

    # blender.execute_script came after turn.started (the client refuses scripts outside an active turn:
    # connection_manager.py:342-348), carried the tool's script, and names this turn: the pane's call ran in the island's turn.
    script_at = index_of(frames, lambda f: f.get("method") == "blender.execute_script")
    assert started < script_at
    params = frames[script_at]["params"]
    assert params["script"] == CUBE_SCRIPT
    assert params["tool_name"] == "run_blender_python"
    assert params["session_id"] == session_id
    assert params["agent_ctx"]["chat_session_id"] == session_id
    assert params["agent_ctx"]["turn_id"] == command_id
    assert params["agent_ctx"]["call_id"]
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
    assert "Done: the cube is in the scene." in final_text(slots)
    # A loader was shown and then hidden (one spinner, always: slot_processor.py:312-317).
    loaders = [p["loader"]["visible"] for p in slots if "loader" in p]
    assert loaders and loaders[0] is True and loaders[-1] is False
    # The tool call is visible as a step row (steps_format.apply_steps_to_bubble).
    steps = [p["steps"] for p in slots if "steps" in p]
    assert any("run_blender_python" in json.dumps(s) for s in steps)

    # turn.ended carries the last seq (turn_events.py:279).
    ended = next(f for f in frames if f.get("method") == "agent.turn.ended")
    assert ended["params"] == {"session_id": session_id, "turn_id": command_id, "last_seq": seqs[-1]}

    # The pane's Hermes got Blender's result back from the tool call.
    assert results[-1]["isError"] is False and "Cube" in results[-1]["content"][0]["text"]


def test_a_failed_script_is_reported_to_the_agent_not_swallowed(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("mcp", "run_blender_python", {"script": "boom("}), ("say", "The script failed; I will not retry.")])
        command_id, _ = await chat(island, "run bad code", str(uuid.uuid4()))
        await island.ended(command_id)
        return island.events(command_id), serve.mcp_results

    events, results = run(stack, scenario, on_script=lambda p: {"success": False, "error": "SyntaxError: unexpected EOF"})
    assert results[-1]["isError"] is True and "SyntaxError" in results[-1]["content"][0]["text"]
    assert events[-1]["status"] == "completed"


def test_scene_summary_tool_runs_the_fixed_listing_script(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("mcp", "scene_summary", {}), ("say", "The scene has one object.")])
        command_id, _ = await chat(island, "what is in the scene?", str(uuid.uuid4()))
        await island.ended(command_id)
        return island.scripts, serve.mcp_results

    scripts, results = run(stack, scenario, on_script=lambda p: {
        "success": True, "output": '{"objects": [{"name": "Cube", "type": "MESH"}], "materials": []}'})
    script = scripts[-1]
    assert script["tool_name"] == "scene_summary"
    assert "bpy.data.objects" in script["script"] and "bpy.data.materials" in script["script"]
    assert "__RESULT__" in script["script"]  # executor.py:429-431 flattens the __RESULT__ variable
    assert "Cube" in results[-1]["content"][0]["text"]


def test_the_pane_receives_the_users_message_and_lampways_tool_definitions(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hello.")])
        command_id, _ = await chat(island, "hi there", str(uuid.uuid4()))
        await island.ended(command_id)
        url, bearer = serve.mcp
        async with httpx.AsyncClient() as http:
            listed = (await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                      headers={"Authorization": f"Bearer {bearer}"})).json()
        return [p["text"] for m, p in serve.calls if m == "prompt.submit"], {t["name"] for t in listed["result"]["tools"]}

    prompts, tools = run(stack, scenario)
    assert len(prompts) == 1 and prompts[0].rstrip().endswith("hi there")
    assert {"run_blender_python", "scene_summary", "lampway_qa_candidates"} <= tools


def test_attach_replays_events_after_the_cursor_and_status_describes_the_turn(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Adding a cube."), ("mcp", "run_blender_python", {"script": CUBE_SCRIPT}), ("say", "Done.")])
        session_id = str(uuid.uuid4())
        command_id, _ = await chat(island, "Add a cube", session_id)
        await island.ended(command_id)
        events = [f["params"] for f in island.frames if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == command_id]
        mark = len(island.frames)
        rid = await island.send("agent.attach", {"session_id": session_id, "turn_id": command_id, "after_seq": 1})
        reply = await island.reply(rid)
        during = island.frames[mark:island.frames.index(reply)]
        status = await island.reply(await island.send("agent.status", {"session_ids": [session_id]}))
        state = await island.reply(await island.send("agent.request_status", {"command_id": command_id}))
        unknown = await island.reply(await island.send("agent.attach", {"session_id": session_id, "turn_id": "never-existed",
                                                                        "after_seq": -1}))
        return session_id, command_id, events, during, reply, status, state, unknown

    session_id, command_id, events, during, reply, status, state, unknown = run(stack, scenario)
    last_seq = events[-1]["seq"]
    replayed = [f["params"] for f in during if f.get("method") == "agent.turn.event"]
    ended_again = [f["params"] for f in during if f.get("method") == "agent.turn.ended"]
    assert not [f for f in during if f.get("method") not in ("agent.turn.event", "agent.turn.ended")], during
    assert reply["result"].get("status") != "unavailable" and "code" not in reply["result"]
    assert [e["seq"] for e in replayed] == list(range(2, last_seq + 1))
    assert [e["event"] for e in replayed] == [e["event"] for e in events[2:]]
    # The ended marker is re-sent too, so a client that missed it settles (turn_events.py:276-281).
    assert ended_again == [{"session_id": session_id, "turn_id": command_id, "last_seq": last_seq}]

    info = status["result"]["turns"][session_id]
    assert info["turn_id"] == command_id and info["replay_available"] is True
    assert info["status"] == "ended" and info["active"] is False and info["last_seq"] == last_seq

    assert state["result"] == {"state": "complete", "result": {**state["result"]["result"], "ok": True}}
    assert unknown["result"]["status"] == "unavailable"


def test_status_for_an_unknown_session_is_an_empty_turns_map(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "agent.status", {"session_ids": ["nope"]})
        reply = ws.receive_json()
    assert reply["id"] == rid and reply["result"] == {"turns": {}, "conversations": {}}


def test_a_second_message_in_the_same_tab_goes_to_the_same_hermes_session(stack):
    """The conversation is Hermes's (A0): the tab's second message is a second prompt in the same session of the same pane."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "First answer.")])
        serve.scripts.append([("say", "Second answer.")])
        session_id = str(uuid.uuid4())
        c1, _ = await chat(island, "first", session_id)
        await island.ended(c1)
        c2, _ = await chat(island, "second", session_id)
        await island.ended(c2)
        return units.opened, [(p["session_id"], p["text"]) for m, p in serve.calls if m == "prompt.submit"], serve.only().history, \
            final_text(island.events(c2))

    opened, prompts, history, second = run(stack, scenario)
    assert len(opened) == 1, "one pane for the tab"
    assert len(prompts) == 2 and prompts[0][0] == prompts[1][0], "both prompts went to the same Hermes session"
    assert [(m["role"], m["text"].rstrip().split("\n")[-1]) for m in history] == [
        ("user", "first"), ("assistant", "First answer."), ("user", "second"), ("assistant", "Second answer.")]
    assert second == "Second answer."


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


def test_marks_reach_the_pane_with_the_users_words(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Making it red.")])
        command_id, _ = await chat(island, "make this red", str(uuid.uuid4()), mark_context=MARKS)
        await island.ended(command_id)
        return next(p["text"] for m, p in serve.calls if m == "prompt.submit")

    text = run(stack, scenario)
    assert "make this red" in text and "the user circled `alpha_cube`" in text, text
