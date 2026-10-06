# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_status_tool.md tests 1-7: the agent's ``lampway_connections`` reads status only - seven allowed fields, no write action,
the fixed refusal texts every other tool gives, ``for_use`` mapping a tool to its connection, the same fields over Lampway's MCP server
as in the main agent, and never a check."""

import asyncio
import json

import httpx
import pytest

from lampway_server import connections as C
from lampway_server.agent import connections_tools as CT
from lampway_server.connections import hub as H
from lampway_server.connections import store as CS

KEY = "msy-FAKE-TOOL-SENTINEL-888888888888"
ALLOWED = {"id", "label", "state", "route_on", "usable", "checked_age_s", "next_step"}


class Net:
    def __init__(self):
        self.requests = []

    def handler(self, request):
        self.requests.append(request)
        return httpx.Response(200, json={"balance": 1})


@pytest.fixture
def net():
    return Net()


@pytest.fixture
def hub(tmp_path, net):
    routes = {"studio:meshy": False, "openrouter": True}
    h = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={"MESHY_API_KEY": KEY}, store=CS.MemoryStore(), which=lambda b: None,
              home=tmp_path / "home", route_on=lambda r: routes.get(r, False), transport=httpx.MockTransport(net.handler))
    C.set_active(h)
    return h


def test_tool_has_no_write_action(hub):
    spec = next(s for s in CT.specs() if s.name == "lampway_connections")
    assert spec.parameters["additionalProperties"] is False and "action" not in spec.parameters["properties"]
    text, is_error = asyncio.run(CT.call("lampway_connections", {"ids": ["studio:meshy"], "action": "test"}))
    assert is_error and "action" in text


def test_projection_is_an_allow_list(hub, monkeypatch):
    sentinel_view = {"id": "studio:meshy", "label": "Meshy", "group": "Studios", "kind": "api_key", "state": "connected", "qualifiers": [],
                     "route": {"id": "studio:meshy", "on": True}, "active_source": {"mode": "env", "label": "MESHY_API_KEY from the environment"},
                     "identity": {"masked": "s•••@e•••.com", "plan": "Pro", "tier": "paid", "balance": {"amount": 1240, "unit": "credits"}},
                     "scopes": ["rodin:read"], "expires_at": 9e9, "checked_at": 1.0, "check_age_s": 840, "check_kind": "remote",
                     "fingerprint": {"last4": "SENT", "sha8": "deadbeef"}, "conflict": "the environment sets SECRET_NAME", "next_step": "/home/x/key.txt",
                     "unused": False, "note": "", "secret_path": "/home/x/.keys"}
    monkeypatch.setattr(hub, "view", lambda ids=None: [sentinel_view])
    text, is_error = asyncio.run(CT.call("lampway_connections", {"ids": ["studio:meshy"]}))
    assert not is_error
    out = json.loads(text)
    assert set(out["connections"][0]) == ALLOWED
    for s in ("s•••@e•••.com", "Pro", "1240", "SENT", "deadbeef", "SECRET_NAME", "/home/x", "rodin:read", "MESHY_API_KEY", "env"):
        assert s not in json.dumps(out["connections"]), s
    assert out["note"] == "status only: identities, balances and secrets are the user's and are not shown to agents"


def test_missing_connection_refusal_text(hub):
    hub._env = {}
    with pytest.raises(C.NotConnected) as exc:
        C.require("studio:meshy")
    assert str(exc.value) == "Meshy is not connected: connect it in Connections"
    text, is_error = CT.refusal(exc.value)
    assert is_error and json.loads(text) == {"error": "Meshy is not connected: connect it in Connections", "needs_connection": "studio:meshy"}


def test_route_off_refusal_text(hub):
    with pytest.raises(C.NotConnected) as exc:
        C.require("studio:meshy")
    assert str(exc.value) == "Meshy is connected but its route is off: switch it on in Privacy" and exc.value.needs_connection == "studio:meshy"
    row = json.loads(asyncio.run(CT.call("lampway_connections", {"ids": ["studio:meshy"]}))[0])["connections"][0]
    assert row["route_on"] is False and row["usable"] is False


def test_for_use_maps_a_tool_to_its_connection(hub, monkeypatch):
    from lampway_server import imagegen as IG
    monkeypatch.setattr(IG, "backend_name", lambda: "openrouter")
    out = json.loads(asyncio.run(CT.call("lampway_connections", {"for_use": "studio_image_generate"}))[0])
    assert [r["id"] for r in out["connections"]] == ["openrouter"]
    monkeypatch.setattr(IG, "backend_name", lambda: "tripo")
    out = json.loads(asyncio.run(CT.call("lampway_connections", {"for_use": "studio_image_generate"}))[0])
    assert [r["id"] for r in out["connections"]] == ["studio:tripo"]
    text, is_error = asyncio.run(CT.call("lampway_connections", {"for_use": "studio_image_generate", "ids": ["openrouter"]}))
    assert is_error and text == "ask by ids or by for_use, not both"
    text, is_error = asyncio.run(CT.call("lampway_connections", {"ids": ["nope"]}))
    assert is_error and text.startswith("no connection nope: the connections are ")


def test_mcp_and_main_agent_see_the_same_fields(hub):
    from lampway_server.agent.tools import TOOLS
    from lampway_server.mcp import McpServer
    main = next(t for t in TOOLS if t.name == "lampway_connections")
    server = McpServer(hub=type("Hub", (), {"sockets": {}})(), agent=None)
    listed = next(t for t in server.tools_payload() if t["name"] == "lampway_connections")
    assert listed["inputSchema"] == main.parameters
    reply = asyncio.run(server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lampway_connections",
                                                                                                    "arguments": {"ids": ["studio:meshy"]}}}, "", ""))
    via_mcp = json.loads(reply["result"]["content"][0]["text"])
    via_agent = json.loads(asyncio.run(CT.call("lampway_connections", {"ids": ["studio:meshy"]}))[0])
    assert via_mcp == via_agent


def test_tool_never_triggers_a_check(hub, net):
    for _ in range(100):
        asyncio.run(CT.call("lampway_connections", {}))
    assert net.requests == []
