# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators of the Vault's inspection views (specs/asset_library/asset_ui_views.md section 5): two clips aligned on one scrub bar, the boards list, a board opened on
the canvas. Every server call runs off the main thread through the session's pump."""

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator


def _ses():
    from mixar.modules.asset_library.core import session
    session.ensure_running()
    return session


def _redraw():
    for area in _ses().vault_areas():
        area.tag_redraw()


class MIXAR_OT_asset_library_align(Operator):
    """Play the two compared clips on one scrub bar, lined up by their first frame, by time, or by where each first moves"""
    bl_idname = "mixar.asset_library_align"
    bl_label = "Align clips"
    bl_options = {"INTERNAL"}
    mode: EnumProperty(items=[("START", "Start", "Frame 0 with frame 0"), ("TIME", "Time", "By timestamp"), ("MOTION", "Motion", "Where each clip first moves")])

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        vm = ses.VM
        ids = ([vm.active] if vm.active not in vm.compare else []) + list(vm.compare)
        if len(ids) < 2:
            self.report({"INFO"}, "Press Compare on a second clip first")
            return {"CANCELLED"}
        a, b, mode = ids[-2], ids[-1], self.mode.lower()

        def done(ok, value):
            if ok:
                vm.load_pairs(value)
            else:
                vm.message = str(value)
            _redraw()
        ses.PUMP.later(lambda: LC.clip_align(a, b, mode), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_boards(Operator):
    """Read the Vault's boards"""
    bl_idname = "mixar.asset_library_boards"
    bl_label = "Refresh boards"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()

        def done(ok, value):
            if ok:
                ses.VM.boards = [c for c in value.get("collections") or [] if c.get("kind") == "board"]
            _redraw()
        ses.PUMP.later(lambda: LC.collect(action="list"), done)
        return {"FINISHED"}


class MIXAR_OT_asset_library_board(Operator):
    """Open this board on the canvas: drag a tile to place it (the place is saved), the wheel zooms, the middle button drags, Esc closes"""
    bl_idname = "mixar.asset_library_board"
    bl_label = "Open board"
    bl_options = {"INTERNAL"}
    board_id: StringProperty()

    def _open(self, context, modal):
        from mixar.modules.asset_library.core import canvas_view as CV
        from mixar.modules.lampway_tools import library_client as LC
        ses = _ses()
        board = self.board_id
        win, area = context.window, context.area

        def done(ok, value):
            if not ok:
                ses.VM.message = str(value)
                return
            CV.install()
            CV.open_board(board, value.get("items") or [])
            if modal and win is not None and area is not None:
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.mixar.asset_library_canvas("INVOKE_DEFAULT", action="MODAL")
            CV.redraw()
        ses.PUMP.later(lambda: LC.collect(action="get", collection=board), done)

    def invoke(self, context, event):
        self._open(context, True)
        return {"FINISHED"}

    def execute(self, context):
        self._open(context, False)
        return {"FINISHED"}


classes = (MIXAR_OT_asset_library_align, MIXAR_OT_asset_library_boards, MIXAR_OT_asset_library_board)
