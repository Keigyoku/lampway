# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B2 (docs/reports/agent-modes-spec.md), the server side: a harness pane bound to a scene tab.

- The session record carries {harness, native_id, scene_session_id, project_root, mcp_config_path} beside herdr's ids.
- A bound pane gets its own MCP config, written 0600 under the Lampway root, pointing at Lampway's MCP launcher with
  LAMPWAY_BOUND_SESSION=<scene_session_id>; the harness is pointed at it on its own command line or environment.
- Unbinding (the scene tab closed) never touches the pane (law 5): the pane is listed unbound and can be re-bound.
herdr is faked; nothing is started."""
import json
import os
import stat
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .test_byoa_egress import FakeHerdr

LAUNCHER = "/opt/lw/connector/lampway-mcp"


@pytest.fixture
def herdr(monkeypatch):
    monkeypatch.setenv("LAMPWAY_MCP_LAUNCHER", LAUNCHER)
    fake = FakeHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


def _start(fake):
    return next(c["args"] for c in fake.calls if c["args"][:2] == ["agent", "start"])


def _envs(fake):
    made = next(c["args"] for c in fake.calls if c["args"][:2] in (["workspace", "create"], ["tab", "create"]))
    return [made[i + 1] for i, a in enumerate(made) if a == "--env"]


def test_a_bound_claude_pane_has_its_own_mcp_config_pinned_to_the_scene_tab(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    rec = c.create_session("claude", "Chest fit audit", str(tmp_path), by="user", scene_session_id="scene-1")
    assert {k: rec[k] for k in ("harness", "scene_session_id", "project_root")} == {"harness": "claude", "scene_session_id": "scene-1", "project_root": str(tmp_path)}
    assert rec["native_id"] and rec["id"]
    cfg = Path(rec["mcp_config_path"])
    assert cfg.is_file() and str(cfg).startswith(str(tmp_path / "herdr" / "panes" / rec["id"]))
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600 and stat.S_IMODE(cfg.parent.stat().st_mode) == 0o700
    entry = json.loads(cfg.read_text())["mcpServers"]["lampway"]
    assert entry == {"command": LAUNCHER, "args": [], "env": {"LAMPWAY_BOUND_SESSION": "scene-1"}}
    args = _start(herdr)
    assert args[args.index("--mcp-config") + 1] == str(cfg)


def test_a_bound_opencode_pane_names_its_config_in_its_environment(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("opencode", "Chest fit audit", str(tmp_path), by="user", scene_session_id="scene-1")
    assert f"OPENCODE_CONFIG={rec['mcp_config_path']}" in _envs(herdr)
    body = json.loads(Path(rec["mcp_config_path"]).read_text())
    assert body["mcp"]["lampway"]["environment"] == {"LAMPWAY_BOUND_SESSION": "scene-1"} and body["mcp"]["lampway"]["command"] == [LAUNCHER]


def test_an_unbound_pane_writes_nothing_and_says_so_in_its_record(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("codex", "Boots seed read", str(tmp_path), by="user")
    assert rec["harness"] == "codex" and rec["scene_session_id"] is None and rec["mcp_config_path"] is None
    assert not (tmp_path / "herdr" / "panes").exists()
    assert _start(herdr)[-1] == "--no-alt-screen"
    shell = c.create_session("shell", "Scratch shell", str(tmp_path), by="user")
    assert shell["harness"] is None


def test_unbinding_never_touches_the_pane_and_a_pane_can_be_rebound(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("claude", "Chest fit audit", str(tmp_path), by="user", scene_session_id="scene-1")
    before = len(herdr.calls)
    out = c.unbind(rec["id"])
    assert len(herdr.calls) == before                                                  # not one herdr command: the pane runs on
    again = c._get(rec["id"])
    assert again["state"] == "live" and again["scene_session_id"] is None and out["scene_session_id"] is None
    assert json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway"]["env"] == {"LAMPWAY_BOUND_SESSION": ""}
    assert c.find_by_scene("scene-1") == []
    c.bind(rec["id"], "scene-2")
    assert len(herdr.calls) == before
    assert [s["id"] for s in c.find_by_scene("scene-2")] == [rec["id"]]
    assert json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway"]["env"] == {"LAMPWAY_BOUND_SESSION": "scene-2"}


def test_only_a_harness_pane_can_be_bound(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    sh = c.create_session("shell", "Scratch shell", str(tmp_path), by="user")
    with pytest.raises(H.CockpitError, match="harness"):
        c.bind(sh["id"], "scene-1")


def test_an_ended_pane_keeps_its_binding_and_native_id_for_a_resume(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("claude", "Chest fit audit", str(tmp_path), by="user", scene_session_id="scene-1")
    c.reconcile()                                                                      # the fake server has no panes: the record ends
    ended = c._get(rec["id"])
    assert ended["state"] == "ended" and ended["scene_session_id"] == "scene-1" and ended["native_id"] == rec["native_id"]
    assert [s["id"] for s in c.find_by_scene("scene-1")] == [rec["id"]]


def test_a_pane_file_outside_the_lampway_root_is_refused(tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(H.CockpitError, match="Lampway root"):
        c._write_pane_files({str(tmp_path / "elsewhere" / "mcp.json"): "{}"})
    assert not (tmp_path / "elsewhere").exists()


def test_the_binding_route_is_the_users_and_the_create_route_takes_the_scene(settings, provider, herdr, tmp_path, monkeypatch):
    from lampway_server.app import create_app
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    app = create_app(settings, provider=provider, cockpit=H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path)))
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        from .fake_client import FakeMixarClient
        client = FakeMixarClient(http, password=settings.user_password)
        client.login()
        h = client.rest_headers()
        rec = http.post("/app/workbench/sessions", headers=h, json={"agent": "claude", "name": "Chest fit audit", "cwd": str(tmp_path), "scene_session_id": "scene-1"}).json()
        assert rec["scene_session_id"] == "scene-1" and os.path.isfile(rec["mcp_config_path"])
        r = http.post(f"/app/workbench/sessions/{rec['id']}/binding", headers={**h, "X-Lampway-Origin": "agent"}, json={"scene_session_id": "scene-9"})
        assert r.status_code == 403
        r = http.post(f"/app/workbench/sessions/{rec['id']}/binding", headers=h, json={"scene_session_id": None})
        assert r.status_code == 200 and r.json()["scene_session_id"] is None
        r = http.post(f"/app/workbench/sessions/{rec['id']}/binding", headers=h, json={"scene_session_id": "scene-2"})
        assert r.status_code == 200 and r.json()["scene_session_id"] == "scene-2"
