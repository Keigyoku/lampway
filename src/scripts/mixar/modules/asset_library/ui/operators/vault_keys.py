# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's hotkeys (specs/asset_library/asset_ui_editor.md section 6.8; the table and its meaning: ``core/hotkeys.py``). One operator, gated on the mouse being
over a Vault area, bound in the add-on keyconfig's "User Interface" keymap (the keymap the Vault's UI-only region polls) so a keyconfig reload keeps them (CLAUDE.md, the keyconfig-reload rule)."""

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from mixar.modules.asset_library import constants as K
from mixar.modules.asset_library.core import hotkeys as H

_keymaps = []


class MIXAR_OT_asset_library_hotkey(Operator):
    """Vault hotkey: 1-5 rate, X reject, P pick, Space play, / search, F find like this, C compare, Enter place"""
    bl_idname = "mixar.asset_library_hotkey"
    bl_label = "Asset Vault Hotkey"
    bl_options = {"INTERNAL"}
    action: EnumProperty(items=[(a, a.replace("_", " ").title(), "") for a in H.ACTIONS])

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == K.SPACE

    def invoke(self, context, event):
        if self.action == "SEARCH":
            return context.window_manager.invoke_props_dialog(self, title="Search the Asset Vault")
        return self.execute(context)

    def draw(self, context):
        self.layout.activate_init = True
        self.layout.prop(context.window_manager.mixar_lib, "query", text="", icon="VIEWZOOM")

    def execute(self, context):
        from mixar.modules.asset_library.core import session
        from mixar.modules.lampway_tools import library_client as LC
        session.ensure_running()
        step = H.plan(self.action, session.VM)
        if step is None:
            self.report({"INFO"}, "Select an asset first")
            return {"CANCELLED"}
        verb, args = step
        if verb == "rate":
            aid = args.pop("asset_id")
            session.PUMP.later(lambda: LC.rate(aid, **args), lambda ok, v: session.VM.refresh_detail() if ok else None)
        elif verb == "play":
            session.VM.flipbook.toggle()
        elif verb == "search":
            session.VM.submit()
        elif verb == "find":
            bpy.ops.mixar.asset_library_find_similar(asset_id=args["asset_id"], name=args["name"])
        elif verb == "compare":
            session.VM.compare_add(args["asset_id"])
        elif verb == "place":
            return bpy.ops.mixar.asset_library_place(asset_id=args["asset_id"])
        for area in session.vault_areas():
            area.tag_redraw()
        return {"FINISHED"}


classes = (MIXAR_OT_asset_library_hotkey,)


def register():
    for cls in classes:
        if not cls.is_registered:
            bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon if bpy.context.window_manager else None
    if kc is None:
        return
    km = kc.keymaps.new(name="User Interface", space_type="EMPTY", region_type="WINDOW")
    for k in H.KEYMAP:
        kmi = km.keymap_items.new(MIXAR_OT_asset_library_hotkey.bl_idname, k["type"], "PRESS")
        kmi.properties.action = k["action"]
        _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()
    for cls in reversed(classes):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
