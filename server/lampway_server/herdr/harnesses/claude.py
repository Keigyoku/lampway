# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Claude Code (`claude`): the user's own Claude Code, on its own login, in a pane on Lampway's herdr server.

New session: `--session-id <uuid>` chosen by Lampway (recorded as the native id); resume: `--resume <id>`. Effort: `--effort`.
Bypass (the user's tick only): `--dangerously-skip-permissions`. Lampway's tools: a per-pane `--mcp-config <file>` [UNVERIFIED flag].
"""
import json
import os

from ..observers.native import claude_transcript
from .base import Adapter, Observer, SERVER_NAME, ToolWiring, mcp_entry


class Claude(Adapter):
    id = "claude"
    label = "Claude Code"
    binary = "claude"
    herdr_kind = "claude"
    install_hint = "install Claude Code (claude) from Anthropic: npm install -g @anthropic-ai/claude-code"
    status_argv = ("auth", "status")          # [UNVERIFIED] the subcommand name and its exit status on a signed-out machine
    api_key_connections = ("anthropic",)
    picks_session_id = True
    BYPASS = ("--dangerously-skip-permissions",)

    def _args(self, pane, resume_id):
        a = ["--resume", resume_id] if resume_id else (["--session-id", pane.session_id] if pane.session_id else [])
        a += self._bypass(pane)
        if pane.effort:
            a += ["--effort", pane.effort]
        return a

    def lampway_tools(self, pane):
        path = pane.mcp_config_path
        body = json.dumps({"mcpServers": {SERVER_NAME: mcp_entry(pane)}}, indent=2)
        return ToolWiring("mcp_config_file", ("--mcp-config", path) if path else (), {}, {path: body} if path else {}, tuple(pane.launcher),
                          pane.scene_session_id, False,
                          "[UNVERIFIED flag] --mcp-config <file> adds this pane's own server entry; the user's own user-scope entries are left alone")

    def observe(self, record):
        if not record.get("native_id"):
            return Observer("screen", None, True, "no session id recorded: the pane's screen")
        return Observer("session_file", claude_transcript(record.get("cwd") or "", record["native_id"], os.environ.get("CLAUDE_CONFIG_DIR")), True,
                        "Claude Code's own transcript (observers/native.py)")
