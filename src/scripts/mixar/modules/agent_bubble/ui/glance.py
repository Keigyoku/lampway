# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The agent's glance cues while the chat is closed and the floating pill is off (the captain, facelift contracts 04
and 05): the top bar's agent chip, which opens the chat. Inside the chat the native header carries the same cues
(agent_ui_draw.cc: agent_ui_draw_header_glance). DESIGN v2's cues: the Spark in its state (a contract 14 preview glyph), the state in words (the pill's own
status, queue clock included), how many agents run, and what is unread. docs/reports/facelift/pill_parity.md lists
every datum the pill showed and where it lives now."""

from mixar.modules.agent_bubble.ui.header import _get_status, _pill_text

#: The pill's status colour -> the Spark state glyph (contract 05's states).
STATE_GLYPH = {"green": "agent_working", "blue": "agent_blocked", "grey": "agent_idle", "red": "agent_failed"}


def preview(name):
    """The 16 px glyph's icon id; 0 (no icon) when previews cannot load (a header draw must never raise)."""
    try:
        from mixar.modules.common.lampway_icons import icon_id
        return icon_id(name, 16)
    except Exception:  # noqa: BLE001
        return 0


def _glyph(scene, status, unread):
    if getattr(scene, "mixie_chat_state", "") == "CONNECTING":
        return "agent_paused"
    if status.colour == "grey" and unread:
        return "agent_unread"
    return STATE_GLYPH.get(status.colour, "agent_idle")


def running_agents(wm) -> int:
    return sum(1 for c in getattr(wm, "mixar_agent_cards", None) or [] if getattr(c, "status", "") == "WORKING")


def _extras(wm, unread) -> list:
    out = []
    n = running_agents(wm)
    if n:
        out.append(f"{n} agent{'s' if n != 1 else ''} running")
    if unread:
        out.append(f"{unread} unread")
    return out


def draw_topbar(layout, scene, wm, island_open: bool, unread=0) -> None:
    """The way back into a closed chat: the same cues on one button. Nothing while the chat is open."""
    if island_open:
        return
    status = _get_status(scene)
    words = " · ".join([_pill_text(status), *_extras(wm, unread)])
    layout.operator("mixar.agent_bubble_open_window", text=words, icon_value=preview(_glyph(scene, status, unread)),
                    emboss=False)
