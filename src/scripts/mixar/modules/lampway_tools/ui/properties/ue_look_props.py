# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look panel's fields (``scene.lampway_ue_look``): which UE profile the mode applies (empty = the shipped engine
defaults) and the tonemapper cube and its sidecar, generated on the UE side (empty = the profile's own tonemap_cube /
tonemap_cube_meta). Changing a path re-validates the cube once (the status glyph); draw() never reads a file. Whether the mode is
on is the scene's receipt key, not a property: the receipt is the record."""

import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import PropertyGroup


def _refresh(self, context):
    from mixar.modules.lampway_tools.ui.operators import ue_look_ops
    ue_look_ops.refresh(context.scene)


class LampwayUELookProps(PropertyGroup):
    profile: StringProperty(name="UE profile", subtype="FILE_PATH", default="", update=_refresh,
                            description="A lampway.ue-profile/1 file (the UE editor leg's live dump); empty = the shipped engine defaults, which are not the project")
    cube: StringProperty(name="Tonemapper cube", subtype="FILE_PATH", default="", update=_refresh,
                         description="The .cube generated on the UE side (Lampway reads it, never copies it); empty = the profile's tonemap_cube")
    cube_meta: StringProperty(name="Cube sidecar", subtype="FILE_PATH", default="", update=_refresh,
                              description="The cube's JSON sidecar (engine version, tonemapper settings, generator, sha256); empty = the profile's tonemap_cube_meta")


classes = [LampwayUELookProps]


def register():
    for cls in classes:
        if not cls.is_registered:
            bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "lampway_ue_look"):
        bpy.types.Scene.lampway_ue_look = PointerProperty(type=LampwayUELookProps)


def unregister():
    if hasattr(bpy.types.Scene, "lampway_ue_look"):
        del bpy.types.Scene.lampway_ue_look
    for cls in reversed(classes):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
