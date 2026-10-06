# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor's transient state on the WindowManager (``window_manager.mixar_lib``, specs/asset_library/asset_ui_editor.md section 4): the search text, kind, sort,
view and tile size. Nothing is saved with the file; saved searches and boards live in the Vault itself."""

import bpy
from bpy.props import EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from mixar.modules.asset_library import constants as K


def _session():
    from mixar.modules.asset_library.core import session
    session.ensure_running()
    return session


def _on_query(self, context):
    _session().VM.type_text(self.query)


def _on_kind(self, context):
    _session().VM.set_kind(None if self.kind == "ALL" else self.kind.lower())


def _on_sort(self, context):
    _session().VM.set_sort(None if self.sort == "score" else self.sort)


class MIXAR_PG_asset_library(PropertyGroup):
    query: StringProperty(name="Search", description="Search the Vault: names, tags and terms (Enter searches at once)", options={"SKIP_SAVE", "TEXTEDIT_UPDATE"},
                          update=_on_query)
    kind: EnumProperty(name="Kind", items=[("ALL", "All", "Every kind")] + [(k.upper(), k.replace("_", " ").title(), f"Only {k.replace('_', ' ')} assets") for k in K.KINDS],
                       default="ALL", options={"SKIP_SAVE"}, update=_on_kind)
    sort: EnumProperty(name="Sort", items=[(s, s.title(), f"Sort by {s}") for s in K.SORTS], default="score", options={"SKIP_SAVE"}, update=_on_sort)
    view: EnumProperty(name="View", items=[("GRID", "Grid", "Tiles with big previews", "IMGDISPLAY", 0), ("LIST", "List", "One row per asset", "LINENUMBERS_ON", 1)],
                       default="GRID", options={"SKIP_SAVE"})
    tile_size: IntProperty(name="Tile size", description="Thumbnail size in pixels", min=K.TILE_MIN, max=K.TILE_MAX, default=K.TILE_DEFAULT, subtype="PIXEL",
                           options={"SKIP_SAVE"})


classes = (MIXAR_PG_asset_library,)


def register():
    for cls in classes:
        if not cls.is_registered:
            bpy.utils.register_class(cls)
    if not hasattr(bpy.types.WindowManager, "mixar_lib"):
        bpy.types.WindowManager.mixar_lib = PointerProperty(type=MIXAR_PG_asset_library)


def unregister():
    if hasattr(bpy.types.WindowManager, "mixar_lib"):
        del bpy.types.WindowManager.mixar_lib
    for cls in reversed(classes):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
