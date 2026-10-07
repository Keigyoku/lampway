# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grok (Grok Build, `grok`): the user's own Grok CLI, in a Lampway pane.

Resume: `--resume <id>` (`-c` continues the last one). Bypass: none recorded [UNVERIFIED], so none is ever emitted. Lampway's tools:
`grok mcp add` or config.toml scoped to the pane [UNVERIFIED]; `grok mcp add` writes the user's own config, so only the per-pane file
is written here and no flag points Grok at it yet. Observation: `~/.grok/sessions/` [UNVERIFIED]. Grok also speaks ACP.
"""
from pathlib import Path

from .base import Adapter, Observer


class Grok(Adapter):
    id = "grok"
    label = "Grok"
    binary = "grok"
    install_hint = "install Grok Build's CLI (grok) from xAI"            # [UNVERIFIED] no command recorded
    status_argv = None                                                   # [UNVERIFIED] no login status command recorded

    def observe(self, record):
        return Observer("session_file", str(Path.home() / ".grok" / "sessions"), False, "[UNVERIFIED] Grok's session folder; not read until a fixture confirms it")
