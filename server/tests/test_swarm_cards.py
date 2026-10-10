# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Parallel Agents cards for every swarm, whoever started it (docs/reports/agent-modes-spec.md S1 "the todo rows and the Parallel
Agents cards", S3, A4; the captain, 2026-10-07: nothing is hidden from the user or the agent).

The client shows a swarm's workers as the cards its chat's ``todo`` slot feeds (``slot_processor._apply_todo_slot`` mirrors it into
the Parallel Agents panel) and offers "Retry failed tasks" as an ``actions`` chip. A swarm a bound Mode 2 pane starts over MCP, and one
Lampway Agent's Hermes pane starts over its engine endpoint, ran in no island turn, so they emitted none. Now every swarm reports to
the island of its unit's scene tab in those same frames:

* a swarm started inside an island turn that carries its own stream keeps it (``emit_todo``);
* a Mode 1 swarm while Lampway Agent's island turn runs (the front's live sink): on that turn's bubble;
* otherwise (a Mode 2 swarm; a Mode 1 swarm between turns): on a card turn of its own, an observed turn (``observed: true`` with the
  ``swarm`` id), the frames a Your agent tab already renders, on the scene tab's current client socket.

Retry works from those cards under the same rules: the chip sends the user's "continue" (``agent.byoa.send`` in a Your agent tab,
``agent.chat`` in a Lampway Agent tab), from the user's own Client socket; the failed tasks run again as a new swarm in the original's
mode, collected into the scene, and the unit's agent is told what happened.

herdr and the panes are played (``PaneHerdr``, the Mode 2 rig of ``test_swarm_panes.py`` and this file's Mode 1 ``PanePlayer``); the desktop is the fake fleet, and the frames checked are the ones it received."""
import threading
import time

import pytest
from starlette.testclient import TestClient

from lampway_server.agent import questions as Q
from lampway_server.agent.providers.base import Text
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.app import create_app
from lampway_server.auth import mint_jwt

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet
from .mode1_support import units_for
from .test_swarm_panes import SCENE, rig, serve_parent, strict, tasks, wait_for  # noqa: F401  (the Mode 2 rig and its fixtures)
from .herdr_support import PaneHerdr
from .launch_notice_support import retained_human_disclosure  # noqa: F401
from .mode1_support import fake_engine, mcp_entry


def marker_play(swarm_id, worker_id):
    """What a Mode 1 worker's Hermes does by default: one marked script in its own scene, then its summary."""
    n = worker_id.split("-")[1]
    return [("call", "run_blender_python", {"script": f"import bpy\n# by {worker_id}\n# collection QA_candidates w{n}_L000\n"}),
            ("done", f"w{n} drew its markers")]


class PanePlayer:
    """Plays every Mode 1 worker pane the swarm opens, as its Hermes would, over the MCP server its config.yaml names:
    ``("call", tool, args)``, ``("done", summary)`` or ``("exit",)`` (the pane closed)."""

    def __init__(self, http, cockpit, herdr, play):
        self.http, self.cockpit, self.herdr, self.play = http, cockpit, herdr, play
        self.seen = set()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)

    def _watch(self):
        while not self.stop.is_set():
            for rec in self.cockpit.list_sessions():
                if rec.get("created_by") == "swarm" and rec["id"] not in self.seen:
                    self.seen.add(rec["id"])
                    threading.Thread(target=self._play, args=(rec,), daemon=True).start()
            time.sleep(0.02)

    def _play(self, rec):
        _, swarm_id, worker_id = rec["swarm_binding"].split(":")
        url, headers = mcp_entry(rec["home"])
        for step in self.play(swarm_id, worker_id):
            if step[0] == "exit":
                self.herdr.exit(rec["pane_id"])
                return
            name, arguments = (step[1], step[2]) if step[0] == "call" else ("lampway_worker_done", {"summary": step[1]})
            self.http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
                           headers={**headers, "Accept": "application/json, text/event-stream"})


@pytest.fixture
def played(monkeypatch, tmp_path):
    """Lampway's herdr, played, and a stand-in engine build for the Mode 1 hook."""
    from lampway_server.herdr import host as H
    from lampway_server.herdr import launcher as L
    from lampway_server.herdr import swarm_brain as SB
    herdr = PaneHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    monkeypatch.setattr(SB, "POLL_S", 0.05)
    (tmp_path / "proj").mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    cockpit.engine_for_tests = fake_engine(tmp_path / "engines")
    return cockpit, herdr


RETRY = [{"label": Q.RETRY_LABEL, "value": Q.RETRY_ACTION, "style": "primary"}]
UNIT = "7a2b3c4d-1e2f-4a5b-8c9d-0e1f2a3b4c5d"


def card_turn(fleet, swarm_id, session_id=SCENE):
    """(started, events, ended) of the card turn the island got for a swarm, else (None, [], None)."""
    frames = list(fleet.frames)
    started = next((f["params"] for f in frames if f.get("method") == "agent.turn.started" and f["params"].get("swarm") == swarm_id
                    and f["params"].get("session_id") == session_id), None)
    if started is None:
        return None, [], None
    tid = started["turn_id"]
    events = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == tid]
    ended = next((f["params"] for f in frames if f.get("method") == "agent.turn.ended" and f["params"]["turn_id"] == tid), None)
    return started, events, ended


def todos(events):
    return [e["todo"] for e in events if "todo" in e]


def one_done_one_failed(rig):
    """A bound pane's swarm of two: worker-1 finishes, worker-2's harness quits; then the pane collects it."""
    rig.bind_parent()
    sid = rig.parent_json("swarm_start", {"tasks": tasks("boots", "belt")})["swarm_id"]
    panes = wait_for(lambda: len(rig.worker_panes()) == 2 and rig.worker_panes())
    assert panes, "the worker panes never opened"
    one = next(p for p in panes if p["swarm_binding"].endswith(":worker-1"))
    two = next(p for p in panes if p["swarm_binding"].endswith(":worker-2"))
    rig.worker_call(one, "lampway_worker_done", {"summary": "boots made"})
    rig.herdr.exit(two["pane_id"])
    assert wait_for(lambda: rig.status(sid)["worker-2"]["status"] == "failed" and rig.status(sid)["worker-1"]["status"] == "staged")
    rig.parent_json("swarm_collect", {"swarm_id": sid})
    return sid


def island_send(rig, text, rid):
    rig.held["ws"].send_json({"jsonrpc": "2.0", "id": rid, "method": "agent.byoa.send",
                              "params": {"command_id": f"c-{rid}", "payload": {"session_id": SCENE, "text": text}}})
    return wait_for(lambda: next((f for f in list(rig.fleet.frames) if f.get("id") == rid and "result" in f), None))


# ------------------------------------------------------------------------------------------------------------- Mode 2
def test_a_swarm_a_bound_pane_starts_shows_its_workers_as_parallel_agents_cards_in_its_scene_tab(retained_human_disclosure, rig):
    sid = one_done_one_failed(rig)
    started, events, ended = wait_for(lambda: (r := card_turn(rig.fleet, sid))[2] and r) or card_turn(rig.fleet, sid)
    assert started is not None, "the island got no card turn for the pane's swarm, so no Parallel Agents card appears"
    assert started["observed"] is True and started["user_text"] == "" and started["pane"] == rig.parent["id"]
    rows = todos(events)
    assert rows and len(rows[0]) == 2 and all(set(r) == {"id", "text", "status"} for r in rows[0])
    assert [r["id"] for r in rows[0]] == [f"{sid}:worker-1", f"{sid}:worker-2"] and rows[0][0]["text"].startswith("boots: ")
    assert any(r["status"] == "IN_PROGRESS" for t in rows for r in t), "the cards follow the workers"
    assert [r["status"] for r in rows[-1]] == ["DONE", "FAILED"]
    assert len({e["bubble_id"] for e in events if "bubble_id" in e}) == 1, "one bubble carries the swarm's cards"
    assert [e["actions"] for e in events if "actions" in e] == [RETRY], "a failed task offers Retry on the cards"
    assert events[0] == {"type": "run_status", "run_id": started["run_id"], "status": "in_progress"}
    assert events[-1] == {"type": "turn_end", "status": "completed", "run_id": started["run_id"]}, "no offset: the pane's own cursor is not moved"
    assert ended is not None and ended["last_seq"] == len(events) - 1


def test_retry_from_the_cards_reruns_the_failed_tasks_on_the_users_click_and_tells_the_pane(retained_human_disclosure, rig):
    sid = one_done_one_failed(rig)
    reply = island_send(rig, Q.CONTINUE_MESSAGE, "retry-1")                  # the chip's click: the user's "continue"
    assert reply and reply["result"]["result"] == {"ok": True, "pane": rig.parent["id"], "retry": True}
    new = wait_for(lambda: [r for r in rig.worker_panes() if r["swarm_binding"].startswith("swarm:sw2:")])
    assert new and len(new) == 1 and new[0]["name"].startswith("belt"), "only the failed task runs again, on the parent's harness"
    assert new[0]["agent"] == "claude"
    rig.worker_call(new[0], "lampway_worker_done", {"summary": "belt made"})
    typed = wait_for(lambda: [c["args"] for c in rig.herdr.calls if c["args"][:3] == ["pane", "send-text", rig.parent["pane_id"]]])
    assert typed, "the pane's agent was never told"
    note = typed[0][3]
    assert note.startswith("continue") and "sw2" in note and "Retry" in note and "belt" in note and "\n" not in note
    started, events, ended = card_turn(rig.fleet, "sw2")
    assert started is not None and [r["status"] for r in todos(events)[-1]] == ["DONE"] and ended is not None
    assert not [e for e in events if "actions" in e], "nothing failed this time: no Retry chip"
    first = rig.parent_json("swarm_status", {"swarm_id": sid})
    assert first["retried_as"] == "sw2", "the agent can see what its swarm became"
    assert rig.parent_json("swarm_status", {"swarm_id": "sw2"})["collected"] is True, "the retried swarm is the pane's own"
    again = island_send(rig, Q.CONTINUE_MESSAGE, "retry-2")
    assert "retry" not in again["result"]["result"], "a task is retried once per click; nothing is left to retry"


def test_a_continue_from_an_agent_socket_never_retries(retained_human_disclosure, rig, settings):
    one_done_one_failed(rig)
    now = int(time.time())
    token = mint_jwt(settings.jwt_secret, {"sub": settings.user_email, "iat": now, "exp": now + 600, "origin": "agent"})
    with rig.fake.connect_ws(token=token) as ws:
        rig.fake.handshake(ws)
        rid = rig.fake.request(ws, "agent.byoa.send", {"command_id": "c-agent", "payload": {"session_id": SCENE, "text": "continue"}})
        reply = next(f for f in iter(ws.receive_json, None) if f.get("id") == rid)
    assert reply["result"]["result"]["ok"] is False and "agent sends are off" in reply["result"]["result"]["message"]
    time.sleep(0.3)
    assert not [r for r in rig.worker_panes() if r["swarm_binding"].startswith("swarm:sw2:")], "only the user's click retries"


# ------------------------------------------------------------------------------------------------------------- Mode 1
@pytest.fixture
def mode1(settings, played):
    """A server with Lampway Agent's front (``HermesFront``) as the hub's engine, the real Mode 1 hook on a stand-in engine, the
    desktop speaking for the scene tab ``UNIT``. A tool call of the unit's Hermes is ``front.call_tool`` (the engine endpoint's)."""
    from lampway_server import capabilities as CAP
    from lampway_server.engine.front import HermesFront
    cockpit, herdr = played
    app = create_app(settings, provider=ScriptedProvider([[Text("unused")]]), cockpit=cockpit)
    cockpit.mode1 = units_for(cockpit, settings.state_dir, app.state.engine_tokens, engine=cockpit.engine_for_tests)
    CAP.ACTIVE.set("swarm", enabled=True, by="user")
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        ready, stop, held = threading.Event(), threading.Event(), {}
        t = threading.Thread(target=serve_parent, args=(fake, fleet, ready, stop, held), daemon=True)
        t.start()
        assert ready.wait(10)
        hub = app.state.agent
        front = HermesFront(hub, cockpit.mode1)
        hub.engine = front
        held["ws"].send_json({"jsonrpc": "2.0", "id": "st-1", "method": "agent.status", "params": {"session_ids": [UNIT]}})
        assert wait_for(lambda: hub.socket_for(UNIT) is not None)

        class M:
            pass
        m = M()
        m.http, m.app, m.hub, m.front, m.fleet, m.cockpit, m.herdr = http, app, hub, front, fleet, cockpit, herdr
        m.call = lambda name, args: http.portal.call(front.call_tool, UNIT, name, args)
        try:
            yield m
        finally:
            async def cancel_all():
                for swarm in hub.swarm.swarms.values():
                    hub.swarm.cancel_all(swarm)
            http.portal.call(cancel_all)
            wait_for(lambda: all(w.task is None or w.task.done() for s in hub.swarm.swarms.values() for w in s.workers), timeout=10)
            hub.engine = None
            stop.set()
            try:
                held["ws"].send_json({"jsonrpc": "2.0", "method": "system.ping", "id": "bye"})
            except Exception:  # noqa: BLE001
                pass
            t.join(10)
            fleet.close()


def _start_and_collect(m, play):
    import json
    with PanePlayer(m.http, m.cockpit, m.herdr, play):
        text, is_error = m.call("swarm_start", {"tasks": [{"name": "a", "prompt": "QA the piece a"}, {"name": "b", "prompt": "QA the piece b"}]})
        assert is_error is False, text
        sid = json.loads(text)["swarm_id"]
        text, is_error = m.call("swarm_collect", {"swarm_id": sid})
        assert is_error is False, text
    return sid


def test_a_swarm_lampway_agents_pane_starts_between_island_turns_gets_a_card_turn_of_its_own(mode1):
    """Mode 1 with no island turn running (a swarm_start the Hermes pane made in a turn the island did not open, or after its turn
    ended): the cards go to the scene tab on a card turn of their own, as a Mode 2 swarm's do."""
    sid = _start_and_collect(mode1, lambda s, w: [("exit",)] if w == "worker-2" else marker_play(s, w))
    started, events, ended = wait_for(lambda: (r := card_turn(mode1.fleet, sid, UNIT))[2] and r) or card_turn(mode1.fleet, sid, UNIT)
    assert started is not None and started["observed"] is True and started["swarm"] == sid
    assert [r["status"] for r in todos(events)[-1]] == ["DONE", "FAILED"] and [e["actions"] for e in events if "actions" in e] == [RETRY]
    assert ended is not None


def test_a_swarm_lampway_agents_pane_starts_in_an_island_turn_shows_its_cards_on_that_turns_bubble(mode1):
    """Mode 1 while Lampway Agent's island turn runs (the front's live sink): the cards and the Retry chip are on that turn's own
    bubble, as the built-in turn's were; no second turn is opened."""
    from lampway_server.agent.turns import Turn, TurnStream
    from lampway_server.engine.front import Sink
    socket = mode1.hub.socket_for(UNIT)
    turn = Turn(UNIT, "t-island", "run-island")
    link = mode1.front._link(UNIT)
    link.sink = Sink(socket, mode1.hub._session(UNIT), turn, TurnStream(socket, turn), "bubble-island", [])
    sid = _start_and_collect(mode1, lambda s, w: [("exit",)] if w == "worker-2" else marker_play(s, w))
    events = wait_for(lambda: [e for e in turn.events if "actions" in e] and turn.events)
    assert events, "the island turn's bubble never got the Retry chip"
    rows = todos(events)
    assert rows and {e["bubble_id"] for e in events if "todo" in e} == {"bubble-island"}
    assert [r["status"] for r in rows[-1]] == ["DONE", "FAILED"] and [e["actions"] for e in events if "actions" in e] == [RETRY]
    got = [f["params"] for f in list(mode1.fleet.frames) if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == "t-island"]
    assert [p["event"] for p in got if "todo" in p["event"]], "the frames reached the desktop on the island turn"
    assert card_turn(mode1.fleet, sid, UNIT)[0] is None, "no card turn of its own while an island turn shows them"
    link.sink = None


def test_a_mode1_swarm_handed_a_turns_stream_follows_the_island_not_the_turn_that_ended(mode1):
    """A tool call of the unit's Hermes may hand the swarm the island turn's stream (``emit_todo``); that turn can end long before
    the workers do. With Lampway Agent's front running, the cards go where the island is NOW: here no island turn runs, so a card
    turn of its own, and nothing more is written to the ended turn's stream."""
    import json
    from lampway_server.agent.swarm import SwarmContext
    dead = []

    async def emit_todo(rows):
        dead.append(rows)
    socket = mode1.hub.socket_for(UNIT)

    def call(name, args):
        ctx = SwarmContext(socket=socket, session_id=UNIT, turn_id="t-ended", call_id="c", run_id="run-ended", emit_todo=emit_todo)
        return mode1.http.portal.call(mode1.hub.swarm.call, name, args, ctx)
    with PanePlayer(mode1.http, mode1.cockpit, mode1.herdr, marker_play):
        text, is_error = call("swarm_start", {"tasks": [{"name": "a", "prompt": "QA the piece a"}]})
        assert is_error is False, text
        sid = json.loads(text)["swarm_id"]
        assert call("swarm_collect", {"swarm_id": sid})[1] is False
    started, events, ended = card_turn(mode1.fleet, sid, UNIT)
    assert started is not None and [r["status"] for r in todos(events)[-1]] == ["DONE"] and ended is not None
    assert dead == [], "the ended turn's stream is not where the island looks"


@pytest.mark.parametrize("finished", [False, True])
@pytest.mark.parametrize("hermes_running", [False, True])
def test_card_recovery_discovers_its_start_and_replays_it_without_replacing_the_hermes_turn(finished, hermes_running):
    """A fresh client missed the entire start; card discovery is independent of the scene's current agent turn."""
    import asyncio
    from types import SimpleNamespace
    from lampway_server.agent.turns import AgentHub, Turn
    from lampway_server.agent.swarm_island import SwarmIsland

    class Socket:
        def __init__(self):
            self.frames = []

        async def notify(self, method, params):
            self.frames.append((method, params))

    async def exercise():
        hub = AgentHub(None)
        first, restored = Socket(), Socket()
        hub.client_sockets[UNIT] = first
        session = hub._session(UNIT)
        hermes = Turn(UNIT, "t-hermes", "run-hermes") if hermes_running else None
        if hermes is not None:
            session.current = hermes
            session.turns[hermes.turn_id] = hermes
            session.last_turn_id = hermes.turn_id
        island = SwarmIsland(hub)
        swarm = SimpleNamespace(id="fake-recovery", parent_session=UNIT, mode="byoa", owner="pane:parent",
                                harness_id="claude", collected=False, retried=False)
        rows = [{"id": "fake-recovery:worker-1", "text": "Build a chair", "status": "IN_PROGRESS"}]
        await island.report(swarm, rows)
        if finished:
            await island.report(swarm, [{**rows[0], "status": "DONE"}], final=True)
        original = next(params for method, params in first.frames if method == "agent.turn.started")
        status = await hub._status(restored, {"session_ids": [UNIT]})
        if hermes is not None:
            assert status["turns"][UNIT]["turn_id"] == hermes.turn_id
        else:
            assert status["turns"] == {}
        assert status.get("swarm_cards", {}).get(UNIT) == [original], "status must discover cards separately from the agent turn"
        assert session.current is hermes and session.last_turn_id == (hermes.turn_id if hermes else None)
        assert not (await hub._status(restored, {"session_ids": ["another-unit"]})).get("swarm_cards"), "only the asked unit"
        result = await hub._attach(restored, {"session_id": UNIT, "turn_id": original["turn_id"], "after_seq": -1})
        assert result["status"] == "ok"
        assert restored.frames[0] == ("agent.turn.started", {**original, "replay": True}), "start metadata must precede replay slots"
        replayed = [p["event"] for method, p in restored.frames if method == "agent.turn.event"]
        assert replayed == session.turns[original["turn_id"]].events
        assert any(method == "agent.turn.ended" for method, _ in restored.frames) is finished
        unrelated = Socket()
        assert await hub._attach(unrelated, {"session_id": "another-unit", "turn_id": original["turn_id"]}) == {"status": "unavailable"}
        assert unrelated.frames == [], "another unit's session cannot attach the card"
    asyncio.run(exercise())
