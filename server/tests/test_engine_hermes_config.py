# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's Hermes config is the user's capability choices (docs/reports/agent-modes-spec.md E1.3, E1.10, E2).

Captain, 2026-10-06: "Nothing is removed; everything is chosen." Lampway writes each Mode 1 pane's ``HERMES_HOME/config.yaml``
from Capabilities before start (spec A1): the model is Lampway's gateway only (``provider: custom``), the serve platform's toolsets
are exactly the Hermes toolsets of the capabilities in force (plus clarify for a main agent), every outbound check Hermes lets config
switch off is off, and context stays Hermes's (Q3) unless given. On start Lampway compares the tool list the model is sent with the
choices and refuses a mismatch.

The unit tests need nothing outside the server. The live tests run the BUILT, pinned engine's ``hermes serve`` with the rendered
config against a fake OpenAI-compatible model on loopback and a refusing loopback proxy; without the engine they SKIP with the
reason, which is not a pass.
"""

import asyncio
import json
import os
import re
import signal
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lampway_server import capabilities as CAP
from lampway_server.engine import hermes_config as HC

GATEWAY = "http://127.0.0.1:8799/engine/v1"
TOKEN = "engine-token-for-tests"
MODEL = "lampway-engine-model"

#: The ACP toolsets the captain's defaults (Q8) turn on: vision, history.search, skills.use. scene.*, studio.plan are Lampway's
#: own tools, which reach the engine over MCP, not as Hermes toolsets.
DEFAULT_TOOLSETS = ["session_search", "skills", "vision"]


@pytest.fixture
def board(tmp_path):
    return CAP.Store(tmp_path / "state")


def _render(board, **kw):
    return HC.render(board, None, GATEWAY, TOKEN, MODEL, **kw)


@pytest.mark.parametrize("asks_user", [True, False])
def test_owned_panes_preserve_resumable_sessions_and_do_not_archive_open_ones(board, asks_user):
    # Native auto_prune deletes transcripts; auto_archive can hide unended sessions. Q2 permits neither.
    cfg = _render(board, asks_user=asks_user)
    assert cfg["sessions"]["auto_prune"] is False
    assert cfg["sessions"]["auto_archive"] is False


def _acp(cfg):
    """The toolsets of the platform the engine runs on: ``cli``, the one ``hermes serve`` and its TUI read (spec A1;
    tui_gateway/server.py:1939 at the pin). The ACP platform is gone with the ACP child (A5)."""
    assert set(cfg["platform_toolsets"]) == {HC.PLATFORM} == {"cli"}
    return cfg["platform_toolsets"]["cli"]


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))
    else:
        yield path, node


# ---------------------------------------------------------------------------------------------------- render: the toolsets
def test_defaults_turn_on_exactly_the_toolsets_of_the_capabilities_in_force(board):
    cfg = _render(board)
    assert _acp(cfg) == DEFAULT_TOOLSETS + ["clarify"]          # clarify: the island's question (spec A2)
    disabled = set(cfg["agent"]["disabled_toolsets"])
    assert {"terminal", "browser", "code_execution", "memory", "delegation", "file", "web", "cronjob", "computer_use"} <= disabled
    assert not disabled & set(DEFAULT_TOOLSETS)


def test_terminal_on_adds_the_terminal_toolset_with_the_chosen_backend(board):
    assert "terminal" not in _acp(_render(board)) and "terminal" not in _render(board)
    board.set("terminal", enabled=True)
    cfg = _render(board)
    assert "terminal" in _acp(cfg) and "terminal" not in cfg["agent"]["disabled_toolsets"]
    assert cfg["terminal"] == {"backend": "local"}
    board.set("terminal", options={"backend": "docker"})
    assert _render(board)["terminal"] == {"backend": "docker"}
    board.set("terminal", enabled=False)
    cfg = _render(board)
    assert "terminal" not in _acp(cfg) and "terminal" in cfg["agent"]["disabled_toolsets"] and "terminal" not in cfg
    # spec A1: the project root is the terminal's cwd whatever the choice; the backend is chosen only with the capability
    assert HC.render(board, "/proj", GATEWAY, TOKEN, MODEL)["terminal"] == {"cwd": "/proj"}
    board.set("terminal", enabled=True)
    assert HC.render(board, "/proj", GATEWAY, TOKEN, MODEL)["terminal"] == {"cwd": "/proj", "backend": "docker"}


def test_terminal_backend_outside_the_capabilitys_options_is_refused(board):
    board.set("terminal", enabled=True, options={"backend": "somewhere-else"})
    with pytest.raises(HC.Refused, match="backend"):
        _render(board)


def test_web_browse_is_in_force_only_while_its_route_is_on(board):
    board.set("web.browse", enabled=True)
    assert "browser" not in _acp(_render(board, routes_on=lambda r: False))
    assert "browser" in _acp(_render(board, routes_on=lambda r: True))
    board.set("web.browse", enabled=False)
    assert "browser" not in _acp(_render(board, routes_on=lambda r: True))


def test_memory_on_and_off(board):
    cfg = _render(board)
    assert "memory" not in _acp(cfg)
    assert cfg["memory"] == {"memory_enabled": False, "user_profile_enabled": False, "provider": ""}
    assert cfg["auxiliary"]["background_review"]["enabled"] is False
    board.set("memory", enabled=True)
    cfg = _render(board)
    assert "memory" in _acp(cfg) and "memory" not in cfg["agent"]["disabled_toolsets"]
    assert cfg["memory"] == {"memory_enabled": True, "user_profile_enabled": True, "provider": ""}
    assert cfg["auxiliary"]["background_review"]["enabled"] is False
    board.set("background", enabled=True)
    cfg = _render(board)
    assert cfg["auxiliary"]["background_review"]["enabled"] is True
    board.set("memory", enabled=False, project="/proj")
    assert "memory" not in _acp(HC.render(board, "/proj", GATEWAY, TOKEN, MODEL))


def test_skills_write_off_stages_every_skill_write_and_stops_the_curator(board):
    cfg = _render(board)
    assert "skills" in _acp(cfg)
    assert cfg["skills"]["write_approval"] is True and cfg["curator"]["enabled"] is False
    board.set("skills.write", enabled=True)
    cfg = _render(board)
    assert cfg["skills"]["write_approval"] is False and cfg["curator"]["enabled"] is False
    board.set("background", enabled=True)
    cfg = _render(board)
    assert cfg["skills"]["write_approval"] is False and cfg["curator"]["enabled"] is True
    board.set("skills.use", enabled=False)
    board.set("skills.write", enabled=False)
    assert "skills" not in _acp(_render(board))


def test_every_capability_maps_to_its_hermes_toolsets(board):
    expect = {"files.project": "file", "terminal": "terminal", "code.execute": "code_execution", "web.search": "web",
              "web.browse": "browser", "memory": "memory", "subagents": "delegation", "schedule": "cronjob",
              "computer.use": "computer_use", "history.search": "session_search", "vision": "vision"}
    for cid, toolset in expect.items():
        b = CAP.Store(board.state_dir / cid)
        for c in CAP.CATALOGUE:
            if c.default:
                b.set(c.id, enabled=False)
        b.set(cid, enabled=True)
        assert _acp(HC.render(b, None, GATEWAY, TOKEN, MODEL, routes_on=lambda r: True)) == [toolset, "clarify"], cid


def test_the_mapping_and_the_catalogue_agree_both_ways():
    with_hermes = {c.id for c in CAP.CATALOGUE if c.hermes}
    assert set(HC.HERMES_TOOLSETS) | set(HC.NOT_EXPRESSIBLE) == with_hermes
    assert not set(HC.HERMES_TOOLSETS) & set(HC.NOT_EXPRESSIBLE)
    for toolsets in HC.HERMES_TOOLSETS.values():
        assert toolsets and set(toolsets) <= set(HC.TOOLSET_TOOLS)


def test_lampway_tools_stay_reachable_over_mcp_whatever_the_choices(board):
    """Lampway's tools are the ONE config-declared MCP server, ``lampway`` (spec A1, A3): the unit's endpoint with its bearer. The
    platform list carries no ``no_mcp`` (which drops config-declared servers, tools_config.py:685-686 at the pin) and no ``mcp-*``
    toolset is disabled, so the choices never hide Lampway's tools."""
    for c in CAP.CATALOGUE:
        board.set(c.id, enabled=False)
    url = "http://127.0.0.1:8799/engine/mcp/unit-1"
    cfg = _render(board, mcp_url=url, mcp_headers={"Authorization": "Bearer unit-bearer"})
    assert _acp(cfg) == ["clarify"] and "no_mcp" not in _acp(cfg)
    assert cfg["mcp_servers"] == {"lampway": {"url": url, "headers": {"Authorization": "Bearer unit-bearer"}}}
    assert not any(str(t).startswith("mcp") for t in cfg["agent"]["disabled_toolsets"])
    assert "mcp_servers" not in _render(board), "no endpoint given: no server declared"
    with pytest.raises(HC.Refused, match="loopback"):
        _render(board, mcp_url="https://example.invalid/mcp")


def test_a_worker_never_asks_the_user_and_reaches_its_own_endpoint(board):
    """Spec S2/S3: a Mode 1 worker's pane gets no clarify (it reports what it could not do in its summary) and its one MCP server is
    the pane endpoint, pinned to its binding."""
    url = "http://127.0.0.1:8799/api/v1/mcp/pane"
    headers = {"X-Mixar-Session-Id": "swarm:s1:w-1", "Authorization": "Bearer worker-token"}
    cfg = _render(board, mcp_url=url, mcp_headers=headers, asks_user=False)
    assert "clarify" not in _acp(cfg) and "clarify" in cfg["agent"]["disabled_toolsets"]
    assert cfg["mcp_servers"] == {"lampway": {"url": url, "headers": headers}}


def test_the_client_surface_toolsets_are_never_on(board):
    """``hermes serve``'s sessions fold the client surface's toolsets in (``project`` for the TUI, tui_gateway/server.py:1842-1858
    at the pin): Lampway's pane is no Hermes Desktop, so they are named off."""
    for c in CAP.CATALOGUE:
        board.set(c.id, enabled=True)
    disabled = set(_render(board, routes_on=lambda r: True)["agent"]["disabled_toolsets"])
    assert {"project", "desktop_ui"} <= disabled


# ---------------------------------------------------------------------------------------------------- render: the model and logins
def test_the_model_is_lampways_gateway_and_nothing_else(board):
    cfg = _render(board)
    assert cfg["model"] == {"provider": "custom", "base_url": GATEWAY, "api_key": TOKEN, "default": MODEL}
    assert cfg["fallback_providers"] == [] and cfg["providers"] == {}
    assert cfg["auth"] == {"adopt_external_logins": False}


def test_config_gate_no_provider_but_custom_anywhere(board):
    for c in CAP.CATALOGUE:
        board.set(c.id, enabled=True)
    cfg = _render(board, routes_on=lambda r: True, context={"compression": {"enabled": True}})
    providers = [(p, v) for p, v in _walk(cfg) if p and p[-1] == "provider"]
    assert providers, "the gate must see the model's provider"
    for path, value in providers:
        assert value in ("custom", ""), f"{'.'.join(map(str, path))} = {value!r}"
    assert [p for p, v in providers if v == "custom"] == [("model", "provider")]


def test_config_gate_plant_another_provider_is_caught(board):
    """The gate above can fail: a planted second provider is found by the same walk."""
    cfg = _render(board)
    cfg["delegation"] = {"provider": "openrouter"}
    bad = [(p, v) for p, v in _walk(cfg) if p and p[-1] == "provider" and v not in ("custom", "")]
    assert bad == [(("delegation", "provider"), "openrouter")]


def test_no_key_from_the_environment_reaches_the_config(board, monkeypatch):
    sentinel = "sk-env-sentinel-0123456789"
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "NOUS_API_KEY", "HERMES_API_KEY", "OPENAI_BASE_URL",
                "XAI_API_KEY", "GEMINI_API_KEY", "LAMPWAY_ENGINE_TOKEN"):
        monkeypatch.setenv(var, sentinel)
    for c in CAP.CATALOGUE:
        board.set(c.id, enabled=True)
    text = HC.to_yaml(_render(board, routes_on=lambda r: True))
    assert text and sentinel not in text
    source = Path(HC.__file__).read_text()
    assert "environ" not in source and "getenv" not in source


def test_a_gateway_off_loopback_is_refused(board):
    for url in ("https://api.openai.com/v1", "http://10.0.0.5:8799/engine/v1", "http://example.invalid/v1", "ftp://127.0.0.1/x"):
        with pytest.raises(HC.Refused, match="loopback"):
            HC.render(board, None, url, TOKEN, MODEL)
    for url in ("http://127.0.0.1:1/engine/v1", "http://localhost:9/v1", "http://[::1]:9/v1"):
        assert HC.render(board, None, url, TOKEN, MODEL)["model"]["base_url"] == url


def test_an_empty_token_or_model_is_refused(board):
    with pytest.raises(HC.Refused):
        HC.render(board, None, GATEWAY, "", MODEL)
    with pytest.raises(HC.Refused):
        HC.render(board, None, GATEWAY, TOKEN, "")


# ---------------------------------------------------------------------------------------------------- render: outbound calls
def test_every_outbound_check_hermes_lets_config_switch_off_is_off(board):
    cfg = _render(board)
    assert cfg["updates"]["check"] is False
    assert cfg["telemetry"] == {"shared_metrics": {"enabled": False, "send": False}}
    assert cfg["model_catalog"]["enabled"] is False
    assert cfg["security"]["allow_lazy_installs"] is False
    assert cfg["lsp"]["install_strategy"] == "manual"
    assert cfg["tools"]["connectors"]["enabled"] is False
    assert cfg["models_dev"]["url"].startswith("http://127.0.0.1:8799/")
    # spec A1, measured on the pinned serve: no Nous guest bootstrap, no guardian model for approvals (the user answers them)
    assert cfg["nous"] == {"guest": False}
    assert cfg["approvals"] == {"mode": "manual"}


def test_models_dev_url_can_be_given_and_must_be_loopback(board):
    assert _render(board, models_dev_url="http://127.0.0.1:8799/x.json")["models_dev"]["url"] == "http://127.0.0.1:8799/x.json"
    with pytest.raises(HC.Refused, match="loopback"):
        _render(board, models_dev_url="https://models.dev/api.json")


def test_the_mcp_tool_call_timeout_is_hermess_largest_unclamped_value(board):
    """Lampway's MCP tools run Blender scripts up to 600 s and a swarm's collect waits for its workers. Hermes clamps every
    timeout at MAX_SAFE_TIMEOUT_S = 31_536_000 s (agent/deadline.py:38, clamp at :111 at the pin)."""
    assert HC.MCP_TOOL_CALL_TIMEOUT_S == 31_536_000
    assert _render(board)["timeouts"] == {"mcp": {"tool_call": 31_536_000}}


# ---------------------------------------------------------------------------------------------------- render: context is Hermes's (Q3)
def test_context_is_left_at_hermess_defaults_unless_given(board):
    cfg = _render(board)
    assert not {"compression", "context", "prompt_caching"} & set(cfg)
    assert "tool_search" not in cfg["tools"] and "context_length" not in cfg["model"]


def test_context_is_written_through(board):
    ctx = {"compression": {"enabled": True, "threshold": 0.7}, "tools": {"tool_search": {"enabled": "auto", "defer": []}},
           "model": {"context_length": 131072}, "context": {"engine": "compressor"}}
    cfg = _render(board, context=ctx)
    assert cfg["compression"] == {"enabled": True, "threshold": 0.7}
    assert cfg["tools"]["tool_search"] == {"enabled": "auto", "defer": []} and cfg["tools"]["connectors"]["enabled"] is False
    assert cfg["model"]["context_length"] == 131072 and cfg["model"]["provider"] == "custom"
    assert cfg["context"] == {"engine": "compressor"}


@pytest.mark.parametrize("ctx", [{"model": {"provider": "openrouter"}}, {"model": {"base_url": "https://x.invalid"}},
                                 {"platform_toolsets": {"cli": ["terminal"]}}, {"auth": {"adopt_external_logins": True}},
                                 {"agent": {"disabled_toolsets": []}}, {"tools": {"connectors": {"enabled": True}}},
                                 {"updates": {"check": True}}, {"timeouts": {"mcp": {"tool_call": 5}}}, {"mcp_servers": {"x": {}}}])
def test_context_cannot_reach_a_choice_or_the_model_route(board, ctx):
    with pytest.raises(HC.Refused, match="context"):
        _render(board, context=ctx)


# ---------------------------------------------------------------------------------------------------- write
def test_write_makes_a_0600_config_in_a_0700_home_that_reads_back(board, tmp_path):
    yaml = pytest.importorskip("yaml", reason="PyYAML parses the written file back; Hermes reads it in the live test")
    home = tmp_path / "state" / "agent" / "hermes" / "sess1"
    board.set("terminal", enabled=True)
    path = HC.write(home, board, None, GATEWAY, TOKEN, MODEL, context={"compression": {"threshold": 0.5}})
    assert path == home / "config.yaml"
    assert stat.S_IMODE(home.stat().st_mode) == 0o700 and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert yaml.safe_load(path.read_text()) == HC.render(board, None, GATEWAY, TOKEN, MODEL, context={"compression": {"threshold": 0.5}})
    home.chmod(0o755)
    HC.write(home, board, None, GATEWAY, TOKEN, MODEL)
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    # the config and the toolset pin serve reloads live (spec E2), both 0600, and no temporary file left
    assert sorted(p.name for p in home.iterdir()) == [".env", "config.yaml"]
    assert stat.S_IMODE((home / ".env").stat().st_mode) == 0o600
    assert (home / ".env").read_text() == "HERMES_TUI_TOOLSETS=" + ",".join(HC.serve_toolsets(HC.read(home))) + "\n"


def test_yaml_round_trips_awkward_strings():
    yaml = pytest.importorskip("yaml", reason="PyYAML parses the emitted text back")
    doc = {"a": "yes", "b": "no", "c": "null", "d": "1e3", "e": "x: y #z", "f": "", "g": "line\nbreak", "h": "ünïcödé ✓",
           "i": [], "j": {}, "k": ["a", 1, 2.5, True, None], "l": {"m": {"n": False}}, "0": "zero", "o": "'q'\"", "p": "~"}
    assert yaml.safe_load(HC.to_yaml(doc)) == doc


def test_write_never_touches_the_users_own_hermes(board, tmp_path, monkeypatch):
    """E1.10: Lampway's engine Hermes and the user's own Hermes share nothing."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for home in (tmp_path / "home" / ".hermes", tmp_path / "home" / ".hermes" / "profiles" / "x"):
        with pytest.raises(HC.Refused, match="Hermes"):
            HC.write(home, board, None, GATEWAY, TOKEN, MODEL)
    assert not (tmp_path / "home" / ".hermes").exists()


# ---------------------------------------------------------------------------------------------------- the start-up check
def test_lampways_instructions_are_hermess_own_system_prompt_setting(board):
    """Lampway's guidance on its tools reaches Mode 1's Hermes through ``agent.system_prompt`` (hermes_cli/personality.py
    ``resolve_ephemeral_system_prompt``, read when serve builds a session, tui_gateway/server.py:2384, and appended to the system
    message of every model call, agent/chat_completion_helpers.py:2176): no file in the user's project, no replaced identity."""
    cfg = _render(board, instructions="Use Lampway's tools.")
    assert cfg["agent"]["system_prompt"] == "Use Lampway's tools." and cfg["agent"]["disabled_toolsets"]
    assert "system_prompt" not in _render(board)["agent"], "nothing given, nothing written"
    with pytest.raises(HC.Refused, match="context may set only"):
        _render(board, context={"agent": {"system_prompt": "x"}})


def test_the_written_config_reads_back_as_the_dict_it_was_rendered_from(board, tmp_path):
    """A pane's config is re-rendered when the user switches a capability while it runs (spec E2): the server reads back its own
    file for the pane's keys (it keeps only their digests), so ``read`` must give exactly what ``render`` gave."""
    for c in CAP.CATALOGUE:
        board.set(c.id, enabled=True)
    board.set("terminal", options={"backend": "docker"})
    rendered = {}
    HC.write(tmp_path / "h", board, "/proj ect", GATEWAY, TOKEN, MODEL, mcp_url="http://127.0.0.1:8799/engine/mcp/u 1",
             mcp_headers={"Authorization": "Bearer b\"q", "X-Mixar-Session-Id": "swarm:s:w"}, rendered=rendered,
             routes_on=lambda r: True, supports_vision=True, context={"compression": {"threshold": 0.5, "enabled": True}},
             instructions="Line one.\nLine \"two\": yes, no, true.")
    assert HC.read(tmp_path / "h") == rendered
    assert HC.from_yaml(HC.to_yaml({"a": {}, "b": [], "c": [{"x": [1, 2.5, None]}], "d": -1.5e-07, "e": "on"})) == \
        {"a": {}, "b": [], "c": [{"x": [1, 2.5, None]}], "d": -1.5e-07, "e": "on"}


def _tool(name, description=""):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {"type": "object"}}}


DEFAULT_VISIBLE = ["skills_list", "skill_view", "skill_manage", "vision_analyze", "session_search"]


def test_expected_tools_under_the_defaults(board):
    assert HC.expected_tools(board, None) == {"skills_list", "skill_view", "skill_manage", "vision_analyze", "session_search"}
    board.set("terminal", enabled=True)
    assert {"terminal", "process_manage"} <= HC.expected_tools(board, None)


def test_the_check_passes_the_choices_and_lampways_mcp_tools(board):
    tools = [_tool(n) for n in DEFAULT_VISIBLE] + [_tool("mcp__lampway__scene_summary")]
    assert HC.check_advertised(tools, board, None) == []
    assert HC.check_advertised(DEFAULT_VISIBLE, board, None) == []


def test_the_check_allows_the_main_agents_clarify_and_refuses_a_workers(board):
    """Spec A2: the main agent asks the island through Hermes's own ``clarify``; it is allowed, never chosen, so its absence is no
    mismatch. A worker never asks (S2): its clarify is refused."""
    assert HC.check_advertised(DEFAULT_VISIBLE + ["clarify"], board, None) == []
    assert HC.check_advertised(DEFAULT_VISIBLE, board, None) == []
    found = HC.check_advertised(DEFAULT_VISIBLE + ["clarify"], board, None, asks_user=False)
    assert [(m.kind, m.tool) for m in found] == [("unexpected", "clarify")] and HC.refuses(found)


def test_the_check_refuses_a_tool_the_user_did_not_choose(board):
    for extra in ("terminal", "browser_navigate", "execute_code", "memory", "delegate_task", "a_new_hermes_tool", "mcp__github__x"):
        found = HC.check_advertised(DEFAULT_VISIBLE + [extra], board, None)
        assert [(m.kind, m.tool) for m in found] == [("unexpected", extra)], extra
        assert HC.refuses(found)
    board.set("terminal", enabled=True)
    found = HC.check_advertised(DEFAULT_VISIBLE + ["terminal", "process_manage"], board, None)
    assert found == []


def test_a_chosen_tool_hermes_did_not_offer_is_reported_but_does_not_refuse(board):
    found = HC.check_advertised(["skills_list", "skill_view", "skill_manage", "session_search"], board, None)
    assert [(m.kind, m.tool) for m in found] == [("missing", "vision_analyze")]
    assert not HC.refuses(found)


def _bridge(listing, n):
    desc = (f"Search {n} additional tools that are loaded on demand. Takes a list of queries ...\n\nEvery deferred capability is listed "
            "below. If a tool name appears here, do NOT claim it is unavailable.\n\n" + listing)
    return [_tool("tool_search", desc), _tool("tool_describe"), _tool("tool_call")]


def test_deferred_tools_behind_hermess_tool_search_are_checked_too(board):
    """Hermes's tool_search (context, Q3: left to Hermes) defers some tools behind a bridge; the bridge's description lists them,
    in the format of tools/tool_search_catalog.py ``build_catalog_listing_with_form`` at the pin."""
    listing = ("Deferred tool catalog (call schemas via `tool_describe`, invoke via `tool_call`):\n"
               "lampway tools (2):\n- mcp__lampway__scene_summary: Summarise the scene.\n- mcp__lampway__ask_user\n"
               "session_search tools (1):\n- session_search: Search past conversations")
    visible = [_tool(n) for n in DEFAULT_VISIBLE if n != "session_search"]
    names, groups = HC.deferred_listing(visible + _bridge(listing, 3))
    assert names == {"mcp__lampway__scene_summary", "mcp__lampway__ask_user", "session_search"} and groups == frozenset()
    assert HC.check_advertised(visible + _bridge(listing, 3), board, None) == []
    planted = listing + "\nterminal tools (2):\nterminal, process_manage"
    found = HC.check_advertised(visible + _bridge(planted, 5), board, None)
    assert sorted((m.kind, m.tool) for m in found) == [("unexpected", "process_manage"), ("unexpected", "terminal")]
    found = HC.check_advertised(visible + _bridge(listing, 4), board, None)
    assert [(m.kind, m.tool) for m in found] == [("unverifiable", "tool_search")], "a deferred tool the listing does not name"


def test_a_summarised_deferred_group_must_be_an_allowed_mcp_server(board):
    visible = [_tool(n) for n in DEFAULT_VISIBLE]
    ok = "Deferred tool catalog (x):\nlampway (40 tools — names not listed; discover via `tool_search`)"
    assert HC.deferred_listing(visible + _bridge(ok, 40))[1] == {"lampway"}
    assert HC.check_advertised(visible + _bridge(ok, 40), board, None) == []
    bad = ok + "\nbrowser (12 tools — names not listed; discover via `tool_search`)"
    found = HC.check_advertised(visible + _bridge(bad, 52), board, None)
    assert [(m.kind, m.tool) for m in found] == [("unverifiable", "browser")] and HC.refuses(found)


def test_a_bridge_whose_deferred_tools_cannot_be_read_refuses(board):
    visible = [_tool(n) for n in DEFAULT_VISIBLE]
    bare = [_tool("tool_search", "Search remote connector tools (email, calendars, issue trackers, and more)."), _tool("tool_describe"),
            _tool("tool_call")]
    found = HC.check_advertised(visible + bare, board, None)
    assert [(m.kind, m.tool) for m in found] == [("unverifiable", "tool_search")]
    found = HC.check_advertised(DEFAULT_VISIBLE + ["tool_search", "tool_describe", "tool_call"], board, None)
    assert [(m.kind, m.tool) for m in found] == [("unverifiable", "tool_search")]


# ---------------------------------------------------------------------------------------------------- live: the built engine
def _find_engine():
    """The pinned engine built by scripts/lampway/engine_env.py: $LAMPWAY_HERMES_ENGINE, or build/engines/hermes/<tag>/ in this
    checkout or a checkout above it (a lane worktree sits inside the main checkout). Its ``hermes serve`` is what a Mode 1 pane runs
    (spec A1)."""
    given = os.environ.get("LAMPWAY_HERMES_ENGINE")
    candidates = [Path(given)] if given else [p / "build" / "engines" / "hermes" / HC.PINNED_TAG for p in Path(__file__).resolve().parents]
    for root in candidates:
        exe = root / "env" / "bin" / "hermes"
        if exe.is_file() and os.access(exe, os.X_OK):
            return exe
    return None


ENGINE = _find_engine()
live = pytest.mark.skipif(ENGINE is None, reason=f"the built engine (build/engines/hermes/{HC.PINNED_TAG}/env/bin/hermes) is missing; "
                                                 "build it with scripts/lampway/engine_env.py or set LAMPWAY_HERMES_ENGINE")


def _handler(record):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return H


def _fake_model(record):
    class Model(_handler(record)):
        def do_GET(self):
            record.append(("GET", self.path, None))
            if self.path.rstrip("/").endswith("/models"):
                return self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "context_length": 131072}]})
            self._send(404, {"error": "not here"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            record.append(("POST", self.path, {"stream": body.get("stream"), "tools": body.get("tools") or [],
                                               "auth": self.headers.get("Authorization")}))
            text, now = "Hello from the fake model.", int(time.time())
            if body.get("stream"):
                chunks = [{"id": "c1", "object": "chat.completion.chunk", "created": now, "model": MODEL,
                           "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]},
                          {"id": "c1", "object": "chat.completion.chunk", "created": now, "model": MODEL,
                           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}]
                data = b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n"
                return self._send(200, data, "text/event-stream")
            self._send(200, {"id": "c1", "object": "chat.completion", "created": now, "model": MODEL,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    return Model


def _fake_mcp(record):
    """A tiny streamable-HTTP MCP server named ``lampway`` with one tool, as Lampway's engine endpoint will be (E1.6)."""
    class Mcp(_handler(record)):
        def do_POST(self):
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            record.append(msg.get("method"))
            if "id" not in msg:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            method = msg["method"]
            if method == "initialize":
                res = {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "lampway", "version": "0.1"}}
            elif method == "tools/list":
                res = {"tools": [{"name": "lampway_ping", "description": "Answers pong with the word.",
                                  "inputSchema": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]}}]}
            else:
                res = {}
            self._send(200, {"jsonrpc": "2.0", "id": msg["id"], "result": res})

        def do_GET(self):
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_DELETE(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
    return Mcp


def _refusing_proxy(record):
    class Deny(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _deny(self):
            record.append(self.path)
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
        do_CONNECT = do_GET = do_POST = do_HEAD = do_PUT = _deny
    return Deny


def _host(target):
    m = re.match(r"^(?:[a-z]+://)?([^/:]+)", target)
    return m.group(1) if m else target


def _serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


async def _live_turn(root: Path, board, project):
    """One ``hermes serve`` with the rendered config, as a Mode 1 pane runs it (spec A1): a session, one prompt. Returns what the
    fake model, the ``lampway`` MCP server and the refusing proxy saw."""
    from lampway_server.engine.serve_client import ServeClient
    from .serve_support import free_port
    model_seen, mcp_seen, denied = [], [], []
    model, mcp, proxy = _serve(_fake_model(model_seen)), _serve(_fake_mcp(mcp_seen)), _serve(_refusing_proxy(denied))
    home, cwd = root / "agent" / "hermes" / "unit", root / "project"
    cwd.mkdir(parents=True)
    gateway = f"http://127.0.0.1:{model.server_address[1]}/engine/v1"
    rendered = {}
    HC.write(home, board, project, gateway, TOKEN, MODEL, mcp_url=f"http://127.0.0.1:{mcp.server_address[1]}/mcp",
             mcp_headers={"Authorization": "Bearer engine-mcp-token"}, rendered=rendered)
    via = f"http://127.0.0.1:{proxy.server_address[1]}"
    port = free_port()
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "LANG", "LC_ALL", "TZ") or k.startswith("PYTHON") and k != "PYTHONPATH"}
    (home / "managed").mkdir(exist_ok=True)
    (home / "locks").mkdir(exist_ok=True)
    env.update(HERMES_HOME=str(home), HOME=str(root / "home"), TMPDIR=str(root), NO_COLOR="1", HTTPS_PROXY=via, HTTP_PROXY=via,
               https_proxy=via, http_proxy=via, ALL_PROXY=via, all_proxy=via, NO_PROXY="127.0.0.1", no_proxy="127.0.0.1",
               HERMES_MANAGED_DIR=str(home / "managed"), HERMES_GATEWAY_LOCK_DIR=str(home / "locks"),
               HERMES_DASHBOARD_SESSION_TOKEN="serve-token", HERMES_TUI_WS_ORPHAN_REAP_GRACE_S="0",
               HERMES_TUI_TOOLSETS=",".join(HC.serve_toolsets(rendered)))
    (root / "home").mkdir()
    log = open(root / "serve.log", "w")
    proc = await asyncio.create_subprocess_exec(str(ENGINE), "serve", "--host", "127.0.0.1", "--port", str(port), stdin=asyncio.subprocess.DEVNULL,
                                                stdout=log, stderr=log, env=env, cwd=str(cwd), start_new_session=True)
    out = {"error": None}
    client = None
    try:
        events = []

        async def on_event(params):
            events.append(params)
        deadline = time.monotonic() + 120
        while True:
            client = ServeClient(port, "serve-token", on_event=on_event)
            try:
                await client.connect()
                break
            except Exception:  # noqa: BLE001 - serve still starting
                await client.close()
                if time.monotonic() > deadline or proc.returncode is not None:
                    raise
                await asyncio.sleep(0.3)
        created = await client.call("session.create", {"cwd": str(cwd), "cols": 100})
        await client.call("prompt.submit", {"session_id": created["session_id"], "text": "Say hello."}, timeout=120)
        end = time.monotonic() + 180
        while not any(e.get("type") == "message.complete" for e in events):
            assert time.monotonic() < end, "no message.complete"
            await asyncio.sleep(0.1)
        out["status"] = next(e for e in events if e.get("type") == "message.complete")["payload"].get("status")
    except Exception as exc:  # noqa: BLE001 - the test reports it
        out["error"] = repr(exc)
    finally:
        if client is not None:
            await client.close()
        try:
            os.killpg(proc.pid, signal.SIGTERM)                       # serve's own group, by its recorded pid
            await asyncio.wait_for(proc.wait(), 15)
        except (ProcessLookupError, asyncio.TimeoutError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        log.close()
        out["stderr"] = (root / "serve.log").read_text(errors="replace") + "".join(
            p.read_text(errors="replace") for p in (home / "logs").glob("*.log"))
        for srv in (model, mcp, proxy):
            srv.shutdown()
    turns = [body for method, _, body in model_seen if method == "POST" and body["stream"]]
    out.update(turn_tools=turns[0]["tools"] if turns else None, turn_auth=turns[0]["auth"] if turns else None,
               mcp_methods=mcp_seen, denied_hosts=sorted({_host(t) for t in denied}), model_requests=len(model_seen))
    return out


@pytest.fixture(scope="module")
def live_runs(tmp_path_factory):
    """The defaults and ``terminal`` on, run side by side (each serve listens in ~3 s; its first session takes 2-4 s more)."""
    base = tmp_path_factory.mktemp("engine-live")
    boards = {"defaults": CAP.Store(base / "defaults-state"), "terminal": CAP.Store(base / "terminal-state")}
    boards["terminal"].set("terminal", enabled=True)

    async def both():
        return await asyncio.gather(*(_live_turn(base / name, b, None) for name, b in boards.items()))

    results = dict(zip(boards, asyncio.run(both())))
    for name, res in results.items():
        print(f"\n[live {name}] status={res.get('status')} error={res['error']} denied_hosts={res['denied_hosts']} "
              f"tools={[t['function']['name'] for t in res['turn_tools'] or []]} mcp={res['mcp_methods']}")
    return boards, results


def _names(tools):
    return {t["function"]["name"] for t in tools}


def _reachable(tools):
    return _names(tools) | set(HC.deferred_listing(tools)[0])


HERMES_ACTING = re.compile(r"^(terminal|process_manage|browser_.*|execute_code|memory|delegate_task)$")


@live
@pytest.mark.timeout(600)
def test_live_defaults_offer_no_terminal_browser_code_memory_or_delegation(live_runs):
    boards, results = live_runs
    res = results["defaults"]
    assert res["error"] is None and res["status"] == "complete", res["stderr"][-3000:]
    assert res["turn_tools"] is not None, "the fake model never received the turn"
    assert res["turn_auth"] == f"Bearer {TOKEN}"
    reachable = _reachable(res["turn_tools"])
    assert not {n for n in reachable if HERMES_ACTING.match(n)}, sorted(reachable)
    found = HC.check_advertised(res["turn_tools"], boards["defaults"], None)
    assert not HC.refuses(found), found


@live
@pytest.mark.timeout(600)
def test_live_terminal_on_offers_terminal(live_runs):
    boards, results = live_runs
    res = results["terminal"]
    assert res["error"] is None and res["turn_tools"] is not None, res["stderr"][-3000:]
    assert "terminal" in _reachable(res["turn_tools"])
    assert not {n for n in _reachable(res["turn_tools"]) if HERMES_ACTING.match(n) and n not in ("terminal", "process_manage")}
    found = HC.check_advertised(res["turn_tools"], boards["terminal"], None)
    assert not HC.refuses(found), found
    assert HC.refuses(HC.check_advertised(res["turn_tools"], boards["defaults"], None)), "the check must refuse terminal under the defaults"


@live
@pytest.mark.timeout(600)
def test_live_lampways_mcp_tool_is_reachable_under_the_defaults(live_runs):
    """Lampway's tools reach the engine as the session's MCP server ``lampway`` (config.yaml mcp_servers, spec A1, A3). Hermes's tool_search may defer
    it behind the bridge; it must be visible or listed as deferred, or at least registered."""
    _, results = live_runs
    res = results["defaults"]
    assert "tools/list" in res["mcp_methods"], res["mcp_methods"]
    registered = re.search(r"registered \d+ tool\(s\):[^\n]*mcp__lampway__lampway_ping", res["stderr"])
    assert "mcp__lampway__lampway_ping" in _reachable(res["turn_tools"]) or registered, res["stderr"][-3000:]


@live
@pytest.mark.timeout(600)
def test_live_the_switched_off_checks_are_not_attempted(live_runs):
    """Every host Hermes tried through the refusing proxy is recorded (and printed); the ones the config switches off must not be
    among them: the model catalog (hermes-agent.nousresearch.com, raw.githubusercontent.com), models.dev, lazy installs (pypi.org)."""
    _, results = live_runs
    for name, res in results.items():
        tried = set(res["denied_hosts"])
        assert not tried & {"models.dev", "hermes-agent.nousresearch.com", "raw.githubusercontent.com", "pypi.org",
                            "telemetry.nousresearch.com"}, (name, sorted(tried))
