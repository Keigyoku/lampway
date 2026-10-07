# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermes Agent (`hermes`): the USER'S OWN Hermes, never Lampway's engine (agent-modes spec E1.10, captain's Q9).

The two share nothing: the user's Hermes is whatever is on the user's PATH, with the user's own home and providers; Lampway's engine
is the pinned release under `<install>/engines/hermes/<tag>/`. detect() skips any binary under an `engines/hermes` directory, and
nothing here names, reads or writes the user's Hermes home.

Resume: `--resume <id>` [UNVERIFIED]. Bypass: none recorded [UNVERIFIED], so none is ever emitted. Lampway's tools: a per-pane MCP
config file [UNVERIFIED: no flag recorded that points Hermes at it]. Observation: the screen (the spec's `state.db` would mean
reading the user's Hermes home, which E1.10 forbids; raised as a decision).
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
    install_hint = "install Hermes Agent (hermes) from Nous Research, on your PATH (Lampway's own engine copy is never used here)"   # [UNVERIFIED] no command recorded
    status_argv = None                         # [UNVERIFIED] no login status command recorded: Hermes uses the providers configured in it

    def _search_path(self) -> str:
        return os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if d and not _is_engine(d))

    def _args(self, pane, resume_id):
        return ["--resume", resume_id] if resume_id else []      # [UNVERIFIED] the resume flag

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen: Hermes's own state.db is in the user's Hermes home, which Lampway never reads (E1.10)")
