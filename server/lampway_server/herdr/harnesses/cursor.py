# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cursor's agent CLI (`cursor-agent`): the user's own Cursor agent, in a Lampway pane.

Resume: `--resume <chatId>`. Bypass (the user's tick only): `--force` [UNVERIFIED]. Lampway's tools: a project `mcp.json`
[UNVERIFIED]; that file is the user's own and shared by every pane in the project, so only the per-pane file is written here and no
flag points the agent at it yet. Observation: the screen. Cursor also speaks ACP.
"""
from .base import Adapter, Observer


class Cursor(Adapter):
    id = "cursor"
    label = "Cursor agent"
    binary = "cursor-agent"
    install_hint = "install Cursor's agent CLI (cursor-agent) with Cursor's own installer"   # [UNVERIFIED] no command recorded
    status_argv = ("status",)                                                               # [UNVERIFIED] the status subcommand
    BYPASS = ("--force",)                                                                   # [UNVERIFIED] the flag that skips its prompts

    def _args(self, pane, resume_id):
        return (["--resume", resume_id] if resume_id else []) + self._bypass(pane)

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen")
