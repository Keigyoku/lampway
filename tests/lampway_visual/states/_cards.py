# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the agent card states (contract 05): the Parallel Agents mirror written as the chat's todo slot would leave it, and the Spark's
ring sampled where the painter draws it (the QA dump's `agent_panel_cat` rect; ring radius 29/64 of the chip, DESIGN.md 13)."""

import math


def feed(bpy, records):
    from mixar.modules.agent_panel.core import cards
    wm = bpy.context.window_manager
    wm.mixar_agent_cards.clear()
    for i, (status, name, extra) in enumerate(records):
        card = wm.mixar_agent_cards.add()
        card.task_id, card.name, card.task, card.status = f"t{i}", name, name, status
        for key, value in extra.items():
            setattr(card, key, value)
        card.started_at, card.ended_at = (1.0, 42.0) if status in ("DONE", "FAILED") else (1.0, 0.0)
    wm.mixar_agent_cards_overflow = cards.overflow_label([r[0] for r in records])
    wm.mixar_agent_cards_generation += 1
    wm.mixar_agent_cards_active = len(records)


def ring_point(dump, index, angle):
    """Window pixel on the ring of card `index`'s Spark at `angle` (radians from 3 o'clock, anticlockwise)."""
    cat = next(w["rect"] for w in dump["widgets"] if w.get("surface") == "agent_panel_cat" and w.get("index") == index)
    cx, cy = (cat[0] + cat[2] + 1) / 2, (cat[1] + cat[3] + 1) / 2
    s = min(cat[2] - cat[0] + 1, cat[3] - cat[1] + 1) - 2
    r = 29 / 64 * s
    return (round(cx + r * math.cos(angle)), round(cy + r * math.sin(angle)), 1)


def facts(bpy, dump):
    chevron = [w for w in dump["widgets"] if w.get("surface") == "agent_panel_chevron"]
    names = {w["index"]: w.get("text") for w in dump["widgets"] if w.get("surface") == "agent_panel_card"}
    return {"chevron": chevron[0].get("detail") if chevron else None, "visible": [names[i] for i in sorted(names)]}


def regions(bpy):
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'EXECUTE')
    return {"cards": [region.x, region.y, region.x + region.width, region.y + region.height]}
