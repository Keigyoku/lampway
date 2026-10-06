# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later

"""Explicitly apply the built-in palette without changing other preferences."""

import bpy
from bpy.types import Operator

from mixar.config.brand import PRODUCT_NAME

from ...core.theme_backgrounds import apply_forest_backgrounds


class LAMPWAY_OT_apply_night_theme(Operator):
    """Facelift F2: Night is the default theme and the only one offered here; this applies it to any profile."""
    bl_idname = "lampway.apply_night_theme"
    bl_label = f"Apply {PRODUCT_NAME} Night"
    bl_description = f"Switch to {PRODUCT_NAME} Night, the default theme: night slate and lamplight"

    def execute(self, context):
        from ...core.lampway_night import preset_path
        path = preset_path(bpy.utils.preset_paths("interface_theme"))
        if path is None:
            self.report({'ERROR'}, "Lampway Night is not installed: reinstall Lampway to restore its themes")
            return {'CANCELLED'}
        return bpy.ops.script.execute_preset(filepath=path, menu_idname="USERPREF_MT_interface_theme_presets")


class MIXAR_OT_apply_forest_backgrounds(Operator):
    bl_idname = "mixar.apply_forest_backgrounds"
    bl_label = "Reset Workspace Backgrounds"
    bl_description = (
        "Set Lamplight and Workshop viewport backgrounds to #0F0F0F and both Moodboard "
        "hosts to #1E1E1E; use theme backgrounds and hide Material Preview HDRI backdrops"
    )

    def execute(self, context):
        apply_forest_backgrounds(context.preferences.themes[0], bpy.data.screens)
        return {'FINISHED'}


classes = (LAMPWAY_OT_apply_night_theme, MIXAR_OT_apply_forest_backgrounds)
