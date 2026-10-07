# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island is a second client of the unit's ``hermes serve`` (docs/reports/agent-modes-spec.md A2, A3), against a scripted serve
(``serve_support.FakeServe``, the contract measured on the pinned build) and the REAL server on a real port, driven by the Lampway
client's own frames. No engine, no model, no herdr: the unit's pane is played by ``FakeUnits``. What the ACP runtime's tests pinned
is kept here: a tool turn, a question, steer, a permission, R3's image, a disconnect the turn survives. The real pinned serve is
``test_engine_pane_live.py``."""

import asyncio
import json

import pytest
import websockets

from lampway_server.engine.front import ANSWERED_ELSEWHERE
from lampway_server.herdr import launcher as L

from .serve_support import Island, chat, final_text, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class Tui:
    """Another client of the same serve (Hermes's own TUI in the pane), speaking serve's frames."""

    def __init__(self, serve):
        self.serve = serve
        self.requests = []

    async def attach(self, stored):
        self.ws = await websockets.connect(f"ws://127.0.0.1:{self.serve.port}/api/ws?token={self.serve.token}")
        await self.ws.recv()                                                     # gateway.ready
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "client.capabilities", "params": {"server_requests": True}}))
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "session.resume", "params": {"session_id": stored}}))
        self.reader = asyncio.ensure_future(self._read())
        return self

    async def _read(self):
        async for raw in self.ws:
            frame = json.loads(raw)
            if frame.get("method") in ("clarify", "approval"):
                self.requests.append(frame)

    async def answer(self, result):
        while not self.requests:
            await asyncio.sleep(0.05)
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.requests[-1]["id"], "result": result}))

    async def close(self):
        await self.ws.close()
        await asyncio.gather(self.reader, return_exceptions=True)


# ---------------------------------------------------------------------------------------------------- a turn
def test_the_first_chat_opens_the_units_pane_and_a_tool_turn_runs_lampways_tool(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("mcp", "scene_summary", {}), ("say", "There is one cube.")])
        cid, _ = await chat(island, "What is in my scene?", "scene-1")
        await island.ended(cid)
        return island.events(cid)

    async def check():
        pass
    events = run(stack, scenario)
    assert final_text(events) == "There is one cube."
    assert events[0]["type"] == "run_status" and events[-1] == {"type": "turn_end", "status": "completed", "run_id": events[0]["run_id"]}
    steps = [e for e in events if e.get("steps")][-1]["steps"]["items"]
    assert [(s["label"], s["status"]) for s in steps] == [("scene_summary", "done")], "the step's label is the Lampway tool's name"
    assert [e["ephemeral"]["append"] for e in events if "append" in (e.get("ephemeral") or {})] == ["There", " is", " one", " cube."]


def test_the_island_attaches_as_a_client_that_takes_questions_and_submits_the_users_text(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello there", "scene-1")
        await island.ended(cid)
        return serve, units

    serve, units = run(stack, scenario)
    methods = [m for m, _ in serve.calls]
    assert units.opened == ["scene-1"], "the user's first chat opened the unit's pane, once"
    assert methods[:3] == ["client.capabilities", "session.resume", "prompt.submit"], methods
    assert serve.calls[0][1] == {"server_requests": True}
    assert serve.calls[2][1]["text"] == "Hello there"


def test_r3_rules_and_an_image_reach_the_pane_as_an_attachment_then_the_prompt(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Noted.")])
        cid, _ = await chat(island, "Model the chair.", "scene-1",
                            rules={"version": 1, "global": [{"id": "g", "text": "Always use metric units.", "enabled": True}], "project": []},
                            content=[{"type": "text", "text": "Model the chair."},
                                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}],
                            attachment_names=["front.png"])
        await island.ended(cid)
        return serve

    serve = run(stack, scenario)
    order = [m for m, _ in serve.calls if m in ("image.attach_bytes", "prompt.submit")]
    assert order == ["image.attach_bytes", "prompt.submit"], "the image is attached before the prompt"
    assert serve.only().images == [("front.png", PNG)]
    text = next(p for m, p in serve.calls if m == "prompt.submit")["text"]
    assert "Always use metric units." in text and text.rstrip().endswith("Model the chair.")


# ---------------------------------------------------------------------------------------------------- steer and cancel
def test_a_chat_during_the_turn_steers_it_and_is_answered_joined(stack):
    async def scenario(serve, units, island, front):
        gate = asyncio.Event()
        serve.scripts.append([("say", "Making"), ("gate", gate), ("say", "it red.")])
        cid, _ = await chat(island, "Make a chair", "scene-1")
        await island.wait(lambda f: f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid
                          and "append" in (f["params"]["event"].get("ephemeral") or {}))
        _, rid = await chat(island, "Actually make it red", "scene-1")
        reply = await island.reply(rid)
        gate.set()
        await island.ended(cid)
        return reply, island.events(cid), serve.only().steers

    reply, events, steers = run(stack, scenario)
    assert reply["result"] == {"state": "complete", "result": {"ok": True, "joined": True}}
    assert steers == ["Actually make it red"], "session.steer carried the message"
    assert events[-1]["status"] == "completed" and final_text(events) == "Making it red."


def test_cancel_interrupts_the_panes_turn(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "working"), ("until_interrupt",)])
        cid, _ = await chat(island, "Do a long thing", "scene-1")
        await island.wait(lambda f: f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid
                          and "append" in (f["params"]["event"].get("ephemeral") or {}))
        _, rid = await island.command("agent.cancel", {"session_id": "scene-1"})
        reply = await island.reply(rid)
        await island.ended(cid)
        for _ in range(100):
            if front.links["scene-1"].running is False:
                break
            await asyncio.sleep(0.05)
        return reply, island.events(cid), [m for m, _ in serve.calls], front.links["scene-1"].running

    reply, events, methods, running = run(stack, scenario)
    assert reply["result"]["result"]["cancelled"] is True
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "cancelled"
    assert "session.interrupt" in methods and running is False


# ---------------------------------------------------------------------------------------------------- questions and permissions
def test_a_clarify_is_the_islands_question_and_its_answer_continues_the_same_hermes_turn(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("clarify", "Round or square table?", ["Round", "Square"]), ("say", "Round it is.")])
        cid, _ = await chat(island, "Make a table", "scene-1")
        await island.ended(cid)
        first = island.events(cid)
        q = next(e for e in first if e.get("interrupt_id"))
        cid2, _ = await island.command("agent.input", {"session_id": "scene-1", "action": "respond", "text": "Round",
                                                       "answers": ["Round"], "interrupt_id": q["interrupt_id"]})
        await island.ended(cid2)
        return first, q, island.events(cid2), serve.only().answers

    first, q, second, answers = run(stack, scenario)
    assert q["input_type"] == "choice" and [a["value"] for a in q["actions"]] == ["Round", "Square"]
    assert "Round or square table?" in q["content"]["set"]
    assert first[-1]["type"] == "turn_end" and first[-1]["status"] == "in_progress", "the run stays open until the answer"
    assert not [s for e in first if e.get("steps") for s in e["steps"]["items"] if s["label"] == "clarify"], "clarify is no step"
    assert answers == [("clarify", {"answer": "Round"})]
    assert final_text(second) == "Round it is." and second[-1]["status"] == "completed"


def test_a_question_the_pane_answered_closes_the_islands_card_and_the_turn_goes_on_in_the_island(stack):
    """Both clients get the request and the first answer wins; the island is sent no request.cancel (measured), so it closes its
    card itself when the turn moves on, and shows the rest of the turn as its continuation (the same run)."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid0, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid0)
        tui = await Tui(serve).attach(serve.only().stored_id)
        serve.scripts.append([("clarify", "Round or square table?", ["Round", "Square"]), ("say", "Square it is.")])
        cid, _ = await chat(island, "Make a table", "scene-1")
        await island.ended(cid)
        first = island.events(cid)
        q = next(e for e in first if e.get("interrupt_id"))
        await tui.answer({"answer": "Square"})
        pane = await island.wait(lambda f: f.get("method") == "agent.turn.started" and f["params"].get("origin") == "pane")
        tid = pane["params"]["turn_id"]
        await island.ended(tid)
        session = stack.app.state.agent.sessions["scene-1"]
        await tui.close()
        return first, q, pane["params"], island.events(tid), serve.only().answers, session.pending_question

    first, q, started, rest, answers, pending = run(stack, scenario)
    assert answers == [("clarify", {"answer": "Square"})], "the pane's answer won"
    assert started["run_id"] == first[0]["run_id"], "the same run: the island takes it as its continuation"
    close = next(e for e in rest if e.get("bubble_id") == q["bubble_id"])
    assert close["input_type"] == "" and close["actions"] == [] and close["content"]["set"].endswith(ANSWERED_ELSEWHERE)
    assert final_text(rest) == "Square it is." and rest[-1]["status"] == "completed"
    assert pending is None, "the island's question is closed"


def test_an_approval_is_the_islands_permission_card_and_its_choice_goes_back(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("approval", "rm -rf build/tmp"), ("say", "Left it alone.")])
        cid, _ = await chat(island, "Clean up", "scene-1")
        await island.ended(cid)
        card = next(e for e in island.events(cid) if e.get("interrupt_id"))
        cid2, _ = await island.command("agent.input", {"session_id": "scene-1", "action": "respond", "text": "deny",
                                                       "interrupt_id": card["interrupt_id"]})
        await island.ended(cid2)
        return card, island.events(cid2), serve.only().answers

    card, second, answers = run(stack, scenario)
    assert card["input_type"] == "approval" and "rm -rf build/tmp" in card["content"]["set"]
    assert [a["value"] for a in card["actions"]] == ["once", "session", "always", "deny"]
    assert [a["label"] for a in card["actions"]][-1] == "Deny"
    assert answers == [("approval", {"choice": "deny"})]
    steps = [e for e in second if e.get("steps")][-1]["steps"]["items"]
    assert [(s["label"], s["status"]) for s in steps] == [("terminal", "failed")]
    assert final_text(second) == "Left it alone."


# ---------------------------------------------------------------------------------------------------- the pane's own turns (A2, A3)
def test_a_turn_typed_in_the_pane_is_an_island_turn_with_its_text_from_the_history(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        await serve.pane_prompt(serve.only(), "tui says hi", [("say", "Hello from the pane.")])
        started = await island.wait(lambda f: f.get("method") == "agent.turn.started" and f["params"].get("origin") == "pane")
        tid = started["params"]["turn_id"]
        await island.ended(tid)
        return started["params"], island.events(tid)

    started, events = run(stack, scenario)
    assert started["user_text"] == "tui says hi" and started["session_id"] == "scene-1"
    assert final_text(events) == "Hello from the pane." and events[-1]["status"] == "completed"


def test_a_tool_called_in_a_pane_typed_turn_reaches_the_scene_through_the_tabs_current_socket(stack):
    """A3: no island turn asked for it; the call goes to the scene tab's current client socket, and its step comes from serve's
    events once (not again from the MCP side)."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        await serve.pane_prompt(serve.only(), "what is in the scene?", [("mcp", "scene_summary", {}), ("say", "One cube.")])
        started = await island.wait(lambda f: f.get("method") == "agent.turn.started" and f["params"].get("origin") == "pane")
        await island.ended(started["params"]["turn_id"])
        return island.scripts, island.events(started["params"]["turn_id"]), serve.mcp_results

    scripts, events, results = run(stack, scenario)
    assert scripts and scripts[-1]["session_id"] == "scene-1", "the scene tab's own Blender ran it"
    assert results and results[-1]["isError"] is False and "Cube" in results[-1]["content"][0]["text"]
    labels = [s["label"] for s in [e for e in events if e.get("steps")][-1]["steps"]["items"]]
    assert labels == ["scene_summary"]
    assert final_text(events) == "One cube."


def test_with_no_lampway_window_a_tool_call_is_refused_saying_lampway_is_not_open(stack):
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        await island.close()
        for _ in range(100):
            if stack.app.state.agent.socket_for("scene-1") is None:
                break
            await asyncio.sleep(0.05)
        task = await serve.pane_prompt(serve.only(), "summarise", [("mcp", "scene_summary", {}), ("say", "Could not.")])
        await task
        return serve.mcp_results

    results = run(stack, scenario)
    assert results[-1]["isError"] is True and "Lampway is not open" in results[-1]["content"][0]["text"]


def test_a_tool_the_users_capabilities_switch_off_is_refused_at_call_time(stack):
    from lampway_server import capabilities as CAP

    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        CAP.ACTIVE.set("scene.read", enabled=False, by="user")
        task = await serve.pane_prompt(serve.only(), "summarise", [("mcp", "scene_summary", {}), ("say", "No.")])
        await task
        return serve.mcp_results, island.scripts

    results, scripts = run(stack, scenario)
    assert results[-1]["isError"] is True and scripts == [], "E2: nothing reached Blender"


# ---------------------------------------------------------------------------------------------------- persistence
def test_the_islands_socket_closing_stops_nothing_and_attach_replays_the_turn(stack):
    async def scenario(serve, units, island, front):
        gate = asyncio.Event()
        serve.scripts.append([("say", "first"), ("gate", gate), ("say", "after")])
        cid, _ = await chat(island, "Make a chair", "scene-1")
        ev = await island.wait(lambda f: f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid
                               and "append" in (f["params"]["event"].get("ephemeral") or {}))
        last_seq = ev["params"]["seq"]
        await island.close()
        hub = stack.app.state.agent
        for _ in range(100):
            if getattr(hub.sessions["scene-1"].current, "detached", False):
                break
            await asyncio.sleep(0.05)
        gate.set()
        again = await Island(stack.base, stack.settings).connect()
        rid = await again.send("agent.attach", {"session_id": "scene-1", "turn_id": cid, "after_seq": last_seq})
        await again.reply(rid)
        await again.ended(cid)
        await again.close()
        return [m for m, _ in serve.calls], again.events(cid), last_seq, [f["params"]["seq"] for f in again.frames
                                                                         if f.get("method") == "agent.turn.event"]

    methods, events, last_seq, seqs = run(stack, scenario)
    assert "session.interrupt" not in methods, "the island leaving stopped nothing in Hermes"
    assert seqs == list(range(last_seq + 1, last_seq + 1 + len(seqs))), "every missed event, once, in order"
    assert final_text(events) == "first after" and events[-1]["status"] == "completed"


def test_a_dropped_connection_to_serve_catches_up_from_the_replay_ring(stack):
    async def scenario(serve, units, island, front):
        gate = asyncio.Event()
        serve.scripts.append([("say", "one"), ("gate", gate), ("say", "two")])
        cid, _ = await chat(island, "Go", "scene-1")
        await island.wait(lambda f: f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid
                          and "append" in (f["params"]["event"].get("ephemeral") or {}))
        for ws in list(serve.clients):                                   # serve drops Lampway's connection mid-turn
            await ws.close()
        await asyncio.sleep(0.1)
        gate.set()                                                       # the turn goes on and ends while nobody listens
        await island.ended(cid, timeout=60)
        return [m for m, p in serve.calls if m == "session.events.since"], island.events(cid)

    since, events = run(stack, scenario)
    assert since, "the reconnect asked for what it missed"
    assert final_text(events) == "one two" and events[-1]["status"] == "completed"


def test_slash_new_in_the_pane_is_followed_by_the_island(stack):
    """Spec Q15 (proposed): ``/new`` closes the shared session for every client; the island follows the pane to its new one."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        old = serve.only()
        new = await serve.pane_new(old)
        for _ in range(100):
            if front.links["scene-1"].live_id == new.live_id:
                break
            await asyncio.sleep(0.05)
        serve.scripts.append([("say", "Fresh start.")])
        cid2, _ = await chat(island, "Again", "scene-1")
        await island.ended(cid2)
        return front.links["scene-1"].live_id, new, units.infos["scene-1"].stored_id, island.events(cid2), new.history

    live, new, stored, events, history = run(stack, scenario)
    assert live == new.live_id and stored == new.stored_id, "the unit's record follows the pane"
    assert final_text(events) == "Fresh start." and history[0]["text"] == "Again"


def test_slash_new_in_the_pane_tells_the_tabs_client_once_so_the_island_starts_a_new_chat(stack):
    """Q15, the client's half needs a frame: the tab's session id (the unit) does not change, so nothing else tells the island
    that the pane's conversation is a new one. ``agent.pane.new_conversation`` goes to the tab's current socket, once, even
    though serve announces ``sessions.changed`` twice (closed, then created)."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Hi.")])
        cid, _ = await chat(island, "Hello", "scene-1")
        await island.ended(cid)
        new = await serve.pane_new(serve.only())
        frame = await island.wait(lambda f: f.get("method") == "agent.pane.new_conversation")
        for _ in range(20):                                              # a second follow would notify again: give it time
            await asyncio.sleep(0.05)
        frames = [f for f in island.frames if f.get("method") == "agent.pane.new_conversation"]
        return frame["params"], len(frames), front.links["scene-1"].live_id, new

    params, count, live, new = run(stack, scenario)
    assert params == {"session_id": "scene-1", "origin": "pane"}
    assert count == 1 and live == new.live_id


def test_after_slash_new_the_islands_next_chat_is_a_prompt_in_the_new_session_not_an_answer_to_the_old_question(stack):
    """The island's question card belonged to the closed session: once the pane's ``/new`` is followed, the tab's next chat is a
    new prompt (the client has filed the old chat with its card), never a response to a request of a session that is gone."""
    async def scenario(serve, units, island, front):
        serve.scripts.append([("clarify", "Round or square table?", ["Round", "Square"]), ("say", "Round it is.")])
        cid, _ = await chat(island, "Make a table", "scene-1")
        await island.ended(cid)
        old = serve.only()
        new = await serve.pane_new(old)
        await island.wait(lambda f: f.get("method") == "agent.pane.new_conversation")
        serve.scripts.append([("say", "Fresh start.")])
        cid2, _ = await chat(island, "Again", "scene-1")
        await island.ended(cid2, timeout=20)
        return island.events(cid2), new.history, old.answers, stack.app.state.agent.sessions["scene-1"].pending_question

    events, history, old_answers, pending = run(stack, scenario)
    assert old_answers == [], "nothing answered the closed session's question"
    assert history and history[0]["text"] == "Again" and final_text(events) == "Fresh start."
    assert pending is None


# ---------------------------------------------------------------------------------------------------- refusals before a turn
def test_a_tab_in_your_agent_mode_is_refused_first_and_nothing_opens(stack):
    async def scenario(serve, units, island, front):
        cid, rid = await chat(island, "Hello", "scene-1", agent_mode="byoa")
        return await island.reply(rid), units.opened, serve.calls

    reply, opened, calls = run(stack, scenario)
    assert reply["result"]["result"]["code"] == "wrong_mode" and opened == [] and calls == []


def test_an_agents_socket_never_opens_lampway_agents_pane(stack):
    async def scenario(serve, units, island, front):
        frame = island.fake.handshake_frame()
        frame["params"]["role"] = "sandbox"                       # a headless worker's socket: an agent, not the user
        await island.ws.send(json.dumps(frame))
        await asyncio.sleep(0.2)
        cid, rid = await chat(island, "Hello", "scene-1")
        return await island.reply(rid), units.opened

    reply, opened = run(stack, scenario)
    assert reply["result"]["result"]["ok"] is False and reply["result"]["result"]["code"] == "agent_origin" and opened == []


def test_the_herdr_server_is_never_started_for_a_chat(stack, monkeypatch):
    monkeypatch.setattr(L, "server_status", lambda root: {"running": False})

    async def scenario(serve, units, island, front):
        cid, rid = await chat(island, "Hello", "scene-1")
        return await island.reply(rid), units.opened

    reply, opened = run(stack, scenario)
    assert reply["result"]["result"]["code"] == "herdr_not_running" and opened == []
    assert "Start the herdr server" in reply["result"]["result"]["help"][0]
