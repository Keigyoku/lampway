# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cursor's agent CLI (`cursor-agent`): the user's own Cursor agent, in a Lampway pane.

Resume: `--resume <chatId>`. Bypass (the user's tick only): `--force`. Lampway's tools are added through `--plugin-dir`, with a
manifest and MCP file under the pane's own directory. HOME, login and shared project configuration remain the user's. Cursor's
own plugin policy and MCP approval gates still apply; the adapter grants none. Images: refused (nothing recorded says the CLI
takes one). Observation: the screen. Checked on cursor-agent 2026.10.01-e373342; account-backed tool execution remains unverified.
"""
import json
from pathlib import Path

from .base import Adapter, LoginState, Observer, ToolWiring, SERVER_NAME, mcp_entry, bearer_headers, direct_binding


class Cursor(Adapter):
    id = "cursor"
    label = "Cursor agent"
    binary = "cursor-agent"
    herdr_kind = "cursor"
    install_hint = "install Cursor's agent CLI (cursor-agent) with Cursor's own installer"
    status_argv = ("status", "--format", "json")
    BYPASS = ("--force",)
    task_flag = ()                             # `cursor-agent [prompt...]`: the initial prompt
    interrupt_keys = ("ctrl+c",)
    takes_image_paths = False
    images_note = ("Cursor's agent CLI documents no way to take an image in its prompt (cursor-agent 2026.10.01 --help), so the "
                   "image was not sent: describe it in words, or switch this tab to an agent that takes images")
    tools_reachable = True
    direct_ok = True
    worker_note = ("Cursor workers need exclusive MCP discovery. Cursor merges global, project, parent and plugin MCP "
                   "servers; --plugin-dir only adds this pane's entries. Choose a qualified worker mode in Agent "
                   "preferences; Cursor MAIN panes keep their native configuration and login.")
    FACTS = {
        "version": "2026.10.01-e373342 installed with Cursor's own install script into a throwaway HOME; "
                   "`cursor-agent --version`",
        "argv": "`cursor-agent --help`: `[prompt...]`, `--resume [chatId]`, `-f, --force` (alias --yolo)",
        "status": "`cursor-agent status --format json` signed out: {\"isAuthenticated\": false, ...} and exit 0: the field is the signal",
        "mcp": "2026.10.01-e373342 `--help` exposes repeatable --plugin-dir. Its shipped runtime loads root plugin.json and "
               ".mcp.json and passes pluginMcpService into the agent's MCP manager; HOME/login are unchanged. `mcp list` omits "
               "the plugin manager, so it cannot verify this route. [UNVERIFIED by a tool call: an authenticated pane and its "
               "vendor plugin policy are required; no --approve-mcps or policy override is added]",
        "worker_isolation": "Cursor's official CLI MCP configuration documentation describes merged global, project, "
                            "parent and plugin sources (https://cursor.com/docs/cli/mcp). --plugin-dir adds Lampway's "
                            "entries without excluding those sources; workers are refused while MAIN wiring remains additive.",
        "herdr": "herdr 0.9.3 knows the kind `cursor` and runs `cursor-agent` (src/detect/mod.rs interactive_agent_executable)",
        "interrupt": "Ctrl+C: herdr 0.9.3's cursor.toml manifest reads a running turn by 'ctrl+c to stop'. [UNVERIFIED on the "
                     "installed copy: a turn needs an account]",
        "images": "no image option or attachment in `--help`: refused",
        "session_file": "none Lampway reads: the island shows the screen",
    }

    def _args(self, pane, resume_id):
        return (["--resume", resume_id] if resume_id else []) + self._bypass(pane)

    def lampway_tools(self, pane):
        path = pane.mcp_config_path
        if not path:
            return ToolWiring("plugin")
        plugin = Path(path).parent / "lampway-plugin"
        servers = {SERVER_NAME: mcp_entry(pane)} if pane.desktop else {}
        for direct in pane.direct:
            servers[direct.name] = {"url": direct.url, "headers": bearer_headers(direct)}
        body = json.dumps({"mcpServers": servers}, indent=2)
        manifest = json.dumps({"name": "lampway", "version": "1.0.0", "description": "Lampway's tools for this pane"}, indent=2)
        return ToolWiring("plugin", ("--plugin-dir", str(plugin)), {},
                          {path: body, str(plugin / "plugin.json"): manifest, str(plugin / ".mcp.json"): body},
                          tuple(pane.launcher), pane.scene_session_id or direct_binding(pane), False,
                          "Cursor's supported --plugin-dir adds this pane's MCP entries without moving HOME/login or changing shared "
                          "configuration. Its own plugin policy and MCP approvals apply; account-backed tool execution is unverified.")

    def read_status(self, code, out):
        try:
            data = json.loads(out)
        except ValueError:
            return super().read_status(code, out)
        if isinstance(data, dict) and isinstance(data.get("isAuthenticated"), bool):
            return LoginState("signed_in" if data["isAuthenticated"] else "signed_out", str(data.get("message") or "")[:200])
        return super().read_status(code, out)

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen")
