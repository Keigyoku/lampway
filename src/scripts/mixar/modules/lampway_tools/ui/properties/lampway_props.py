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
    # ---- Mesh-paint texturing
    mp_mesh: StringProperty(name="Rebuilt mesh", subtype="FILE_PATH", description="The rebuild's patched UV mesh (fbx) the clay renders are made from")
    mp_design_dir: StringProperty(name="Design plates", subtype="DIR_PATH", description="V3's plates: Front.png, Back.png, Left.png, Right.png")
    mp_recipe: StringProperty(name="Recipe", subtype="FILE_PATH")
    mp_relief_dir: StringProperty(name="Relief views", subtype="DIR_PATH")
    mp_out_root: StringProperty(name="Rebuild outputs", subtype="DIR_PATH", description="The rebuild's out_root (holds patched/)")
    mp_tag: StringProperty(name="Rebuild tag", default="p1", description="The rebuild whose mesh and maps the projection reuses")
    mp_template: StringProperty(name="Template material")
    mp_lift: FloatProperty(name="Lift", unit="LENGTH")
    mp_live: BoolProperty(name="Generate for real", default=False,
                          description="Off = a dry run (the image backend verifies its settings, nothing is generated or spent). On needs the owner's own arming of the backend")
    mp_albedo: BoolProperty(name="Albedo base colour", default=True, description="The projected albedo as the live material's base colour")
    # ---- other tools
    tool: EnumProperty(name="Tool", items=_tool_items)
    feature: EnumProperty(name="Feature", items=[
        ("retopo", "Retopology", "A new all-quad mesh near a target face count"), ("uv_unwrap", "UV unwrap", "A packed UV layout on a new mesh"),
        ("segment_mesh", "Mesh segment", "Split into part objects"), ("auto_rig", "Auto rig", "A UE-named humanoid armature"),
        ("mesh_prep", "Mesh prep", "Branch, hash and repair defects"), ("asset_acceptance", "Asset acceptance", "Identity, orientation, geometry, materials gates"),
        ("image_to_3d", "Image to 3D", "A mesh from views"), ("render_video", "Render video", "A turntable or fly-through")])
    feature_args: StringProperty(name="Options", description='The feature\'s other arguments as JSON, e.g. {"target_faces": 3000}; engine "studio:tripo" asks for approval and clicks nothing')
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
