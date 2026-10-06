# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_agent_tool.md tests 1-7: ``lampway_choices`` reads and proposes, never changes a choice; its views go through an allow-list; an
agent never proposes its own provider; the override policy (CH3) applies to the other tools that take a model; the MCP server and the
main agent see the same answer; ``explain`` names what the job would really run."""

import asyncio
import json

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.agent import choices_tools as CT
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG

FLARE = "openrouter:openai/gpt-image-2.5-flare"
RIVER = "openrouter:sourceful/riverflow-v2.5-pro"


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    CH.active_store().set("image.plates", "global", None, {"preferred": FLARE, "fallbacks": [RIVER]}, by="user")
    yield
    CH.set_active(None, None)


def call(args, origin="agent:main"):
    text, is_error = asyncio.run(CT.call("lampway_choices", args, origin=origin))
    return (json.loads(text) if not is_error else text), is_error


def test_tool_has_no_write_action(live):
    spec = next(s for s in CT.specs() if s.name == "lampway_choices")
    assert set(spec.parameters["properties"]["action"]["enum"]) == {"list", "view", "explain", "propose", "proposals"}
    assert spec.parameters["additionalProperties"] is False
    out, err = call({"action": "set", "purpose": "image.plates"})
    assert err
    out, err = call({"action": "view", "purpose": "image.plates", "project": "/x"})
    assert err and "project" in out


def test_projection_is_an_allow_list(live, monkeypatch):
    from lampway_server.choices import views as V
    real = V.option_view

    def leaky(*a, **k):
        out = real(*a, **k)
        out.update(identity="s•••@e•••.com", balance=1240, path="/home/x/key.txt", variable="OPENROUTER_API_KEY", fingerprint={"sha8": "deadbeef"})
        out["connection"] = {"id": "openrouter", "state": "connected", "masked": "s•••@e•••.com"}
        return out
    monkeypatch.setattr(V, "option_view", leaky)
    for args in ({"action": "view", "purpose": "image.plates"}, {"action": "explain", "purpose": "image.plates"}, {"action": "list"}):
        out, err = call(args)
        blob = json.dumps(out)
        assert not err and all(s not in blob for s in ("s•••@e•••.com", "1240", "/home/x", "OPENROUTER_API_KEY", "deadbeef", "world_digest")), args


def test_propose_changes_nothing(live):
    before = CH.resolve("image.plates", CH.Job(content_class="public")).option
    version = CH.active_store().global_doc()["version"]
    out, err = call({"action": "propose", "purpose": "image.plates", "preferred": RIVER, "reason": "rated 4.7 vs 3.9 over 6 runs", "evidence": ["ledger:run-81"]})
    assert not err and out["state"] == "open" and out["note"] == "the user decides in Choices; nothing has changed"
    assert CH.resolve("image.plates", CH.Job(content_class="public")).option == before and CH.active_store().global_doc()["version"] == version
    out, err = call({"action": "proposals"})
    assert [p["purpose"] for p in out["proposals"]] == ["image.plates"]
    out, err = call({"action": "proposals"}, origin="mcp:other")
    assert out["proposals"] == [], "an origin sees its own proposals only"


def test_agent_cannot_propose_its_own_provider(live):
    out, err = call({"action": "propose", "purpose": "agent.main", "preferred": "claude_cli", "reason": "cheaper"})
    assert err and out.startswith("an agent must not change its own provider")


def test_override_policy_applies_to_other_tools(live, monkeypatch, tmp_path):
    from lampway_server.agent import image_tools as IT
    from lampway_server.prompts.library import Library
    from lampway_server.prompts.runlog import RunLog
    from lampway_server.prompts.service import PromptService
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    svc = PromptService(Library(builtin_dir=Library().dirs["builtin"], user_dir=tmp_path / "u"), RunLog(tmp_path / "runs.jsonl"))
    text, err = asyncio.run(IT.call(svc, "lampway_image_gen", {"prompt": "a helmet", "model": "google/gemini-3.1-flash-image"}))
    assert err and text == "openrouter:google/gemini-3.1-flash-image is not one of your choices for image.plates: propose it with lampway_choices"
    text, err = asyncio.run(IT.call(svc, "lampway_image_gen", {"prompt": "a helmet", "model": "sourceful/riverflow-v2.5-pro"}))
    assert not err and json.loads(text)["model"] == "sourceful/riverflow-v2.5-pro"


def test_mcp_and_main_agent_see_the_same_fields(live):
    from lampway_server.agent.tools import TOOLS
    from lampway_server.mcp import McpServer
    main = next(t for t in TOOLS if t.name == "lampway_choices")
    server = McpServer(hub=type("Hub", (), {"sockets": {}})(), agent=None)
    listed = next(t for t in server.tools_payload() if t["name"] == "lampway_choices")
    assert listed["inputSchema"] == main.parameters
    reply = asyncio.run(server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lampway_choices",
                                                                                                    "arguments": {"action": "view", "purpose": "image.plates"}}}, "", ""))
    assert json.loads(reply["result"]["content"][0]["text"]) == call({"action": "view", "purpose": "image.plates"})[0]


def test_explain_matches_the_real_resolution(live):
    out, err = call({"action": "explain", "purpose": "image.plates", "job": {"content_class": "public", "override": RIVER}})
    real = CH.resolve("image.plates", CH.Job(content_class="public"))
    assert not err and out["option"]["id"] == real.option and out["reason"] == real.reason
    assert out["override_allowed"] is True
    out, err = call({"action": "explain", "purpose": "image.plates", "job": {"override": "openrouter:google/gemini-3.1-flash-image"}})
    assert out["override_allowed"] is False and "propose it" in out["override_reason"]
