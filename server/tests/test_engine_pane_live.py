# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1 live (docs/reports/agent-modes-spec.md A1-A3, A5, E1.3-E1.5): the REAL server with a finished pinned build (found, so in
Mode 1's seat), the Lampway client's own frames, and herdr played but running its panes for real (``live_support``): the
island's first chat opens the unit's pane, whose REAL wrapper (``engine/hermes_pane.py``) starts the REAL pinned ``hermes serve``
and Hermes's REAL TUI in a pty, and the island attaches to that serve as its second client.

The model is the app's main provider behind Lampway's gateway, scripted by markers in the user's text (no network, no spend); every
proxy variable of the pane points at Lampway's egress proxy on a fresh install (every route off), so nothing leaves the machine and
every attempt is a refusal row.

Needs a finished engine build (``scripts/lampway/engine_env.py``: ``$LAMPWAY_ENGINES_DIR``, or ``build/engines`` in this checkout or
one above it), its prebuilt TUI (``engine.json`` ``tui``, or ``LAMPWAY_HERMES_TUI_DIR``) and Node (``LAMPWAY_NODE`` or on PATH).
Without them every test SKIPS, and a skip is not a pass. Each test starts one pane (serve listens in ~3 s)."""

import asyncio
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import pytest

from lampway_server import capabilities as CAP
from lampway_server import egress as EG
from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.app import create_app
from lampway_server.engine import hermes_config as HC
from lampway_server.engine import wiring as W
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .herdr_support import needs_herdr, short_root
from .live_support import RunningHerdr, wait_for
from .serve_support import Island, Stack, free_port


def _engine():
    given = os.environ.get("LAMPWAY_ENGINES_DIR")
    candidates = [Path(given)] if given else [p / "build" / "engines" for p in Path(__file__).resolve().parents]
    for c in candidates:
        rec = W.find_engine(c)
        if rec is not None:
            return c, rec
    return None, None


ENGINES, ENGINE = _engine()
TUI = Path(os.environ.get("LAMPWAY_HERMES_TUI_DIR") or (Path(ENGINE["dir"]) / ENGINE["tui"] if ENGINE and ENGINE.get("tui") else "/nonexistent"))
NODE = os.environ.get("LAMPWAY_NODE") or shutil.which("node")
MISSING = ("no finished engine build (LAMPWAY_ENGINES_DIR or build/engines): run scripts/lampway/engine_env.py" if ENGINE is None else
           f"no prebuilt Hermes TUI at {TUI} (engine.json tui, or LAMPWAY_HERMES_TUI_DIR)" if not (TUI / "dist" / "entry.js").is_file() else
           "no Node.js for Hermes's TUI (LAMPWAY_NODE or node on PATH)" if not NODE else
           f"the engine at {ENGINE['dir']} has no hermes binary" if not os.access(Path(ENGINE["dir"]) / "env/bin/hermes", os.X_OK) else None)
pytestmark = [pytest.mark.skipif(MISSING is not None, reason=MISSING or ""), pytest.mark.timeout(400)]

FULL = "mcp__lampway__scene_summary"
SCENE = {"success": True, "scene": "Scene", "object_count": 1, "objects": [{"name": "Cube", "type": "MESH"}]}
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class LiveProvider(ScriptedProvider):
    """The app's main provider, scripted by markers in the latest user text: ``SCENE`` calls scene_summary (directly when Hermes
    shows it, else through its tool_call bridge), ``ASK`` calls Hermes's clarify, ``APPROVE`` runs a deleting terminal command,
    ``HOLD`` waits for ``release`` before it answers. A request without tools is Hermes's auxiliary call (a title)."""

    name = "scripted-live"

    def __init__(self):
        super().__init__()
        self.release = threading.Event()
        self.release.set()
        self.target = None

    @staticmethod
    def _user_texts(request):
        return [m.text() for m in request.messages if m.role == "user" and m.text()]

    async def stream(self, request):
        self.requests.append(request)
        names = [t.name for t in request.tools]
        if not names:
            yield Text("Scene question")
            return
        users = self._user_texts(request)
        last = users[-1] if users else ""
        idx = max((i for i, m in enumerate(request.messages) if m.role == "user" and m.text()), default=-1)
        results = [p for m in request.messages[idx + 1:] for p in m.content if p.get("type") == "tool_result"]
        if not results and len(users) >= 2 and "HOLD" in users[-2]:      # a steer arrived as a user message after the tool's result
            results = [p for m in request.messages for p in m.content if p.get("type") == "tool_result"][-1:]
        if results and any("HOLD" in u for u in users[-2:]):
            await asyncio.to_thread(self.release.wait, 120)              # the tool ran; the answer waits for the test
        if results:
            seen = str(results[-1].get("content") or "")
            if "TERM" in last:
                yield Text(f"Terminal said: {seen[:200]}")
                return
            if "ASK" in last:
                choice = "Round" if "Round" in seen else "Square" if "Square" in seen else "?"
                yield Text(f"You chose {choice}.")
            elif "APPROVE" in last:
                yield Text("The command ran." if "approval-target" not in seen or "denied" not in seen.lower() else "Denied.")
            elif any("make it red" in u for u in users):
                yield Text("Red it is.")
            else:
                yield Text("There is one cube." if "Cube" in seen else f"Tool said: {seen[:80]}")
            return
        call = None
        if "SCENE" in last or "HOLD" in last:
            call = (FULL, {}) if FULL in names else ("tool_call", {"calls": [{"name": FULL, "arguments": {}}]})
        elif "ASK" in last:
            call = ("clarify", {"question": "Round or square table?", "choices": ["Round", "Square"]})
        elif "APPROVE" in last:
            call = ("terminal", {"command": f"rm -rf {self.target}"})
        elif "TERM" in last:
            reach = set(names) | set(HC.deferred_listing([{"type": "function", "function": {"name": t.name, "description": t.description}}
                                                          for t in request.tools])[0])
            if "terminal" not in reach:
                yield Text("No terminal here.")
                return
            call = ("terminal", {"command": "echo lampway-live-$((6*7))"}) if "terminal" in names else \
                ("tool_call", {"calls": [{"name": "terminal", "arguments": {"command": "echo lampway-live-$((6*7))"}}]})
        if call is None:
            yield Text("Hello from the gateway." if "rules" not in last.lower() else "Noted the rules.")
            return
        yield ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=call[0], arguments=call[1])


@pytest.fixture
def live(settings, tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(ENGINES))           # found, so in the seat: no switch (spec A5)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(project))
    monkeypatch.setenv("LAMPWAY_HERMES_TUI_DIR", str(TUI))
    monkeypatch.setenv("LAMPWAY_NODE", NODE)
    settings.port = free_port()
    strict = EG.Egress(tmp_path / "strict-egress")                       # a fresh install: every route off
    herdr = RunningHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "bin_path", lambda: "herdr (played)")
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(project))
    provider = LiveProvider()
    provider.target = str(project / "approval-target")
    state = {"settings": settings, "strict": strict, "herdr": herdr, "cockpit": cockpit, "provider": provider, "project": project,
             "tmp": tmp_path}

    def make_app():
        app = create_app(settings, provider=provider, egress=strict, cockpit=cockpit)
        assert app.state.engine_wiring is not None, "create_app did not select the engine"
        return app
    state["make_app"] = make_app
    yield state
    homes = [r.get("home") for r in cockpit.list_sessions() if r.get("home")]
    left = herdr.end_all(homes)
    assert left == [], f"a serve outlived its pane: {left}"


def run(live, scenario, app=None):
    app = app or live["make_app"]()
    with Stack(app, live["settings"]) as stack:
        async def go():
            island = await Island(stack.base, live["settings"], on_script=lambda p: SCENE).connect()
            try:
                return await scenario(stack, island)
            finally:
                await island.close()
        return asyncio.run(go())


async def chat(island, text, sid, **extra):
    cid, rid = await island.command("agent.chat", {**island.chat(text, sid), **extra})
    return cid, rid


def final_text(events):
    sets = [e["content"]["set"] for e in events if (e.get("content") or {}).get("set")]
    return sets[-1] if sets else None


def pane_of(live, unit):
    return next(r for r in live["cockpit"].list_sessions() if r.get("unit") == unit and r.get("role") == "main")


# ---------------------------------------------------------------------------------------------------- A1, A2, A3: the first turn
def test_live_the_first_chat_opens_the_real_pane_and_a_tool_turn_runs_through_it_with_the_tui_attached(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"
    checks = []

    async def scenario(stack, island):
        original = stack.app.state.engine_tokens.first_check

        def recorded(session_id, token, tools):
            verdict = original(session_id, token, tools)
            checks.append((session_id, [t["function"]["name"] for t in tools], verdict))
            return verdict
        stack.app.state.engine_tokens.first_check = recorded
        cid, _ = await chat(island, "SCENE: what is in my scene?", unit)
        await island.ended(cid, timeout=240)
        return island.events(cid), list(island.scripts), stack

    events, scripts, stack = run(live, scenario)
    rec = pane_of(live, unit)
    proc = live["herdr"].proc_for(rec)
    # the island's turn, through the pane's Hermes
    assert final_text(events) == "There is one cube.", events
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed"
    steps = [e for e in events if e.get("steps")][-1]["steps"]["items"]
    assert [(s["label"], s["status"]) for s in steps if s["label"] == "scene_summary"] == [("scene_summary", "done")]
    assert scripts and scripts[0]["session_id"] == unit, "the tool reached the scene tab's Blender"
    turns = [r for r in live["provider"].requests if r.tools]
    assert turns and (FULL in {t.name for t in turns[0].tools} or "tool_call" in {t.name for t in turns[0].tools})
    # Lampway's guidance on its tools reaches the model: Hermes appends the config's agent.system_prompt to its system message
    from lampway_server.agent.prompt import SYSTEM_PROMPT
    assert SYSTEM_PROMPT.splitlines()[0] in turns[0].system and "mcp__lampway__" in turns[0].system, turns[0].system[-2000:]
    assert turns[0].system.startswith("You are Hermes Agent"), "Hermes's own identity stays"
    # the pane: Lampway's wrapper in a pane of the unit's own tab, its record without a secret, its session in the home
    home = Path(rec["home"])
    token = (home / "serve.token").read_text()
    assert rec["agent"] == "lampway_hermes" and rec["role"] == "main" and rec["stored_session_id"]
    assert json.loads((home / "session.json").read_text())["stored_session_id"] == rec["stored_session_id"]
    assert token not in json.dumps(live["cockpit"].list_sessions()) and token not in " ".join(proc.argv)
    # the TUI shows the island's turn: the same live session, resumed (the island's prompt and the model's reply are on screen)
    assert wait_for(lambda: "There is one cube." in proc.screen_text(), 30), proc.screen_text()
    assert "what is in my scene" in proc.screen_text()
    # E1.3: the config came from hermes_config and passed the start-up check on its first request with tools
    assert len(checks) == 1 and checks[0][0] == unit and checks[0][2] is None, checks
    text = (home / "config.yaml").read_text()
    assert 'provider: "custom"' in text and f'base_url: "{stack.base}/engine/v1"' in text and "platform_toolsets:\n  cli:" in text
    assert f'url: "{stack.base}/engine/mcp/{unit}"' in text and '- "clarify"' in text.split("disabled_toolsets")[0]
    gw_token = re.search(r'^  api_key: "([^"]+)"$', text, re.M).group(1)
    bearer = re.search(r'^      Authorization: "Bearer ([^"]+)"$', text, re.M).group(1)
    assert gw_token.startswith("lwe_")
    assert text == HC.to_yaml(HC.render(CAP.ACTIVE, str(live["project"]), f"{stack.base}/engine/v1", gw_token, W.MODEL_ID,
                                        mcp_url=f"{stack.base}/engine/mcp/{unit}", mcp_headers={"Authorization": f"Bearer {bearer}"},
                                        instructions=SYSTEM_PROMPT)), \
        "the pane's config is exactly what hermes_config renders from the active board"
    assert (home / "managed").is_dir() and not any((home / "managed").iterdir())
    cache = home / "models_dev_cache.json"                               # if Hermes read models.dev, it read it from the gateway
    if cache.exists():
        assert list(json.loads(cache.read_text())) == ["lampway"]
    assert proc.alive(), "the server's shutdown ended no pane (law 5)"
    # E1.5: nothing left the machine; every attempt is a refusal row of the engine's proxy
    rows = live["strict"].log()
    assert not [r for r in rows if r.get("event") == "send"], rows
    print(f"\n[live pane] hosts the pane tried and the proxy refused: {sorted({r['provider'] for r in rows if r.get('via') == 'engine_proxy'})}")


# ---------------------------------------------------------------------------------------------------- E2: a switch reaches the running pane
def test_live_a_capability_switched_while_the_pane_runs_is_obeyed_from_the_next_turn_in_the_same_conversation(live):
    """The user switches ``terminal`` on in Choices and privacy while Lampway Agent's pane runs: the next turn's model request offers
    it and a command runs; switched off again, it is gone from the next request. The conversation is the same Hermes session
    throughout (no new pane, the first turn's words still in the request)."""
    import httpx
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        auth = {"Authorization": f"Bearer {island.fake.access_token}"}
        cid, _ = await chat(island, "Hello before the switch", unit)
        await island.ended(cid, timeout=240)
        async with httpx.AsyncClient(base_url=stack.base, headers=auth) as http:
            put = await http.put("/app/capabilities/terminal", json={"enabled": True})
            assert put.status_code == 200, put.text
            n_on = len(live["provider"].requests)
            cid2, _ = await chat(island, "TERM: run the echo", unit)
            await island.ended(cid2, timeout=240)
            on = (live["provider"].requests[n_on:], island.events(cid2))
            put = await http.put("/app/capabilities/terminal", json={"enabled": False})
            assert put.status_code == 200, put.text
            n_off = len(live["provider"].requests)
            cid3, _ = await chat(island, "TERM: try again", unit)
            await island.ended(cid3, timeout=240)
            off = (live["provider"].requests[n_off:], island.events(cid3))
        return on, off

    (on_reqs, on_events), (off_reqs, off_events) = run(live, scenario)

    def reach(reqs):
        r = next(r for r in reqs if r.tools)
        return {t.name for t in r.tools} | set(HC.deferred_listing([{"type": "function", "function": {"name": t.name, "description":
                                                                                                         t.description}} for t in r.tools])[0])
    assert "terminal" in reach(on_reqs), "switched on: offered from the next turn"
    assert "lampway-live-42" in (final_text(on_events) or ""), on_events
    assert "terminal" not in reach(off_reqs), "switched off: gone from the next turn"
    assert final_text(off_events) == "No terminal here."
    assert any("Hello before the switch" in m.text() for m in next(r for r in off_reqs if r.tools).messages), "the same conversation"
    assert len([r for r in live["cockpit"].list_sessions() if r.get("unit") == unit]) == 1, "the same pane"


# ---------------------------------------------------------------------------------------------------- R2: the archive from Hermes's sessions
def test_live_the_clients_archive_is_served_from_the_panes_hermes_session(live):
    """``agent.history_sync`` answers from the pane's real serve (``session.list``, ``session.history``): the turn's user text and
    the reply, in order, each record hashed as the client checks; acknowledged, nothing is sent again."""
    import hashlib
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid, _ = await chat(island, "SCENE: what is in my scene?", unit)
        await island.ended(cid, timeout=240)
        rid = await island.send("agent.history_sync", {"acknowledgements": [], "session_ids": [unit]})
        first = (await island.reply(rid))["result"]
        p = first["sessions"][0]
        ack = {"session_id": unit, "epoch": p["epoch"], "seq": p["records"][-1]["seq"]}
        rid = await island.send("agent.history_sync", {"acknowledgements": [ack], "session_ids": [unit]})
        return first, (await island.reply(rid))["result"]

    first, again = run(live, scenario)
    assert first["version"] == 1 and first["owner_id"] == "lampway-local" and len(first["sessions"]) == 1
    p = first["sessions"][0]
    rows = [(r["record"]["payload"]["role"], r["record"]["payload"]["text"]) for r in p["records"]]
    assert rows[0] == ("user", "SCENE: what is in my scene?") and rows[-1] == ("assistant", "There is one cube."), rows
    assert [r["seq"] for r in p["records"]] == list(range(1, len(rows) + 1))
    for r in p["records"]:
        raw = json.dumps(r["record"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        assert r["event_id"] == hashlib.sha256(raw).hexdigest()
    rec = pane_of(live, unit)
    assert {r["record"]["run_id"] for r in p["records"]} == {rec["stored_session_id"]}
    assert again["sessions"] == [], "acknowledged: nothing is sent again"
    assert (Path(rec["home"]) / "archive.json").is_file(), "the delivery state lives in the unit's home"


# ---------------------------------------------------------------------------------------------------- checkpoints: a rewind is Hermes's undo
def test_live_a_checkpoint_rewind_drops_the_undone_turns_from_the_panes_hermes_conversation(live):
    """The scene went back to before the second turn: serve's ``session.undo`` drops it from Hermes's session, so the next turn's
    model request carries the first turn's words and not the second's; the tip's bookmark cannot bring them back."""
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid1, _ = await chat(island, "Hello first turn", unit)
        await island.ended(cid1, timeout=240)
        cid2, _ = await chat(island, "Hello second turn", unit)
        await island.ended(cid2, timeout=240)
        _, rid = await island.command("agent.checkpoint.mark", {"session_id": unit, "request_id": "tip"})
        tip = (await island.reply(rid))["result"]
        _, rid = await island.command("agent.checkpoint.rewind", {"session_id": unit, "request_id": cid2})
        back = (await island.reply(rid))["result"]
        n = len(live["provider"].requests)
        cid3, _ = await chat(island, "Hello third turn", unit)
        await island.ended(cid3, timeout=240)
        _, rid = await island.command("agent.checkpoint.rewind", {"session_id": unit, "request_id": "tip"})
        forward = (await island.reply(rid))["result"]
        return tip, back, live["provider"].requests[n:], forward

    tip, back, reqs, forward = run(live, scenario)
    assert tip == {"ok": True, "has_conversation": True}
    assert back == {"ok": True, "has_conversation": True, "removed_turns": 1}, back
    words = "\n".join(m.text() for r in reqs if r.tools for m in r.messages)
    assert "Hello first turn" in words and "Hello third turn" in words and "Hello second turn" not in words
    assert forward["ok"] is False and forward["code"] == "rewind_forward", forward


# ---------------------------------------------------------------------------------------------------- the quick start's mock provider
def test_live_the_mock_provider_answers_hermes_through_the_gateway_and_reaches_the_scene(live):
    """``--provider mock`` (the quick start): behind the gateway it drives the pane's real Hermes with the tool names Hermes offers,
    so a question gets the scene's summary from Blender and a ``py:`` message runs its script in the scene."""
    from lampway_server.agent.providers.mock import MockProvider
    unit = f"scene-{uuid.uuid4().hex[:6]}"
    app = create_app(live["settings"], provider=MockProvider(), egress=live["strict"], cockpit=live["cockpit"])

    async def scenario(stack, island):
        cid, _ = await chat(island, "What is in my scene?", unit)
        await island.ended(cid, timeout=240)
        first = (island.events(cid), list(island.scripts))
        cid2, _ = await chat(island, "py: import bpy\n__RESULT__ = {'cubes': 1}", unit)
        await island.ended(cid2, timeout=240)
        return first, (island.events(cid2), list(island.scripts))

    (events, scripts), (events2, scripts2) = run(live, scenario, app=app)
    assert events[-1]["status"] == "completed" and "Scene summary from Blender" in (final_text(events) or ""), events
    assert scripts and scripts[0]["session_id"] == unit and "bpy.data.objects" in scripts[0]["script"]
    assert events2[-1]["status"] == "completed" and "Ran your script" in (final_text(events2) or ""), events2
    assert len(scripts2) == len(scripts) + 1 and "__RESULT__ = {'cubes': 1}" in scripts2[-1]["script"]


# ---------------------------------------------------------------------------------------------------- A2: questions, permissions, steer
def test_live_a_question_a_permission_and_a_steer_from_the_island(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"
    CAP_terminal = {"done": False}

    async def scenario(stack, island):
        CAP.ACTIVE.set("terminal", enabled=True, by="user")              # before the pane's config is written
        CAP_terminal["done"] = True
        target = Path(live["provider"].target)
        target.mkdir(parents=True, exist_ok=True)
        # a question: clarify -> the island's card -> agent.input -> the same Hermes turn goes on
        cid, _ = await chat(island, "ASK me about the table", unit)
        await island.ended(cid, timeout=240)
        q = next(e for e in island.events(cid) if e.get("interrupt_id"))
        cid2, _ = await island.command("agent.input", {"session_id": unit, "action": "respond", "text": "Round", "answers": ["Round"],
                                                       "interrupt_id": q["interrupt_id"]})
        await island.ended(cid2, timeout=120)
        asked = (q, island.events(cid2))
        # a permission: approval -> the island's permission card -> "once" -> the command runs
        cid3, _ = await chat(island, "APPROVE the cleanup", unit)
        await island.ended(cid3, timeout=120)
        card = next(e for e in island.events(cid3) if e.get("interrupt_id"))
        cid4, _ = await island.command("agent.input", {"session_id": unit, "action": "respond", "text": "once",
                                                       "interrupt_id": card["interrupt_id"]})
        await island.ended(cid4, timeout=120)
        approved = (card, island.events(cid4), target.exists())
        # a steer: a chat while the turn runs joins it
        live["provider"].release.clear()
        cid5, _ = await chat(island, "HOLD: make a chair", unit)
        await island.wait(lambda f: f.get("method") == "blender.execute_script", timeout=120)
        _, rid = await chat(island, "make it red", unit)
        joined = await island.reply(rid, timeout=60)
        await asyncio.sleep(1.0)
        live["provider"].release.set()
        await island.ended(cid5, timeout=180)
        return asked, approved, (joined, island.events(cid5))

    try:
        (q, after_q), (card, after_card, target_left), (joined, steered) = run(live, scenario)
    finally:
        live["provider"].release.set()
    # Hermes marks its first choice "(Recommended)" (measured); the island shows the choices as Hermes sent them
    assert q["input_type"] == "choice" and [a["value"].split(" (")[0] for a in q["actions"]] == ["Round", "Square"], q
    assert final_text(after_q) == "You chose Round." and after_q[-1]["status"] == "completed"
    assert card["input_type"] == "approval" and "rm -rf" in card["content"]["set"], card
    assert [a["value"] for a in card["actions"]][:1] == ["once"] and "deny" in [a["value"] for a in card["actions"]]
    assert target_left is False, "the user's 'once' let the command run"
    assert final_text(after_card)
    assert joined["result"] == {"state": "complete", "result": {"ok": True, "joined": True}}
    assert final_text(steered) == "Red it is." and steered[-1]["status"] == "completed", steered


# ---------------------------------------------------------------------------------------------------- A2: R3 and cancel
def test_live_rules_and_an_image_reach_the_pane_and_cancel_interrupts_it(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid, _ = await chat(island, "Model the chair with these rules.", unit,
                            rules={"version": 1, "global": [{"id": "g", "text": "Always use metric units.", "enabled": True}], "project": []},
                            content=[{"type": "text", "text": "Model the chair."},
                                     {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}],
                            attachment_names=["front.png"])
        await island.ended(cid, timeout=240)
        first = island.events(cid)
        live["provider"].release.clear()
        cid2, _ = await chat(island, "HOLD: a long one", unit)
        await island.wait(lambda f: f.get("method") == "agent.turn.started" and f["params"]["turn_id"] == cid2, timeout=60)
        await asyncio.sleep(2.0)
        _, rid = await island.command("agent.cancel", {"session_id": unit})
        reply = await island.reply(rid)
        live["provider"].release.set()
        await island.ended(cid2, timeout=120)
        return first, reply, island.events(cid2)

    try:
        first, reply, cancelled = run(live, scenario)
    finally:
        live["provider"].release.set()
    assert first[-1]["status"] == "completed"
    sent = "\n".join(m.text() for r in live["provider"].requests if r.tools for m in r.messages)
    assert "Always use metric units." in sent and "front.png" in sent
    home = Path(pane_of(live, unit)["home"])
    images = list((home / "images").glob("*")) if (home / "images").is_dir() else []
    assert images, "the image reached the pane's Hermes (image.attach_bytes)"
    assert reply["result"]["result"]["cancelled"] is True and cancelled[-1]["status"] == "cancelled"


# ---------------------------------------------------------------------------------------------------- A2/A3: a turn typed in the TUI
def test_live_a_turn_typed_in_the_tui_is_shown_in_the_island_and_its_tool_reaches_the_scene(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid, _ = await chat(island, "Hello", unit)
        await island.ended(cid, timeout=240)
        proc = live["herdr"].proc_for(pane_of(live, unit))
        assert wait_for(lambda: "Hello from the gateway." in proc.screen_text(), 30)
        before = len(island.scripts)
        proc.write("SCENE typed in the pane")
        await asyncio.sleep(0.5)
        proc.write("\r")
        started = await island.wait(lambda f: f.get("method") == "agent.turn.started" and f["params"].get("origin") == "pane", 120)
        await island.ended(started["params"]["turn_id"], timeout=120)
        return started["params"], island.events(started["params"]["turn_id"]), island.scripts[before:]

    started, events, scripts = run(live, scenario)
    assert started["user_text"] == "SCENE typed in the pane", started
    assert scripts and scripts[0]["session_id"] == unit, "a tool called in a pane-typed turn reached the scene tab's Blender"
    assert final_text(events) == "There is one cube." and events[-1]["status"] == "completed"


# ---------------------------------------------------------------------------------------------------- persistence
def test_live_the_island_leaving_stops_nothing_and_attach_replays_the_turn(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid0, _ = await chat(island, "Hello", unit)
        await island.ended(cid0, timeout=240)
        live["provider"].release.clear()
        cid, _ = await chat(island, "HOLD: then answer", unit)
        await island.wait(lambda f: f.get("method") == "blender.execute_script", timeout=120)
        last_seq = max(f["params"]["seq"] for f in island.frames if f.get("method") == "agent.turn.event" and f["params"]["turn_id"] == cid)
        await island.close()
        hub = stack.app.state.agent
        assert wait_for(lambda: getattr(hub.sessions[unit].current, "detached", False), 30)
        live["provider"].release.set()
        again = await Island(stack.base, live["settings"], on_script=lambda p: SCENE).connect()
        rid = await again.send("agent.attach", {"session_id": unit, "turn_id": cid, "after_seq": last_seq})
        await again.reply(rid)
        await again.ended(cid, timeout=180)
        events = again.events(cid)
        await again.close()
        return events

    try:
        events = run(live, scenario)
    finally:
        live["provider"].release.set()
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed", events
    assert final_text(events)


def test_live_quitting_the_tui_keeps_serve_and_only_enter_reopens_it(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def scenario(stack, island):
        cid, _ = await chat(island, "Hello", unit)
        await island.ended(cid, timeout=240)
        rec = pane_of(live, unit)
        proc = live["herdr"].proc_for(rec)
        assert wait_for(lambda: "Hello from the gateway." in proc.screen_text(), 30)
        mark = len(proc.text())
        proc.write("/quit")
        await asyncio.sleep(0.5)
        proc.write("\r")
        reopened_prompt = wait_for(lambda: "Press Enter to reopen Hermes" in proc.text()[mark:], 30)
        serve_pid = int((Path(rec["home"]) / "serve.pid").read_text())
        alive = Path(f"/proc/{serve_pid}").exists()
        # the backend runs on: the island still talks to it with no TUI attached
        cid2, _ = await chat(island, "Hello again", unit)
        await island.ended(cid2, timeout=120)
        mark2 = len(proc.text())
        await asyncio.sleep(1.0)
        nothing_yet = "Hello again" not in proc.text()[mark2:]
        proc.write("\r")                                                  # the user's Enter
        back = wait_for(lambda: "Hello again" in proc.screen_text(), 60)
        return reopened_prompt, alive, island.events(cid2), nothing_yet, back

    prompt, alive, events, nothing_yet, back = run(live, scenario)
    assert prompt, "the wrapper says how to reopen"
    assert alive, "serve outlived the TUI"
    assert final_text(events) == "Hello from the gateway."
    assert nothing_yet, "the TUI did not come back by itself"
    assert back, "Enter reopened the TUI on the same session, history intact"


def test_live_a_server_restart_re_adopts_the_pane_and_the_conversation_goes_on(live):
    unit = f"scene-{uuid.uuid4().hex[:6]}"

    async def first(stack, island):
        cid, _ = await chat(island, "Hello before the restart", unit)
        await island.ended(cid, timeout=240)
        return island.events(cid)

    before = run(live, first)
    assert before[-1]["status"] == "completed"
    rec = pane_of(live, unit)
    assert live["herdr"].proc_for(rec).alive(), "the pane outlived the server"
    runs_before = len([c for c in live["herdr"].calls if c["args"][:2] == ["pane", "run"]])
    asked_before = len(live["provider"].requests)

    async def second(stack, island):
        cid, _ = await chat(island, "SCENE after the restart", unit)
        await island.ended(cid, timeout=240)
        return island.events(cid)

    after = run(live, second)                                             # a new server process's app on the same state and port
    assert final_text(after) == "There is one cube." and after[-1]["status"] == "completed", after
    assert len([c for c in live["herdr"].calls if c["args"][:2] == ["pane", "run"]]) == runs_before, "no new pane: re-adopted"
    later = [r for r in live["provider"].requests[asked_before:] if r.tools]
    assert later and any("Hello before the restart" in m.text() for m in later[0].messages), "the same Hermes conversation"


# ---------------------------------------------------------------------------------------------------- on a REAL herdr server
@needs_herdr
def test_live_on_a_real_herdr_server_the_pane_runs_the_tui_and_survives_a_server_restart(settings, tmp_path, monkeypatch):
    """The same path with nothing played: Lampway's own herdr server (started here as the user's cockpit Start would), the
    ``lampway_hermes`` pane opened by the island's first chat in its unit's tab, the wrapper typed into the pane's shell by
    ``pane run``, ``hermes serve`` and the TUI in it; then a server restart re-adopts the pane (herdr's own ``process-info``)."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(ENGINES))           # found, so in the seat: no switch (spec A5)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(project))
    monkeypatch.setenv("LAMPWAY_HERMES_TUI_DIR", str(TUI))
    monkeypatch.setenv("LAMPWAY_NODE", NODE)
    settings.port = free_port()
    root = short_root("lwm1-")
    cockpit = H.Cockpit(root, project_root=str(project))
    provider = LiveProvider()
    unit = f"scene-{uuid.uuid4().hex[:6]}"
    live = {"settings": settings}
    try:
        cockpit.ensure_server()
        app = create_app(settings, provider=provider, egress=EG.Egress(tmp_path / "strict"), cockpit=cockpit)

        async def first(stack, island):
            cid, _ = await chat(island, "SCENE: what is in my scene?", unit)
            await island.ended(cid, timeout=240)
            return island.events(cid)
        events = run(live, first, app=app)
        assert final_text(events) == "There is one cube." and events[-1]["status"] == "completed", events
        rec = next(r for r in cockpit.list_sessions() if r.get("unit") == unit)
        assert rec["agent"] == "lampway_hermes" and rec["role"] == "main" and rec["stored_session_id"]
        assert wait_for(lambda: "There is one cube." in cockpit.read_screen(rec["id"], 120), 30), cockpit.read_screen(rec["id"], 120)
        alive, why = cockpit.pane_alive(rec["id"])
        assert alive, why
        # a new server on the same state: reconcile re-adopts the pane through herdr's own process-info, and the turn goes on
        again = create_app(settings, provider=provider, egress=EG.Egress(tmp_path / "strict2"), cockpit=cockpit)

        async def second(stack, island):
            cid, _ = await chat(island, "SCENE after the restart", unit)
            await island.ended(cid, timeout=240)
            return island.events(cid)
        after = run(live, second, app=again)
        assert final_text(after) == "There is one cube." and after[-1]["status"] == "completed", after
        assert [r["id"] for r in cockpit.list_sessions() if r.get("unit") == unit] == [rec["id"]], "re-adopted, not reopened"
        print(f"\n[real herdr] pane {rec['pane_id']} in tab {rec['tab_id']}; serve on port {rec['port']}")
    finally:
        homes = [r.get("home") for r in cockpit.list_sessions() if r.get("home")]
        try:
            L.stop_server(root, confirmed=True)                          # ends every pane: each wrapper ends its serve
        finally:
            left = []
            for home in homes:
                pid_file = Path(home) / "serve.pid"
                if pid_file.is_file():
                    pid = int(pid_file.read_text())
                    if not wait_for(lambda: not Path(f"/proc/{pid}").exists() or
                                    Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] == "Z", 20):
                        left.append(pid)
                        os.killpg(pid, 9)
            shutil.rmtree(root, ignore_errors=True)
            assert left == [], f"a serve outlived its pane: {left}"
