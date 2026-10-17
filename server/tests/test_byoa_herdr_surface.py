# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B6 (docs/reports/agent-modes-spec.md): the fixes the herdr surface needs before any harness is wired.

- The workbench input route decides who is typing from the caller (an agent-declared request, a cross-origin request or an
  agent/MCP token is an agent send), never from ``body.by``.
- ``AgentOps.workbench_open`` applies the same "your own agents in panes" switch as the ``wb_create`` route.
- ``lampway_workbench`` is never offered over MCP, so one BYOA agent cannot drive another pane.
No herdr binary is needed: the cockpit is a recording fake."""
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.auth import mint_jwt


class RecordingCockpit:
    """Only what the app touches: a root, the registry, the reconcile at start, and send_input (which records who typed)."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.sends = []

    def list_sessions(self):
        return []

    def reconcile(self):
        return {"server": "not_running"}

    def send_input(self, sid, text, submit=True, by="agent", user_typed_at=None):
        self.sends.append({"sid": sid, "text": text, "by": by})


@pytest.fixture
def wb(settings, provider, tmp_path):
    cp = RecordingCockpit(tmp_path / "herdr")
    app = create_app(settings, provider=provider, cockpit=cp)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake.rest_headers(), cp, settings


def _send(http, headers, body):
    return http.post("/app/workbench/sessions/s1/input", headers=headers, json=body)


def test_a_body_claiming_the_user_from_an_agent_declared_request_is_an_agent_send(wb):
    http, h, cp, _ = wb
    assert _send(http, {**h, "X-Lampway-Origin": "agent"}, {"text": "rm -rf", "by": "user"}).status_code == 200
    assert cp.sends[-1]["by"] == "agent"
    assert _send(http, {**h, "X-Mixar-Job-Origin": "agent"}, {"text": "x", "by": "user"}).status_code == 200
    assert cp.sends[-1]["by"] == "agent"


def test_a_cross_origin_request_is_an_agent_send_whatever_its_body_says(wb):
    http, h, cp, _ = wb
    _send(http, {**h, "Origin": "https://evil.example"}, {"text": "x", "by": "user"})
    assert cp.sends[-1]["by"] == "agent"


def test_an_agent_or_mcp_token_is_an_agent_send(wb):
    http, h, cp, settings = wb
    for claim in ({"origin": "agent"}, {"origin": "mcp"}, {"aud": "mcp"}):
        tok = mint_jwt(settings.jwt_secret, {"sub": settings.user_email, "iat": int(time.time()), "exp": int(time.time()) + 600, **claim})
        r = _send(http, {**h, "Authorization": f"Bearer {tok}"}, {"text": "x", "by": "user"})
        assert r.status_code == 200 and cp.sends[-1]["by"] == "agent", claim


def test_the_users_own_client_is_the_user_and_the_body_field_decides_nothing(wb):
    http, h, cp, _ = wb
    _send(http, h, {"text": "hello", "by": "user"})
    assert cp.sends[-1]["by"] == "user"
    _send(http, h, {"text": "hello", "by": "agent"})                       # the body field is ignored both ways: the caller decides
    assert cp.sends[-1]["by"] == "user"
    _send(http, {**h, "Origin": "http://127.0.0.1:8787"}, {"text": "hello"})  # the cockpit page itself (same origin)
    assert cp.sends[-1]["by"] == "user"


# ---------------------------------------------------------------------------------------------------- AgentOps.workbench_open
class OpenCockpit:
    def __init__(self):
        self.opened = []

    def list_sessions(self):
        return []

    def create_session(self, agent, name, cwd, task="", effort=None, bypass=False, resume_id=None, command=None, by="user", project_root=None):
        self.opened.append((agent, name, by))
        return {"id": "new", "name": name}


@pytest.mark.anyio
async def test_the_agent_open_path_refuses_a_harness_while_byoa_is_off(tmp_path, monkeypatch):
    from lampway_server.ops import registry as REG
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    cp = OpenCockpit()
    ops = REG.AgentOps(cp, tmp_path / "ops", cwd=str(tmp_path), switch_dir=tmp_path / "state")
    r = await ops.run("workbench_open", {"agent": "claude", "name": "Chest fit audit"}, request_id="o1", request_text="open claude for the chest audit")
    assert r["status"] == "failed" and "your own agents in Lampway's panes are off" in r["text"] and cp.opened == []
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    r = await ops.run("workbench_open", {"agent": "claude", "name": "Chest fit audit"}, request_id="o2", request_text="open claude for the chest audit")
    assert r["status"] == "completed" and cp.opened == [("claude", "Chest fit audit", "agent")]


@pytest.mark.anyio
async def test_the_switch_file_in_the_servers_state_dir_counts_for_the_agent_path_too(tmp_path, monkeypatch):
    from lampway_server.ops import registry as REG
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "local_cli.json").write_text('{"enabled": true}')
    cp = OpenCockpit()
    ops = REG.AgentOps(cp, tmp_path / "ops", cwd=str(tmp_path), switch_dir=tmp_path / "state")
    r = await ops.run("workbench_open", {"agent": "codex", "name": "Boots seed read"}, request_id="o3", request_text="open codex")
    assert r["status"] == "completed" and cp.opened[-1][0] == "codex"


def test_the_agent_hub_hands_the_servers_state_dir_to_the_ops_layer(settings, provider, tmp_path):
    app = create_app(settings, provider=provider, cockpit=RecordingCockpit(tmp_path / "herdr"))
    assert Path(app.state.agent.ops.switch_dir) == Path(settings.state_dir)


# ---------------------------------------------------------------------------------------------------- MCP
def test_lampway_workbench_is_never_offered_over_mcp():
    from lampway_server import mcp as M
    from lampway_server.agent import tools as T
    assert "lampway_workbench" in {t.name for t in T.TOOLS}                  # the in-app agent has it (behind panes.drive) ...
    assert "lampway_workbench" not in {t.name for t in M.offered_tools()}    # ... an external MCP client never does
    assert not any(t["name"] == "lampway_workbench" for t in M.McpServer(None, None).tools_payload())
