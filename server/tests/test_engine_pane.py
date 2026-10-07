# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1's pane (docs/reports/agent-modes-spec.md A1): the ``lampway_hermes`` adapter, the pane wrapper, the server's half that
prepares a pane's home and re-adopts it, and the unit's MCP endpoint (A3). No Hermes runs here: herdr is played, the engine build
is a stand-in, and the wrapper's loop runs against a stand-in ``hermes``. The real pinned serve, wrapper and TUI are
``test_engine_pane_live.py``."""

import asyncio
import json
import shlex
import os
import stat
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from lampway_server import egress as EG
from lampway_server.app import create_app
from lampway_server.engine import gateway as GW
from lampway_server.engine import hermes_pane as WP
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .herdr_support import PaneHerdr
from .mode1_support import fake_engine, mcp_entry, units_for


# ---------------------------------------------------------------------------------------------------- the adapter
def test_lampway_hermes_is_built_and_its_argv_names_only_the_wrapper_and_the_home(tmp_path):
    ad = HN.get("lampway_hermes")
    assert ad.id == "lampway_hermes" and "lampway_hermes" in HN.LAMPWAY_ADAPTERS and HN.is_lampway("lampway_hermes")
    assert "lampway_hermes" not in HN.ids() and "lampway_hermes" not in [r["id"] for r in HN.listing()], \
        "Lampway's own agent is never in the user's Your agent list"
    argv = ad.launch(HN.PaneSpec(cwd=str(tmp_path), home=str(tmp_path / "h")), task="Model the boots, secret-free")
    assert argv == [sys.executable, str(Path(WP.__file__)), "--home", str(tmp_path / "h")]
    assert ad.resume("anything", HN.PaneSpec(cwd=str(tmp_path), home=str(tmp_path / "h"))) == argv, "the wrapper resumes from its home"
    assert ad.route is None, "Mode 1 is Lampway's own engine: no byoa route (its doors are the gateway and the egress proxy)"
    assert ad.detect() is None and ad.observe({}) is None and ad.process_match == "hermes_pane.py"
    with pytest.raises(ValueError, match="home"):
        ad.launch(HN.PaneSpec(cwd=str(tmp_path)))
    assert "byoa:lampway_hermes" not in EG.ROUTES


# ---------------------------------------------------------------------------------------------------- the cockpit and the server's half
@pytest.fixture
def mode1(tmp_path, monkeypatch, settings):
    herdr = PaneHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    (tmp_path / "proj").mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    cockpit.pane_mcp_url = "http://127.0.0.1:8787/api/v1/mcp/pane"
    app = create_app(settings, cockpit=cockpit)              # the active Capabilities board the config is rendered from
    registry = app.state.engine_tokens
    engine = fake_engine(tmp_path / "engines")
    units = units_for(cockpit, settings.state_dir, registry, engine=engine)
    cockpit.mode1 = units
    return SimpleNamespace(cockpit=cockpit, herdr=herdr, units=units, registry=registry, engine=engine, app=app, state=settings.state_dir)


def test_without_the_engine_lampways_pane_is_refused_with_help_and_herdr_is_never_asked(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(L, "run", lambda root, args, **k: calls.append(args) or "")
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(H.CockpitError, match="scripts/lampway/engine_env.py and restart Lampway"):
        c.create_session("lampway_hermes", "Lampway for a scene tab", str(tmp_path), by="user", unit="scene-1")
    assert calls == [] and c.list_sessions() == []


def test_a_units_main_pane_is_prepared_before_herdr_is_asked_and_its_record_keeps_no_secret(mode1):
    rec = mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for Kitchen", str(mode1.cockpit.project_root), by="user",
                                       unit="scene-1", unit_label="Kitchen", display_agent="Lampway · Kitchen")
    home = Path(rec["home"])
    assert home == Path(mode1.state) / "agent" / "hermes" / "scene-1"
    assert (rec["unit"], rec["role"], rec["scene_session_id"], rec["agent"]) == ("scene-1", "main", None, "lampway_hermes")
    assert rec["port"] > 0 and rec["token_file"] == str(home / "serve.token") and rec["stored_session_id"] is None
    token = (home / "serve.token").read_text()
    for f in ("serve.token", "pane.json", "config.yaml"):
        assert stat.S_IMODE((home / f).stat().st_mode) == 0o600, f
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    run = next(c["args"] for c in mode1.herdr.calls if c["args"][:2] == ["pane", "run"])
    # measured on herdr 0.9.3: `pane run` types its arguments joined by spaces, unquoted; one shell-quoted command survives a space
    assert run[3:] == [shlex.join([sys.executable, str(Path(WP.__file__)), "--home", str(home)])]
    made = mode1.herdr.made()
    assert made and all(token not in " ".join(c["args"]) for c in mode1.herdr.calls), "the serve token is in no herdr argv"
    assert token not in mode1.cockpit.path.read_text() and token not in (home / "pane.json").read_text()
    spec = json.loads((home / "pane.json").read_text())
    assert spec["hermes"] == str(Path(mode1.engine["dir"]) / "env/bin/hermes") and spec["port"] == rec["port"]
    assert spec["tui_dir"] == str(Path(mode1.engine["dir"]) / "src/ui-tui") and spec["cwd"] == str(mode1.cockpit.project_root)
    url, headers = mcp_entry(home)
    assert url == "http://127.0.0.1:8787/engine/mcp/scene-1"
    bearer = headers["Authorization"].removeprefix("Bearer ")
    assert GW.Registry.digest(bearer) == rec["mcp_token_sha256"] and mode1.units.check_mcp("scene-1", bearer)
    assert not mode1.units.check_mcp("scene-1", "a-guess") and not mode1.units.check_mcp("scene-2", bearer)
    gw_token = next(ln.split('"')[1] for ln in (home / "config.yaml").read_text().splitlines() if ln.startswith("  api_key:"))
    assert mode1.registry.session_for(gw_token) == "scene-1" and GW.Registry.digest(gw_token) == rec["gateway_token_sha256"]
    assert gw_token not in mode1.cockpit.path.read_text()
    assert mode1.units.opened_records and mode1.units.opened_records[-1]["id"] == rec["id"], "the server creates its session next"
    assert mode1.herdr.metadata[rec["pane_id"]]["display_agent"] == "Lampway · Kitchen"
    assert mode1.app.state.agent.byoa.mode_of("scene-1") == "runtime", "Lampway's own pane never puts the tab in Your agent mode"


def test_the_main_pane_starts_with_no_byoa_route_and_its_start_is_no_egress(mode1, tmp_path):
    strict = EG.Egress(tmp_path / "strict")
    prev = EG.ACTIVE
    EG.set_active(strict)
    try:
        mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for a tab", str(mode1.cockpit.project_root), by="user", unit="u1")
    finally:
        EG.set_active(prev)
    assert not [r for r in strict.log() if str(r.get("route", "")).startswith("byoa:")], "no byoa route is asked"


def test_a_reconcile_after_a_restart_re_adopts_the_pane_and_its_tokens_by_digest(mode1):
    rec = mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for a tab", str(mode1.cockpit.project_root), by="user", unit="u1")
    home = Path(rec["home"])
    gw_token = next(ln.split('"')[1] for ln in (home / "config.yaml").read_text().splitlines() if ln.startswith("  api_key:"))
    bearer = mcp_entry(home)[1]["Authorization"].removeprefix("Bearer ")
    out = mode1.cockpit.reconcile()
    assert rec["id"] in out["adopted"], "the wrapper is the pane's foreground process"
    fresh = GW.Registry()                                                  # the restarted server knows no token yet
    units = units_for(mode1.cockpit, mode1.state, fresh, engine=mode1.engine)
    assert fresh.session_for(gw_token) is None and not units.check_mcp("u1", bearer)
    adopted = units.adopt()
    assert [r["id"] for r in adopted] == [rec["id"]]
    assert fresh.session_for(gw_token) == "u1" and units.check_mcp("u1", bearer), "the pane thinks and calls tools on"
    assert units.known("u1").port == rec["port"]


def test_no_tui_or_no_node_is_refused_with_what_to_do_and_nothing_is_fetched(mode1, tmp_path):
    (Path(mode1.engine["dir"]) / "src/ui-tui/dist/entry.js").unlink()
    with pytest.raises(H.CockpitError, match="engine_env.py"):
        mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for a tab", str(mode1.cockpit.project_root), by="user", unit="u1")
    (Path(mode1.engine["dir"]) / "src/ui-tui/dist/entry.js").write_text("//")
    mode1.units.environ = {"PATH": str(tmp_path / "empty")}
    with pytest.raises(H.CockpitError, match="LAMPWAY_NODE"):
        mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for a tab", str(mode1.cockpit.project_root), by="user", unit="u1")
    assert not [c for c in mode1.herdr.calls if c["args"][:2] == ["pane", "run"]]


def test_only_a_mode1_panes_own_fields_change_through_update_mode1(mode1):
    rec = mode1.cockpit.create_session("lampway_hermes", "Lampway Agent for a tab", str(mode1.cockpit.project_root), by="user", unit="u1")
    assert mode1.cockpit.update_mode1(rec["id"], stored_session_id="20261007_x")["stored_session_id"] == "20261007_x"
    with pytest.raises(H.CockpitError, match="fields"):
        mode1.cockpit.update_mode1(rec["id"], bypass=True)


# ---------------------------------------------------------------------------------------------------- the wrapper
def spec(tmp_path, **kw):
    return {"hermes": "/engine/env/bin/hermes", "port": 4321, "cwd": str(tmp_path / "proj"), "tui_dir": "/engine/src/ui-tui",
            "node": "/opt/node/bin/node", "env": {"HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1"}, **kw}


def test_the_wrapper_gives_serve_its_token_only_in_its_environment_and_keeps_every_secret_out(tmp_path):
    environ = {"PATH": "/usr/bin", "OPENROUTER_API_KEY": "sk-or-v1-FAKE", "GITHUB_TOKEN": "ghp_FAKE", "HERMES_HOME": "~/.hermes",
               "HERMES_DESKTOP": "1", "HTTPS_PROXY": "http://corp:3128", "LAMPWAY_JWT_SECRET": "x", "LANG": "C.UTF-8"}
    home = tmp_path / "h"
    env = WP.serve_env(spec(tmp_path), home, "serve-tok", environ)
    assert env["HERMES_DASHBOARD_SESSION_TOKEN"] == "serve-tok"
    assert not [k for k in env if k.endswith(("_KEY", "_SECRET")) or k == "GITHUB_TOKEN"]
    assert env["HERMES_HOME"] == str(home) and env["HOME"] == str(home / "home") and env["HERMES_MANAGED_DIR"] == str(home / "managed")
    assert env["HERMES_GATEWAY_LOCK_DIR"] == str(home / "locks"), "one serve per unit, not one per OS user"
    assert env["HERMES_TUI_WS_ORPHAN_REAP_GRACE_S"] == "0" and "HERMES_DESKTOP" not in env
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9" and env["NO_PROXY"] == "127.0.0.1" and env["LANG"] == "C.UTF-8"
    tui = WP.tui_env(spec(tmp_path), home, "serve-tok", environ)
    assert "HERMES_DASHBOARD_SESSION_TOKEN" not in tui
    assert tui["HERMES_TUI_GATEWAY_URL"] == "ws://127.0.0.1:4321/api/ws?token=serve-tok"
    assert tui["HERMES_SKIP_NODE_BOOTSTRAP"] == "1" and tui["HERMES_NODE"] == "/opt/node/bin/node", "Node is never fetched"
    assert tui["PATH"].split(os.pathsep)[0] == "/opt/node/bin" and tui["HERMES_TUI_DIR"] == "/engine/src/ui-tui"
    assert WP.serve_argv(spec(tmp_path)) == ["/engine/env/bin/hermes", "serve", "--host", "127.0.0.1", "--port", "4321"]
    assert WP.tui_argv(spec(tmp_path), "20261007_a") == ["/engine/env/bin/hermes", "--tui", "--resume", "20261007_a"]
    assert "serve-tok" not in " ".join(WP.serve_argv(spec(tmp_path)) + WP.tui_argv(spec(tmp_path), "x"))
    # measured live: serve folds a GUI's `project` toolset into every session; the pinned list (choices + Lampway's server) drops it
    pinned = WP.serve_env(spec(tmp_path, toolsets=["vision", "clarify", "lampway"]), home, "serve-tok", {**environ, "HERMES_TUI_TOOLSETS": "all"})
    assert pinned["HERMES_TUI_TOOLSETS"] == "vision,clarify,lampway"


STAND_IN = r'''#!/usr/bin/env python3
"""A stand-in hermes: `serve` answers HTTP on its port; `--tui` records itself and exits (or stops serve first, as the user's own
`hermes serve --stop` would)."""
import http.server, json, os, signal, sys
from pathlib import Path
log = Path(os.environ["STAND_IN_LOG"])
args = sys.argv[1:]
def note(**kw):
    with log.open("a") as fh:
        fh.write(json.dumps(kw) + "\n")
if args[:1] == ["serve"]:
    port = int(args[args.index("--port") + 1])
    note(serve=os.getpid(), token=os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN"))
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(426); self.send_header("Content-Length", "0"); self.end_headers()
    http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
elif "--tui" in args:
    note(tui=args, url=os.environ.get("HERMES_TUI_GATEWAY_URL"), token=os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN"))
    stop = Path(os.environ["STAND_IN_LOG"] + ".stop")
    if stop.exists():
        stop.unlink()
        os.kill(int(Path(os.environ["HERMES_HOME"], "serve.pid").read_text()), signal.SIGTERM)
'''


class Keys:
    """The pane's keyboard: a line per Enter, end of input when the pane goes."""

    def __init__(self):
        self.r, self.w = os.pipe()
        self.inp = os.fdopen(self.r, "r")

    def enter(self):
        os.write(self.w, b"\n")

    def close(self):
        os.close(self.w)


def notes(log):
    return [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []


def wait(cond, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_the_wrapper_keeps_serve_when_the_tui_exits_and_reopens_it_only_on_enter(tmp_path, monkeypatch):
    from .serve_support import free_port
    exe = tmp_path / "hermes"
    exe.write_text(STAND_IN)
    exe.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    (home / "serve.token").write_text("serve-tok")
    (home / "session.json").write_text(json.dumps({"stored_session_id": "20261007_abc"}))
    (home / "pane.json").write_text(json.dumps({**spec(tmp_path, hermes=str(exe), port=free_port(), node=sys.executable, session_wait_s=5),
                                                "cwd": str(tmp_path)}))
    log = tmp_path / "stand-in.log"
    keys, out = Keys(), []

    class Out:
        def write(self, s):
            out.append(s)

        def flush(self):
            pass
    environ = {"PATH": os.environ["PATH"], "STAND_IN_LOG": str(log)}
    pane = WP.Pane(home, environ=environ, out=Out(), inp=keys.inp)
    result = {}
    monkeypatch.setattr(WP, "node_problem", lambda node: "")             # the version probe is its own test
    try:
        t = threading.Thread(target=lambda: result.update(code=pane.run()), daemon=True)
        t.start()
        assert wait(lambda: any("Press Enter to reopen" in s for s in out)), out
        serves, tuis = [n for n in notes(log) if "serve" in n], [n for n in notes(log) if "tui" in n]
        assert len(serves) == 1 and serves[0]["token"] == "serve-tok", "serve got its token in its environment"
        assert len(tuis) == 1 and tuis[0]["tui"] == ["--tui", "--resume", "20261007_abc"] and tuis[0]["token"] is None
        assert tuis[0]["url"].endswith("/api/ws?token=serve-tok")
        time.sleep(0.5)
        assert len([n for n in notes(log) if "tui" in n]) == 1, "nothing reopens without the user's Enter"
        assert pane.serve_alive(), "serve keeps running when the TUI exits"
        keys.enter()
        assert wait(lambda: len([n for n in notes(log) if "tui" in n]) == 2)
        assert len([n for n in notes(log) if "serve" in n]) == 1, "the same serve"
        Path(str(log) + ".stop").write_text("")                           # the user's own `hermes serve --stop`
        keys.enter()
        assert wait(lambda: any("backend stopped" in s for s in out)), out
        time.sleep(0.3)
        assert len([n for n in notes(log) if "serve" in n]) == 1, "a stopped serve is not restarted without a click"
        keys.enter()
        assert wait(lambda: len([n for n in notes(log) if "serve" in n]) == 2), "Enter starts it again"
        assert wait(lambda: sum(1 for s in out if "Press Enter to reopen" in s) >= 2)
        keys.close()                                                     # end of input: the pane is gone; the wrapper ends
        t.join(10)
        assert not t.is_alive() and result.get("code") == 0
    finally:
        pane.stop_serve()                                                # what main() does on the way out, by its recorded group
    assert pane.serve is None


def test_node_is_found_or_refused_with_help(tmp_path):
    assert "LAMPWAY_NODE" in WP.node_problem(str(tmp_path / "no-node"))
    old = tmp_path / "node"
    old.write_text("#!/bin/sh\necho v20.11.0\n")
    old.chmod(0o755)
    assert "22" in WP.node_problem(str(old)) and "v20.11.0" in WP.node_problem(str(old))
    new = tmp_path / "node22"
    new.write_text("#!/bin/sh\necho v22.22.0\n")
    new.chmod(0o755)
    assert WP.node_problem(str(new)) == ""


# ---------------------------------------------------------------------------------------------------- the unit's MCP endpoint (A3)
class _Front:
    def __init__(self):
        self.calls = []
        from lampway_server.engine.front import HermesFront
        self.tool_specs = HermesFront.tool_specs.__get__(self)

    def session_for_token(self, unit, token):
        return unit if (unit, token) == ("u1", "right") else None

    async def call_tool(self, unit, name, arguments):
        self.calls.append((unit, name, arguments))
        return "pong", False


def test_the_units_endpoint_needs_its_bearer_and_offers_the_users_tools_without_ask_user(fake, http):
    front = _Front()
    http.app.state.agent.engine = front
    rpc = lambda body, token="right", unit="u1": http.post(f"/engine/mcp/{unit}", json=body, headers={"Authorization": f"Bearer {token}"})  # noqa: E731
    assert rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, token="wrong").status_code == 401
    assert rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, unit="u2").status_code == 401
    init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}).json()
    assert init["result"]["serverInfo"]["name"] == "lampway"
    names = {t["name"] for t in rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]}
    assert {"run_blender_python", "scene_summary", "lampway_capabilities"} <= names
    assert "ask_user" not in names, "the island's questions are Hermes's own clarify (A2)"
    assert "swarm_start" not in names                                    # the swarm is off until the user switches it on (E2)
    off = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "swarm_start", "arguments": {}}}).json()
    assert off["result"]["isError"] and "capability" in off["result"]["content"][0]["text"] and front.calls == []
    ok = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "scene_summary", "arguments": {}}}).json()
    assert ok["result"] == {"content": [{"type": "text", "text": "pong"}], "isError": False}
    assert front.calls == [("u1", "scene_summary", {})]


def test_a_closed_socket_detaches_an_engine_turn_and_still_cancels_a_built_in_one(settings, provider):
    """The hub names the pane's running turn as a survivor of its client's socket (ws.py then leaves it running) and marks it
    detached; with no engine in the seat the turn is cancelled as before."""
    from lampway_server.agent.turns import Session, Turn

    hub = create_app(settings, provider=provider).state.agent

    async def go(engine_running):
        hub.engine = SimpleNamespace(is_running=lambda sid: engine_running) if engine_running is not None else None
        sock = object()
        session = Session("s1")
        turn = Turn("s1", "t1", "r1")
        turn.task = asyncio.get_running_loop().create_task(asyncio.sleep(30))
        turn.socket = sock
        session.current = turn
        hub.sessions["s1"] = session
        survivors = hub.socket_closed(sock)
        await asyncio.sleep(0)
        out = (survivors, turn.detached, turn.task.cancelled())
        turn.task.cancel()
        return out, turn.task

    (survivors, detached, cancelled), task = asyncio.run(go(True))
    assert survivors == {task} and detached and not cancelled
    (survivors, detached, cancelled), _ = asyncio.run(go(None))
    assert survivors == set() and not detached and cancelled
