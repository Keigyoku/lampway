# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look panel: the profile, the cube and its sidecar (file pickers), the cube's status glyph and the mode toggle. Styling
is the theme's (stock layout widgets and icons, no colours of its own); draw() reads the scene's receipt key and the operators'
cached answers, never a file."""

from bpy.types import Panel

from mixar.modules.lampway_tools.ue import look
from mixar.modules.lampway_tools.ui.operators.ue_look_ops import CACHE, CUBE_STATUS

GLYPH = {"valid": ("CHECKMARK", "Cube valid"), "missing": ("QUESTION", "Cube missing"), "mismatch": ("ERROR", "Cube mismatch")}


class LAMPWAY_PT_ue_look(Panel):
    bl_idname = "LAMPWAY_PT_ue_look"
    bl_label = "UE Look"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        on = bool(scene.get(look.STATE_KEY))
        col = layout.column(align=True)
        col.enabled = not on                                              # the profile and cube are fixed while their look is applied
        p = scene.lampway_ue_look
        col.prop(p, "profile")
        col.prop(p, "cube")
        col.prop(p, "cube_meta")
        if not p.profile:
            layout.label(text="Engine defaults: not the project", icon="INFO")
        state = CUBE_STATUS.get("state") or "missing"
        icon, text = GLYPH[state]
        layout.label(text=text + (f": {CUBE_STATUS.get('why')}"[:80] if state != "valid" and CUBE_STATUS.get("why") else ""), icon=icon)
        layout.operator("lampway.ue_look_toggle", text="UE Look: on" if on else "UE Look: off", icon="HIDE_OFF" if on else "HIDE_ON", depress=on)
        if CACHE["line"]:
            layout.label(text=CACHE["line"][:90])


classes = [LAMPWAY_PT_ue_look]
