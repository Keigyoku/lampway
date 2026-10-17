# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI plugin injection adds only a pane-local MCP entry and retains the user's login home."""
import json
from pathlib import Path

from lampway_server.herdr import harnesses as HN


def test_cursor_plugin_files_are_pane_local_and_keep_bearers_off_the_command_line(tmp_path):
    root = tmp_path / "panes" / "one"
    direct = HN.DirectServer("lampway_swarm", "http://127.0.0.1:8787/api/v1/mcp/pane",
                             {HN.SESSION_HEADER: "scene-one"}, "LAMPWAY_PANE_KEY", "pane-only-bearer")
    pane = HN.PaneSpec(cwd=str(tmp_path / "project"), scene_session_id="scene-one",
                       mcp_config_path=str(root / "mcp.json"), launcher=("/opt/lw/lampway-mcp",), direct=(direct,))
    adapter = HN.get("cursor")
    wiring = adapter.lampway_tools(pane)
    assert wiring.kind == "plugin" and adapter.tools_reachable and adapter.direct_ok
    plugin = root / "lampway-plugin"
    assert wiring.argv == ("--plugin-dir", str(plugin))
    assert all(Path(path).is_relative_to(root) for path in wiring.files), "nothing writes the user home or project config"
    manifest = json.loads(wiring.files[str(plugin / "plugin.json")])
    assert manifest["name"] == "lampway" and manifest["version"]
    servers = json.loads(wiring.files[str(plugin / ".mcp.json")])["mcpServers"]
    assert servers["lampway"] == {"command": "/opt/lw/lampway-mcp", "args": [], "env": {HN.BOUND_ENV: "scene-one"}}
    assert servers["lampway_swarm"]["headers"] == {HN.SESSION_HEADER: "scene-one", "Authorization": "Bearer pane-only-bearer"}
    assert not wiring.env, "HOME and the harness's own config/login variables remain unchanged"
    for argv in (adapter.launch(pane), adapter.resume("old-session", pane)):
        assert "--plugin-dir" in argv and "pane-only-bearer" not in " ".join(argv)
        assert not any(arg in argv for arg in ("--approve-mcps", "--force", "--yolo")), "tool wiring grants no permission bypass"


def test_cursor_worker_plugin_contains_only_its_direct_server_and_no_desktop_launcher(tmp_path):
    direct = HN.DirectServer("lampway", "http://127.0.0.1:8787/api/v1/mcp/pane",
                             {HN.SESSION_HEADER: "swarm:one:worker-one"}, "LAMPWAY_WORKER_KEY", "worker-only-bearer")
    pane = HN.PaneSpec(cwd=str(tmp_path), desktop=False, direct=(direct,), mcp_config_path=str(tmp_path / "pane" / "mcp.json"))
    wiring = HN.get("cursor").lampway_tools(pane)
    plugin = Path(pane.mcp_config_path).parent / "lampway-plugin"
    servers = json.loads(wiring.files[str(plugin / ".mcp.json")])["mcpServers"]
    assert set(servers) == {"lampway"} and "command" not in servers["lampway"]
    assert servers["lampway"]["headers"][HN.SESSION_HEADER] == "swarm:one:worker-one"
    assert wiring.bound_session == "swarm:one:worker-one"
