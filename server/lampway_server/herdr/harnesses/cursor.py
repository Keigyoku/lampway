# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cursor's agent CLI (`cursor-agent`): the user's own Cursor agent, in a Lampway pane.

Resume: `--resume <chatId>`. Bypass (the user's tick only): `--force`. Lampway's tools: not reachable from this pane. The agent
reads MCP servers only from the project's `.cursor/mcp.json` and the user's `~/.cursor/mcp.json`; CURSOR_CONFIG_DIR would move the
user's whole config, login included. Images: refused (nothing recorded says the CLI takes one). Observation: the screen. Checked on
an installed cursor-agent 2026.10.01-e373342 (see FACTS).
"""
import json

from .base import Adapter, LoginState, Observer


class Cursor(Adapter):
    id = "cursor"
    label = "Cursor agent"
    binary = "cursor-agent"
    herdr_kind = "cursor"
    install_hint = "install Cursor's agent CLI (cursor-agent): curl https://cursor.com/install -fsS | bash"
    status_argv = ("status", "--format", "json")
    BYPASS = ("--force",)
    task_flag = ()                             # `cursor-agent [prompt...]`: the initial prompt
    interrupt_keys = ("ctrl+c",)
    takes_image_paths = False
    images_note = ("Cursor's agent CLI documents no way to take an image in its prompt (cursor-agent 2026.10.01 --help), so the "
                   "image was not sent: describe it in words, or switch this tab to an agent that takes images")
    tools_reachable = False
    tools_note = ("Cursor's agent reads MCP servers only from the project's .cursor/mcp.json and your ~/.cursor/mcp.json, which "
                  "Lampway never writes, so this pane cannot reach Lampway's tools; add Lampway's connector there yourself if you "
                  "want them (it is not pinned to a scene tab)")
    FACTS = {
        "version": "2026.10.01-e373342 installed with Cursor's installer (https://cursor.com/install) into a throwaway HOME; "
                   "`cursor-agent --version`",
        "argv": "`cursor-agent --help`: `[prompt...]`, `--resume [chatId]`, `-f, --force` (alias --yolo)",
        "status": "`cursor-agent status --format json` signed out: {\"isAuthenticated\": false, ...} and exit 0: the field is the signal",
        "mcp": "`cursor-agent mcp --help` / `mcp list`: '.cursor/mcp.json or ~/.cursor/mcp.json' only",
        "herdr": "herdr 0.9.3 knows the kind `cursor` and runs `cursor-agent` (src/detect/mod.rs interactive_agent_executable)",
        "interrupt": "Ctrl+C: herdr 0.9.3's cursor.toml manifest reads a running turn by 'ctrl+c to stop'. [UNVERIFIED on the "
                     "installed copy: a turn needs an account]",
        "images": "no image option or attachment in `--help`: refused",
        "session_file": "none Lampway reads: the island shows the screen",
    }

    def _args(self, pane, resume_id):
        return (["--resume", resume_id] if resume_id else []) + self._bypass(pane)

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
