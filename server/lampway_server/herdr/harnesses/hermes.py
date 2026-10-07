# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermes Agent (`hermes`): the USER'S OWN Hermes, never Lampway's engine (agent-modes spec E1.10, captain's Q9).

The two share nothing: the user's Hermes is whatever is on the user's PATH, with the user's own home and providers; Lampway's engine
is the pinned release under `<install>/engines/hermes/<tag>/`. detect() skips any binary under an `engines/hermes` directory, and
nothing here names, reads or writes the user's Hermes home.

Resume: `--resume <id>`. Bypass (the user's tick only): `--yolo`. Lampway's tools: not reachable from this pane. Hermes reads its MCP
servers only from `config.yaml` in its home (HERMES_HOME, else ~/.hermes): pointing a pane at another home would take the user's
providers and logins away from it, and writing the user's home is what E1.10 forbids. A user who wants Lampway's tools in their
own Hermes adds Lampway's connector themselves (`hermes mcp add`), unpinned to any tab. Observation: the screen (its `state.db` is
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
    tools_note = ("Your own Hermes reads MCP servers only from config.yaml in its own home, which Lampway never writes (agent-modes "
                  "spec E1.10), so this pane cannot reach Lampway's tools; add Lampway's connector yourself with `hermes mcp add` "
                  "if you want them there (it is not pinned to a scene tab)")
    FACTS = {
        "version": "Hermes Agent v0.21.5 (2026.9.24): Lampway's pinned build of the same release, run as a user's would be with a "
                   "throwaway HOME and HERMES_HOME (`hermes --version`)",
        "argv": "`hermes --help` (v0.21.5): `--resume, -r SESSION` (by id or title), `--yolo` (bypass approval prompts); no positional "
                "prompt at the top level",
        "status": "`hermes status` prints every component and exits 0 signed out: no login status command is run",
        "mcp": "MCP servers live only in HERMES_HOME's config.yaml (`hermes mcp --help`; the source reads no other config variable "
               "than HERMES_HOME): no per-pane config without replacing the user's home",
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
