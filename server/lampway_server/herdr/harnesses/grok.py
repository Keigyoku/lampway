# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grok (Grok Build, `grok`): the user's own Grok CLI, in a Lampway pane.

New session: `--session-id <uuid>` chosen by Lampway (recorded as the native id); resume: `--resume <id>`. Bypass (the user's tick
only): `--always-approve`. Lampway's supported pane wiring remains unavailable. Grok 1.0.46 accepts a primary custom-agent
Markdown file through `--agent <path>` and can add inline MCP entries. That overlay retains unrelated servers from the user's
config and compat sources; `enabled: false` does not remove an inherited entry. A worker-only MCP route preserving the user's
login is therefore unproved. Observation: the screen. Checked on an installed Grok 1.0.46 (see FACTS).
"""
from .base import Adapter, Observer


class Grok(Adapter):
    id = "grok"
    label = "Grok"
    binary = "grok"
    herdr_kind = "grok"
    install_hint = "install Grok Build's CLI (grok) with xAI's own installer (its Grok CLI page)"
    status_argv = None                         # grok has `login` and `logout`, no status command
    picks_session_id = True
    BYPASS = ("--always-approve",)
    task_flag = ()                             # `grok [PROMPT]`: the interactive session starts with it
    interrupt_keys = ("ctrl+c",)
    takes_image_paths = True
    tools_reachable = False
    tools_note = ("Grok's --agent file can add MCP entries, but its primary-agent overlay retains unrelated configured servers; "
                  "enabled: false does not remove an inherited server. Lampway has no verified worker-only pane route preserving "
                  "your login, so its supported pane wiring remains unavailable. Lampway never writes your shared MCP config.")
    FACTS = {
        "version": "1.0.46 installed with xAI's own install script into a throwaway HOME; `grok --version` -> "
                   "'grok 1.0.46 (2765805b9442)'",
        "argv": "`grok --help` (1.0.46): `[PROMPT]`, `-s, --session-id <SESSION_ID>` (a new conversation's UUID), `-r, --resume "
                "[<SESSION_ID_OR_TITLE>]`, `--always-approve`, `--agent <path>`",
        "status": "no status command (`login`, `logout` only)",
        "mcp": "`grok mcp add --help` and docs/user-guide/07-mcp-servers.md (installed with 1.0.46): user and project config.toml, "
               ".mcp.json and compat sources; GROK_CONFIG_PATH and GROK_CONFIG naming a pane file left `grok mcp list` empty (checked)",
        "primary_agent": "network-denied synthetic first turn on 1.0.46 activated --agent <absolute.md> when mcpServers was a YAML "
                         "sequence of singleton mappings; the earlier mapping-shaped fixture was invalid. The custom body and "
                         "inline stdio server were observed without an account or provider call",
        "mcp_scope": "the same offline fixture retained the inherited desktop server despite enabled: false; a complete same-name "
                     "inline entry replaced it, but an unrelated inherited sentinel still initialized and listed tools. "
                     "mcpInheritance: none did not exclude primary-agent disk sources. Inline env placeholders arrived literally; "
                     "omitting the inline env mapping preserved the inherited process binding. This does not prove HTTP headers "
                     "or an exclusive worker route (scratch receipt grok-primary-route-supported-receipt.json)",
        "herdr": "herdr 0.9.3 knows the kind `grok` (src/detect/mod.rs interactive_agent_executable)",
        "interrupt": "Ctrl+C: docs/user-guide/03-keyboard-shortcuts.md (1.0.46) 'Esc ... never cancels a running turn (Ctrl+C does)'; "
                     "herdr 0.9.3's grok.toml still names an older 'Esc:cancel' footer",
        "images": "an image dragged into the prompt (a pasted path) becomes an image chip (docs/user-guide/03-keyboard-shortcuts.md, "
                  "1.0.46). [UNVERIFIED by a turn: needs an account]",
        "session_file": "~/.grok/sessions/<url-encoded cwd>/<session id>/updates.jsonl, an ACP session-update stream (docs/user-guide/"
                        "17-sessions.md, 1.0.46); not mirrored yet: the island shows the screen",
    }

    def _args(self, pane, resume_id):
        if resume_id:
            return ["--resume", resume_id, *self._bypass(pane)]
        return (["--session-id", pane.session_id] if pane.session_id else []) + self._bypass(pane)

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen (Grok's updates.jsonl is an ACP stream Lampway does not mirror yet)")
