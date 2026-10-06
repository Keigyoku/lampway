# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look panel's one field: which UE profile the mode applies (``scene.lampway_ue_look.profile``; empty = the shipped
engine-defaults profile). Whether the mode is on is the scene's receipt key, not a property: the receipt is the record."""

import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import PropertyGroup


class LampwayUELookProps(PropertyGroup):
    profile: StringProperty(name="UE profile", subtype="FILE_PATH", default="",
                            description="A lampway.ue-profile/1 file (the UE editor leg's live dump); empty = the shipped engine defaults, which are not the project")


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
