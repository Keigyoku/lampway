# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pi (`pi`): the user's own Pi coding agent, in a Lampway pane.

Pi has no MCP by design [UNVERIFIED]: it reaches Lampway through a Pi extension that calls the Lampway launcher, shipped with
Lampway [UNVERIFIED; the extension is not built yet]. Resume: `--session <id>` [UNVERIFIED]. Bypass: none (Pi has no permission
prompt to bypass) [UNVERIFIED]. Observation: its session file [UNVERIFIED], the screen until a fixture records where it lives.
"""
import json

from .base import BOUND_ENV, Adapter, Observer, ToolWiring

EXTENSION = "lampway"


class Pi(Adapter):
    id = "pi"
    label = "Pi"
    binary = "pi"
    config_name = "lampway-extension.json"
    install_hint = "install Pi (pi): npm install -g @mariozechner/pi-coding-agent"     # [UNVERIFIED] the package name
    status_argv = None                                                                # [UNVERIFIED] no login status command recorded

    def _args(self, pane, resume_id):
        return ["--session", resume_id] if resume_id else []                          # [UNVERIFIED] session switch / resume

    def lampway_tools(self, pane):
        cmd = list(pane.launcher) or ["lampway-mcp"]
        path = pane.mcp_config_path
        body = json.dumps({"extension": EXTENSION, "launcher": cmd, "env": {BOUND_ENV: pane.scene_session_id or ""}}, indent=2)
        return ToolWiring("extension", (), {}, {path: body} if path else {}, tuple(pane.launcher), pane.scene_session_id, False,
                          f"[UNVERIFIED] Pi has no MCP by design: the Pi extension '{EXTENSION}' (to ship with Lampway, not built yet) calls the "
                          "Lampway launcher with this pane's binding; until it ships this pane cannot reach Lampway's tools")

    def observe(self, record):
        return Observer("screen", None, True, "[UNVERIFIED] Pi's own session file, once a fixture records where it lives; the pane's screen until then")
