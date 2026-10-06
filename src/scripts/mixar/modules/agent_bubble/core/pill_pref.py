# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The "Floating agent pill" preference (the captain, facelift contracts 04 and 05): off by default, for existing
users too. Off, minimising the chat closes it and the top bar's agent chip is the way back; what the pill showed
lives in the chat's header and that chip (ui/glance.py). A persisted config key, like the completion sound."""

from mixar.config.config import add_config, get_config

KEY = "floating_agent_pill"
NOTE_KEY = "floating_agent_pill_note_seen"


def enabled() -> bool:
    return bool(get_config().get(KEY, False))


def set_enabled(on: bool) -> bool:
    ok = add_config(KEY, bool(on))
    if on:
        add_config(NOTE_KEY, True)   # someone who turned it on knows where it is
    return ok


def note_pending() -> bool:
    """The one-time note in the chat header (where the pill went, how to bring it back) is still owed."""
    return not enabled() and not bool(get_config().get(NOTE_KEY, False))


def mark_note_seen() -> None:
    add_config(NOTE_KEY, True)
