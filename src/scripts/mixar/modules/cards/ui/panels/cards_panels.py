# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The project cards in the Asset Vault editor (specs/mrmak/09-report-cards.md section 4): one row per card, freshly touched first, its pages as buttons that open in the
browser. ``draw`` reads the cache only; the list arrives through Refresh."""

from bpy.types import Panel


def draw_cards(layout) -> None:
    from mixar.modules.cards.core import state as ST
    head = layout.row(align=True)
    head.label(text="Project cards")
    head.operator("lampway.cards_refresh", text="", icon="FILE_REFRESH")
    if ST.CACHE["status"] == "offline":
        layout.label(text=ST.CACHE["message"], icon="ERROR")
    if not ST.CACHE["cards"]:
        layout.label(text="No cards yet: build one with lampway_cards", icon="INFO")
        return
    for c in ST.CACHE["cards"]:
        box = layout.box()
        row = box.row(align=True)
        row.label(text=c["title"])
        row.label(text=c["status"])
        pin = row.operator("lampway.cards_pin", text="", icon="PINNED" if c.get("pinned") else "UNPINNED", emboss=False)
        pin.card_id, pin.pinned = c["id"], not c.get("pinned")
        if c.get("steps"):
            box.label(text=", ".join(c["steps"]))
            pages = box.row(align=True)
            for i, name in enumerate(c["steps"]):
                op = pages.operator("lampway.cards_open", text=name, icon="URL")
                op.card_id, op.step = c["id"], i


class MIXAR_ASSETS_PT_cards(Panel):
    bl_label = "Project cards"
    bl_idname = "MIXAR_ASSETS_PT_cards"
    bl_space_type = "MIXAR_ASSETS"
    bl_region_type = "WINDOW"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_cards(self.layout)


classes = (MIXAR_ASSETS_PT_cards,)
