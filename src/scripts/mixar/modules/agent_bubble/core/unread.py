# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the agent said while the chat was closed (a glance cue the top bar's agent chip shows; facelift 04/05)."""

_SEEN = {"count": None}


def closed(scene) -> None:
    """The chat closed: everything up to now has been seen."""
    _SEEN["count"] = len(getattr(scene, "mixie_chat_messages", None) or [])


def opened() -> None:
    _SEEN["count"] = None


def count(scene) -> int:
    seen = _SEEN["count"]
    if seen is None:
        return 0
    messages = list(getattr(scene, "mixie_chat_messages", None) or [])
    return sum(1 for m in messages[seen:] if getattr(m, "sender", "") == "AGENT")
