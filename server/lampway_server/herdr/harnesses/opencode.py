# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenCode (`opencode`): the user's own OpenCode, on its own login, in a Lampway pane.

Resume: `--session <id>`. Bypass (the user's tick only): `--auto`. Lampway's tools: this pane's own config file named by
`OPENCODE_CONFIG` [UNVERIFIED: the spec named the project's opencode.json, which every pane in the project would share and which is
the user's own file; a per-pane file through the variable keeps the binding per pane].
"""
import json

from .base import BOUND_ENV, SERVER_NAME, Adapter, Observer, ToolWiring

#: OpenCode stops listing a server's tools after 5 s by default; the launcher may first have to start Lampway (the Client's setup).
TOOLS_TIMEOUT_MS = 60_000


class OpenCode(Adapter):
    id = "opencode"
    label = "OpenCode"
    binary = "opencode"
    herdr_kind = "opencode"
    install_hint = "install OpenCode (opencode): npm install -g opencode-ai"          # [UNVERIFIED] the package name
    status_argv = ("auth", "list")                                                     # [UNVERIFIED] lists providers; exit status only
    BYPASS = ("--auto",)

    def _args(self, pane, resume_id):
        return (["--session", resume_id] if resume_id else []) + self._bypass(pane)

    def lampway_tools(self, pane):
        cmd = list(pane.launcher) or ["lampway-mcp"]
        body = json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": {SERVER_NAME: {
            "type": "local", "command": cmd, "enabled": True, "timeout": TOOLS_TIMEOUT_MS, "environment": {BOUND_ENV: pane.scene_session_id or ""}}}}, indent=2)
        path = pane.mcp_config_path
        return ToolWiring("mcp_config_file", (), {"OPENCODE_CONFIG": path} if path else {}, {path: body} if path else {}, tuple(pane.launcher),
                          pane.scene_session_id, False, "[UNVERIFIED] OPENCODE_CONFIG names this pane's own config file; the project's opencode.json is left alone")

    def observe(self, record):
        return Observer("screen", None, True, "OpenCode keeps no session file Lampway reads: the pane's screen")
