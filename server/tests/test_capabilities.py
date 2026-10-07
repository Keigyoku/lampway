# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capabilities: one switchboard for what an agent can do (docs/reports/agent-modes-spec.md E2; captain, 2026-10-06: "I want it all
behind a single interface you can choose WHAT your agent can do. The user can choose like they choose Routes").

Nothing is removed; every ability is a row the user switches. Only the user's click changes one; an agent reads the board and
proposes. A capability that needs an egress route stays off until that route is on (law 2). Lampway's own tool families are
checked at call time, for the in-app agent and for external MCP clients alike.
"""

import json
import os
import stat
import uuid

import pytest

from lampway_server import capabilities as CAP
from lampway_server.agent.providers.base import Text, ToolCall

#: The captain's defaults (Q8, approved 2026-10-06 as proposed).
ON_BY_DEFAULT = {"scene.read", "scene.edit", "vision", "history.search", "skills.use", "studio.plan"}


@pytest.fixture
def board(tmp_path):
    store = CAP.Store(tmp_path / "state")
    CAP.set_active(store)
    yield store
    CAP.set_active(None)


def test_the_catalogue_is_the_specs_table_with_the_captains_defaults():
    ids = [c.id for c in CAP.CATALOGUE]
    assert len(ids) == len(set(ids)) == 21
    assert {"messaging.*", "mcp.*", "web.browse", "terminal", "panes.drive", "swarm"} <= set(ids)
    assert {c.id for c in CAP.CATALOGUE if c.default} == ON_BY_DEFAULT
    for c in CAP.CATALOGUE:
        assert c.risk in CAP.RISKS and c.approval in CAP.APPROVALS and c.label and c.does.endswith(".")
    assert CAP.get("messaging.telegram").routes == ("msg:telegram",) and CAP.get("mcp.github").id == "mcp.github"
    with pytest.raises(CAP.UnknownCapability):
        CAP.get("teleport")


def test_a_fresh_board_is_the_defaults(board):
    assert {c.id for c in CAP.CATALOGUE if board.effective(c.id)[0]} == ON_BY_DEFAULT


def test_only_the_user_changes_it_and_every_change_is_logged(board, tmp_path):
    with pytest.raises(CAP.Refused) as refused:
        board.set("swarm", enabled=True, by="agent")
    assert refused.value.status == 403 and not board.effective("swarm")[0]
    board.set("swarm", enabled=True, by="user")
    assert board.effective("swarm") == (True, "")
    path = tmp_path / "state" / "capabilities.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    rows = [json.loads(line) for line in (tmp_path / "state" / "capabilities" / "log.jsonl").read_text().splitlines()]
    assert [(r["id"], r["event"], r["by"]) for r in rows] == [("swarm", "refused_change", "agent"), ("swarm", "changed", "user")]


def test_a_project_overrides_the_global_choice(board):
    board.set("swarm", enabled=True, by="user")
    board.set("swarm", enabled=False, project="/projects/chair", by="user")
    assert board.effective("swarm")[0] and not board.effective("swarm", project="/projects/chair")[0]
    assert board.effective("swarm", project="/projects/lamp")[0]


def test_a_capability_waits_for_its_routes(board):
    board.set("web.browse", enabled=True, by="user")
    on, why = board.effective("web.browse", routes_on=lambda route: False)
    assert not on and "web:any" in why
    assert board.effective("web.browse", routes_on=lambda route: True) == (True, "")


def test_lampway_tools_belong_to_a_family():
    assert CAP.family_of("swarm_start") == "swarm"
    assert CAP.family_of("studio_plan") == "studio.plan"
    assert CAP.family_of("lampway_workbench", {"action": "send"}) == "panes.drive"
    assert CAP.family_of("lampway_workbench", {"action": "read"}) == "scene.read"
    assert CAP.family_of("scene_summary") == "scene.read"
    assert CAP.family_of("run_blender_python") == "scene.edit"
    assert CAP.family_of("lampway_capabilities") is None and CAP.family_of("ask_user") is None    # never gated


def test_the_agent_tool_reads_and_proposes_but_cannot_set(board):
    from lampway_server.agent import capabilities_tools as CT
    spec = CT.specs()[0]
    assert spec.parameters["properties"]["action"]["enum"] == ["list", "explain", "propose", "proposals"]
    text, err = CT.call("lampway_capabilities", {"action": "propose", "id": "web.search", "enabled": True, "reason": "find a reference"},
                        origin="agent")
    assert not err and "proposed" in text
    assert not board.effective("web.search")[0]
    assert [p["id"] for p in board.proposals()] == ["web.search"]
    _, err = CT.call("lampway_capabilities", {"action": "set", "id": "web.search"}, origin="agent")
    assert err


def test_the_rest_route_refuses_an_agent_and_takes_the_users_click(fake, http, settings):
    fake.login()
    listed = fake.get("/app/capabilities")
    assert listed.status_code == 200
    rows = {r["id"]: r for r in listed.json()["capabilities"]}
    assert rows["swarm"]["enabled"] is False and rows["scene.edit"]["enabled"] is True and rows["web.browse"]["routes"] == [
        {"id": "web:any", "on": False}]
    refused = fake.put("/app/capabilities/swarm", json={"enabled": True}, headers={"X-Lampway-Origin": "agent"})
    assert refused.status_code == 403
    done = fake.put("/app/capabilities/swarm", json={"enabled": True})
    assert done.status_code == 200 and done.json()["enabled"] is True
    assert fake.put("/app/capabilities/teleport", json={"enabled": True}).status_code == 404


def test_the_in_app_agent_does_not_see_or_run_a_family_that_is_off(fake, provider, http):
    provider.script = [[ToolCall(id="s1", name="swarm_start", arguments={"tasks": []})], [Text("ok")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("split it up", str(uuid.uuid4())))
        fake.run_turn(ws, cmd, on_script=lambda p: {"success": True})
    offered = {t.name for t in provider.requests[0].tools}
    assert "swarm_start" not in offered and "lampway_capabilities" in offered and "run_blender_python" in offered
    result = next(p for m in provider.requests[1].messages for p in m.content if p.get("type") == "tool_result")
    assert result["is_error"] and "swarm" in result["content"] and "lampway_capabilities" in result["content"]


def test_an_mcp_call_into_a_family_that_is_off_is_refused_with_its_name(fake, http):
    fake.login()
    assert fake.put("/app/capabilities/scene.edit", json={"enabled": False}).status_code == 200
    body = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "x=1"}}}
    reply = fake.post("/api/v1/mcp", json=body, headers={"X-Mixar-Instance-Id": "nobody", "X-Mixar-Session-Id": "scene-1",
                                                          "Accept": "application/json, text/event-stream"}).json()
    result = reply["result"]
    assert result["isError"] and "scene.edit" in result["content"][0]["text"]
