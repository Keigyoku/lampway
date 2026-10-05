# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scene properties of the Lampway tools panel (``scene.lampway_tools``). The fields only hold what the buttons pass
to ``mixar.modules.lampway_tools.api``; the configuration of record lives in ``scene['lampway_qa']`` and the
rulings directory, so a scene saved with the panel closed loses nothing."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from mixar.modules.lampway_tools import runner


def _tool_items(self, context):
    return [(t.name, t.name, t.summary) for t in runner.TOOLS.values()]


class LampwayToolsProps(PropertyGroup):
    # ---- Mesh QA
    qa_recipe: StringProperty(name="Recipe", subtype="FILE_PATH", description="The parts recipe json (parts and their motion classes)")
    qa_owner: StringProperty(name="Owner map", subtype="FILE_PATH", description="A .npy of one part index per polygon; empty = the mesh's int face attribute 'part'")
    qa_piece: StringProperty(name="Piece", description="The piece's name; its rulings live in <project root>/<piece>/rulings")
    qa_offset_z: FloatProperty(name="Lift", unit="LENGTH", description="Live frame minus the mesh's own frame in Z (how far the piece was lifted onto the floor)")
    qa_orig_poly: StringProperty(name="Source faces", subtype="FILE_PATH", description="A rebuild's orig_poly .npy (source face per polygon, -1 = patch); empty for a source mesh")
    qa_turn: FloatProperty(name="Turn", description="The rebuild's turn about Z in degrees (patch_holes --turn)")
    close_round: BoolProperty(name="Everything else is intentional", default=False,
                              description="Answer every candidate nobody named 'keep' (his: everything else looks intentional)")
    mislabel_to: StringProperty(name="Relabel to", description="Target parts for the green strokes, as stroke:part pairs, e.g. 0:cuirass_back_plate,1:cape_drape_upper")
    # ---- Rebuild
    rb_source_mesh: StringProperty(name="Source mesh", subtype="FILE_PATH")
    rb_source_owner: StringProperty(name="Source owner", subtype="FILE_PATH")
    rb_relief_dir: StringProperty(name="Relief views", subtype="DIR_PATH")
    rb_plates_dir: StringProperty(name="Plates", subtype="DIR_PATH")
    rb_template: StringProperty(name="Template material", description="The live textured material to copy for the rebuild")
    rb_lift: FloatProperty(name="Lift", unit="LENGTH")
    rb_tag: StringProperty(name="Tag", default="p1", description="A new name for this rebuild; a tag is never overwritten")
    rb_res: EnumProperty(name="Atlas", items=[("2048", "2048", ""), ("4096", "4096", "")], default="2048")
    rb_color_full: BoolProperty(name="Colour at full resolution", default=False)
    rb_ornament: StringProperty(name="Ornament", default="", description="max_tris:reach_px:min_share, e.g. 600:24:0.25 at 4096")
    rb_mesh_gold: BoolProperty(name="Gold from mesh relief", default=False)
    # ---- other tools
    tool: EnumProperty(name="Tool", items=_tool_items)
    tool_args: StringProperty(name="Arguments", description="The tool's arguments, space separated (paths relative to the project root)")
    last_message: StringProperty(name="Last result", default="")


classes = [LampwayToolsProps]


def register():
    for cls in classes:
        if not cls.is_registered:
            bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "lampway_tools"):
        bpy.types.Scene.lampway_tools = PointerProperty(type=LampwayToolsProps)


def unregister():
    if hasattr(bpy.types.Scene, "lampway_tools"):
        del bpy.types.Scene.lampway_tools
    for cls in reversed(classes):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
