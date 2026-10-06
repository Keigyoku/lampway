# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project card operators: refresh the list, pin, set the status, rebuild a page, open a card in the browser."""

from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator


def ui_theme(context) -> str:
    """light when Blender's own UI is light (the Paper theme), else dark: the report opens in the same light as the app."""
    try:
        r, g, b = context.preferences.themes[0].user_interface.wcol_regular.inner[:3]
    except (AttributeError, IndexError):
        return "dark"
    return "light" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else "dark"


def _st():
    from mixar.modules.cards.core import state
    state.ensure_running()
    return state


class LAMPWAY_OT_cards_refresh(Operator):
    """Read the project cards from the server"""
    bl_idname = "lampway.cards_refresh"
    bl_label = "Refresh cards"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        _st().refresh()
        return {"FINISHED"}


class LAMPWAY_OT_cards_pin(Operator):
    """Pin the card so it never archives itself"""
    bl_idname = "lampway.cards_pin"
    bl_label = "Pin card"
    bl_options = {"INTERNAL"}
    card_id: StringProperty()
    pinned: BoolProperty(default=True)

    def execute(self, context):
        st = _st()
        cid, pinned = self.card_id, self.pinned
        st.PUMP.later(lambda: st.request("POST", f"/app/cards/{cid}", {"pinned": pinned}), lambda ok, v: st.refresh() if ok else st.CACHE.update(message=str(v)))
        return {"FINISHED"}


class LAMPWAY_OT_cards_status(Operator):
    """Mark the card active, done or archived (metadata only: its pages and media stay)"""
    bl_idname = "lampway.cards_status"
    bl_label = "Card status"
    bl_options = {"INTERNAL"}
    card_id: StringProperty()
    status: EnumProperty(items=[("active", "Active", ""), ("done", "Done", ""), ("archived", "Archived", "")])

    def execute(self, context):
        st = _st()
        cid, status = self.card_id, self.status
        st.PUMP.later(lambda: st.request("POST", f"/app/cards/{cid}", {"status": status}), lambda ok, v: st.refresh() if ok else st.CACHE.update(message=str(v)))
        return {"FINISHED"}


class LAMPWAY_OT_cards_rebuild(Operator):
    """Rebuild this card's page from the ledger (the page is generated: change the data, not the page)"""
    bl_idname = "lampway.cards_rebuild"
    bl_label = "Rebuild page"
    bl_options = {"INTERNAL"}
    card_id: StringProperty()
    kind: EnumProperty(items=[("design_versions", "Design rounds", ""), ("motion_tests", "Motion tests", ""), ("receipt", "Receipt", "")])
    piece: StringProperty()

    def execute(self, context):
        st = _st()
        body = {"card": self.card_id, "kind": self.kind, "piece": self.piece or self.card_id}
        st.PUMP.later(lambda: st.request("POST", "/app/cards/build", body), lambda ok, v: st.refresh() if ok else st.CACHE.update(message=str(v)))
        return {"FINISHED"}


class LAMPWAY_OT_cards_open(Operator):
    """Open this card's page in your browser (served on its own local origin; Blender never renders it)"""
    bl_idname = "lampway.cards_open"
    bl_label = "Open card"
    bl_options = {"INTERNAL"}
    card_id: StringProperty()
    step: IntProperty(default=0, min=0)

    def execute(self, context):
        import webbrowser
        st = _st()
        cid, step = self.card_id, self.step

        def done(ok, value):
            if ok:
                webbrowser.open(value["url"])
            else:
                st.CACHE.update(message=str(value))
        theme = ui_theme(context)
        st.PUMP.later(lambda: st.request("GET", f"/app/cards/{cid}/open?step={step}&theme={theme}"), done)
        return {"FINISHED"}


classes = (LAMPWAY_OT_cards_refresh, LAMPWAY_OT_cards_pin, LAMPWAY_OT_cards_status, LAMPWAY_OT_cards_rebuild, LAMPWAY_OT_cards_open)
