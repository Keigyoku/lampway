# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermes Agent (`hermes`): the USER'S OWN Hermes, never Lampway's engine (agent-modes spec E1.10, captain's Q9).

The two share nothing: the user's Hermes is whatever is on the user's PATH, with the user's own home and providers; Lampway's engine
is the pinned release under `<install>/engines/hermes/<tag>/`. detect() skips any binary under an `engines/hermes` directory, and
nothing here names, reads or writes the user's Hermes home.

Resume: `--resume <id>`. Bypass (the user's tick only): `--yolo`. Lampway's supported pane wiring remains unavailable. Hermes
loads MCP servers from its home's `config.yaml` and enabled portable plugins. Native `--toolsets` can restrict discovery to a
named connector, but a dedicated symbolic connector/helper requires explicit persistent setup. Another HERMES_HOME changes
configuration and provider state; some profile OAuth state can fall back to the root profile, which does not establish a
general login-preserving pane route. Lampway never writes the user's home (E1.10). Observation: the screen (its `state.db` is
in the user's Hermes home). Checked on Hermes Agent v0.21.5 (2026.9.24) with a throwaway HOME and HERMES_HOME (see FACTS).
"""
import os

from .base import Adapter, Observer

ENGINE_MARK = ("engines", "hermes")


def _is_engine(directory: str) -> bool:
    parts = os.path.realpath(directory).split(os.sep)
    return any(parts[i:i + 2] == list(ENGINE_MARK) for i in range(len(parts) - 1))


class Hermes(Adapter):
    id = "hermes"
    label = "Your Hermes"
    binary = "hermes"
    herdr_kind = "hermes"
    install_hint = "install Hermes Agent (hermes) from Nous Research, on your PATH (Lampway's own engine copy is never used here)"
    status_argv = None                         # `hermes status` is a board of every component, not a login check
    BYPASS = ("--yolo",)
    interrupt_keys = ("ctrl+c",)
    takes_image_paths = True
    tools_reachable = False
    tools_note = ("Your own Hermes loads configured MCP servers and enabled portable plugins. Lampway never writes your shared "
                  "configuration (agent-modes spec E1.10). Its native --toolsets filter can select a dedicated connector, but "
                  "that connector/helper needs explicit persistent setup; this adapter has no verified pane-scoped wiring "
                  "preserving your existing provider and login configuration")
    FACTS = {
        "version": "Hermes Agent v0.21.5 (2026.9.24): Lampway's pinned build of the same release, run as a user's would be with a "
                   "throwaway HOME and HERMES_HOME (`hermes --version`)",
        "argv": "`hermes --help` (v0.21.5): `--resume, -r SESSION` (by id or title), `--yolo` (bypass approval prompts); no positional "
                "prompt at the top level",
        "status": "`hermes status` prints every component and exits 0 signed out: no login status command is run",
        "mcp": "config.yaml under HERMES_HOME supplies native servers; tools/mcp_tool_config.py also merges enabled portable "
               "plugin servers. No separate per-process MCP config-path override was found in v0.21.5",
        "mcp_filter": "on the pinned v2026.9.24 interpreter, network-denied discovery connected four synthetic servers without "
                      "a filter (worker, unrelated native, user portable plugin, project portable plugin); the native --toolsets "
                      "name filter connected only the worker. Its symbolic LAMPWAY_BOUND_SESSION arrived, and synthetic login-store "
                      "and environment-file hashes stayed unchanged. This proves discovery filtering, not a user-TUI scene call "
                      "or an installed connector/helper (scratch receipt native-mcp-scope-options-receipt.json)",
        "profile_auth": "hermes_cli/auth.py _load_provider_state_with_source can fall back to the root profile's login store for "
                        "some OAuth state; profile configuration and environment files remain separate. Native refresh can write "
                        "the root login store (auth_xai.py). This is not a general login-preserving scoped-config route",
        "herdr": "herdr 0.9.3 knows the kind `hermes` (src/detect/mod.rs interactive_agent_executable)",
        "interrupt": "Ctrl+C: the TUI's hotkeys ('clear draft / interrupt / exit', ui-tui/src/content/hotkeys.ts) and its busy "
                     "placeholder 'Ctrl+C to interrupt'; a typed draft is cleared first",
        "images": "the TUI attaches a pasted image path and keeps the caption after it (ui-tui/src/app/useComposerState.ts "
                  "attachImageToken); `/image <path>` does the same. [UNVERIFIED by a turn: needs a configured provider]",
        "session_file": "its state.db is in the user's Hermes home, which Lampway never reads (E1.10): the island shows the screen",
    }

    def _search_path(self) -> str:
        return os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if d and not _is_engine(d))

    def _args(self, pane, resume_id):
        return (["--resume", resume_id] if resume_id else []) + self._bypass(pane)

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen: Hermes's own state.db is in the user's Hermes home, which Lampway never reads (E1.10)")
