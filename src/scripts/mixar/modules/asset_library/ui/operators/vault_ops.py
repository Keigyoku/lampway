# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor's operators (specs/asset_library/asset_ui_editor.md section 4): search, facets, selection, paging, place, rate, compare, find like this, show in
folder, copy, save a search, and the pop-out window. Network calls run off the main thread through the session's pump; placing is ``lampway_tools.api.asset_place`` (one undo
step, the asset's record read from the server)."""

import os

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from mixar.modules.asset_library import constants as K


def _ses():
    from mixar.modules.asset_library.core import session
    session.ensure_running()
    return session


def _redraw():
    for area in _ses().vault_areas():
        area.tag_redraw()


class MIXAR_OT_asset_library_search(Operator):
    """Search the Vault now"""
    bl_idname = "mixar.asset_library_search"
    bl_label = "Search"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        _ses().VM.submit()
        return {"FINISHED"}


class MIXAR_OT_asset_library_toggle_facet(Operator):
    """Filter by this value (click again to remove the filter)"""
    bl_idname = "mixar.asset_library_toggle_facet"
    bl_label = "Filter"
    bl_options = {"INTERNAL"}
    facet: StringProperty()
    value: StringProperty()

    def execute(self, context):
        ses = _ses()
        if self.facet == "kind":
            context.window_manager.mixar_lib.kind = "ALL" if ses.VM.kind == self.value else self.value.upper()
        else:
            ses.VM.toggle_facet(self.facet, self.value)
        return {"FINISHED"}


class MIXAR_OT_asset_library_select(Operator):
    """Select this asset (Ctrl adds or removes it, Shift selects the range)"""
    bl_idname = "mixar.asset_library_select"
    bl_label = "Select"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty()
    mode: EnumProperty(items=[("set", "Set", ""), ("toggle", "Toggle", ""), ("range", "Range", "")], default="set")

    def invoke(self, context, event):
        self.mode = "toggle" if event.ctrl else ("range" if event.shift else "set")
        return self.execute(context)

    def execute(self, context):
        _ses().VM.select(self.asset_id, mode=self.mode)
        _redraw()
        return {"FINISHED"}


class MIXAR_OT_asset_library_page(Operator):
    """Show the next or the previous page"""
    bl_idname = "mixar.asset_library_page"
    bl_label = "Page"
    bl_options = {"INTERNAL"}
    direction: EnumProperty(items=[("NEXT", "Next", ""), ("PREV", "Previous", "")])

    def execute(self, context):
        vm = _ses().VM
        vm.next_page() if self.direction == "NEXT" else vm.prev_page()
        return {"FINISHED"}


class MIXAR_OT_asset_library_place(Operator):
    """Put this asset into the scene the way its kind needs (one undo step)"""
    bl_idname = "mixar.asset_library_place"
    bl_label = "Place in scene"
    bl_options = {"REGISTER"}
    asset_id: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        from mixar.modules.lampway_tools import api
        vm = _ses().VM
        aid = self.asset_id or vm.active
        record = vm.detail if vm.detail and vm.detail.get("id") == aid else None
        res = api.asset_place(asset_id=aid, asset=record) if record else api.asset_place(asset_id=aid)
        if not res.get("ok"):
            self.report({"ERROR"}, f"{res.get('error')} ({'; '.join(res.get('help') or [])})")
            return {"CANCELLED"}
        names = ", ".join(p["name"] for p in res["placed"] if p.get("name"))
        self.report({"INFO"}, f"Placed {names}" + (f". Keep the credit: {res['attribution']}" if res.get("attribution") else ""))
        return {"FINISHED"}


class MIXAR_OT_asset_library_rate(Operator):
    """Rate this asset (your stars always win over an agent's)"""
    bl_idname = "mixar.asset_library_rate"
    bl_label = "Rate"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty()
    stars: IntProperty(min=1, max=5, default=3)

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        aid, stars = self.asset_id, self.stars

        def done(ok, value):
            if ok and ses.VM.active == aid:
                ses.VM.refresh_detail()
        ses.PUMP.later(lambda: LC.rate(aid, stars=stars), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_compare_add(Operator):
    """Add this asset to the comparison (the last two are compared)"""
    bl_idname = "mixar.asset_library_compare_add"
    bl_label = "Compare"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty()

    def execute(self, context):
        _ses().VM.compare_add(self.asset_id)
        _redraw()
        return {"FINISHED"}


class MIXAR_OT_asset_library_find_similar(Operator):
    """Find assets like this one (runs on this machine)"""
    bl_idname = "mixar.asset_library_find_similar"
    bl_label = "Find like this"
    bl_options = {"INTERNAL"}
    asset_id: StringProperty()
    name: StringProperty()

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        aid, name = self.asset_id, self.name or self.asset_id

        def done(ok, value):
            if ok:
                ses.VM.show_similar(name, value.get("items") or [])
            else:
                ses.VM.message = str(value)
        ses.PUMP.later(lambda: LC.similar([aid]), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_open_folder(Operator):
    """Open the folder that holds this file (the file itself is never changed)"""
    bl_idname = "mixar.asset_library_open_folder"
    bl_label = "Show in folder"
    bl_options = {"INTERNAL"}
    path: StringProperty()

    def execute(self, context):
        folder = os.path.dirname(self.path)
        if not os.path.isdir(folder):
            self.report({"ERROR"}, "the folder is gone: re-run the Vault's verify")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=folder)
        return {"FINISHED"}


class MIXAR_OT_asset_library_copy(Operator):
    """Copy to the clipboard"""
    bl_idname = "mixar.asset_library_copy"
    bl_label = "Copy"
    bl_options = {"INTERNAL"}
    text: StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.text
        return {"FINISHED"}


class MIXAR_OT_asset_library_save_search(Operator):
    """Keep this search in the Vault under a name"""
    bl_idname = "mixar.asset_library_save_search"
    bl_label = "Save search"
    bl_options = {"INTERNAL"}
    name: StringProperty(name="Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        q = {k: v for k, v in ses.VM.payload().items() if k not in ("cursor", "include", "facets")}
        name = self.name or ses.VM.text or "search"
        ses.PUMP.later(lambda: LC.collect(action="save_search", name=name, query=q), lambda ok, value: None)
        return {"FINISHED"}


class MIXAR_OT_asset_library_initial_import(Operator):
    """Choose a folder to add to the Vault: it is read and previewed first; nothing is imported until you confirm. Files stay where they are"""
    bl_idname = "mixar.asset_library_initial_import"
    bl_label = "Initial import"
    bl_options = {"INTERNAL"}
    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        paths = [os.path.normpath(self.directory)]
        ses.VM.import_scanning(paths)

        def done(ok, value):
            ses.VM.import_previewed(value) if ok else ses.VM.import_failed(str(value))
        ses.PUMP.later(lambda: LC.scan(paths), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_import_confirm(Operator):
    """Import what the preview listed (the files are referenced where they are, never moved or changed)"""
    bl_idname = "mixar.asset_library_import_confirm"
    bl_label = "Import"
    bl_options = {"INTERNAL"}
    cancel: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        if self.cancel:
            ses.VM.importing = {"state": "idle"}
            return {"FINISHED"}
        scan_id = ses.VM.import_confirmable()
        if not scan_id:
            self.report({"ERROR"}, "there is no preview to import: choose a folder with Initial import first")
            return {"CANCELLED"}
        ses.VM.import_started()

        def done(ok, value):
            ses.VM.import_done(value) if ok else ses.VM.import_failed(str(value))
        ses.PUMP.later(lambda: LC.import_scan(scan_id), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_open_window(Operator):
    """Open the Asset Vault in its own window (a second press brings it to the front)"""
    bl_idname = "mixar.asset_library_open_window"
    bl_label = "Asset Vault Window"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.window is not None and context.screen is not None

    def execute(self, context):
        for win in context.window_manager.windows:
            if win != context.window and len(win.screen.areas) == 1 and win.screen.areas[0].type == K.SPACE:
                self.report({"INFO"}, "The Asset Vault window is already open")       # Python cannot raise a window; one window at a time all the same
                return {"FINISHED"}
        area = max(context.screen.areas, key=lambda a: a.width * a.height)
        old = area.ui_type
        area.ui_type = K.SPACE
        try:
            with context.temp_override(area=area, region=next(r for r in area.regions if r.type == "WINDOW")):
                res = bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
        finally:
            area.ui_type = old
        return {"FINISHED"} if "FINISHED" in res else {"CANCELLED"}


classes = (MIXAR_OT_asset_library_search, MIXAR_OT_asset_library_toggle_facet, MIXAR_OT_asset_library_select, MIXAR_OT_asset_library_page,
           MIXAR_OT_asset_library_place, MIXAR_OT_asset_library_rate, MIXAR_OT_asset_library_compare_add, MIXAR_OT_asset_library_find_similar,
           MIXAR_OT_asset_library_open_folder, MIXAR_OT_asset_library_copy, MIXAR_OT_asset_library_save_search, MIXAR_OT_asset_library_initial_import,
           MIXAR_OT_asset_library_import_confirm, MIXAR_OT_asset_library_open_window)
