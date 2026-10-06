# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Scene properties of the Lampway tools panel (``scene.lampway_tools``). The fields only hold what the buttons pass
to ``mixar.modules.lampway_tools.api``; the configuration of record lives in ``scene['lampway_qa']`` and the
rulings directory, so a scene saved with the panel closed loses nothing."""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup

from mixar.modules.lampway_tools import runner


def _studio_items(self, context):
    from mixar.modules.lampway_tools import studio_state
    rows = studio_state.STATE["actions"] or [{"id": "tripo.state", "label": "Read the Studio state (refresh first)"}]
    return [(a["id"], a["label"][:40], a["label"]) for a in rows]


_ITEMS = []


def _prompt_items(self, context):
    from mixar.modules.lampway_tools import studio_state
    rows = studio_state.PROMPTS["templates"] or [{"id": "", "title": "(refresh the templates)", "description": ""}]
    _ITEMS[:] = [(t["id"], t["title"][:48], t.get("description", "")[:200]) for t in rows]      # Blender keeps pointers into this list: it must outlive the call
    return _ITEMS


class PromptVar(PropertyGroup):
    """One row of the generated variable form: the value is held as text and typed on use (the server validates it)."""
    name: StringProperty()
    kind: StringProperty()
    value: StringProperty()
    vmin: FloatProperty()
    vmax: FloatProperty()
    choices: StringProperty(description="enum values, | separated")
    help: StringProperty()


class PromptLibraryRow(PropertyGroup):
    """One template of the prompt library list (facelift contract 08), mirrored from the server by lampway.prompts_refresh."""
    template_id: StringProperty()
    title: StringProperty()
    version: StringProperty()
    media: StringProperty()
    price: StringProperty(description="Mean billed price of this version, or 'no runs yet'")
    hover: StringProperty(description="Runs and rating of this version")


def _library_filter_items(self, context):
    rows = getattr(self, "prompt_library", ())
    counts = {"image": sum(1 for r in rows if r.media == "image"), "video": sum(1 for r in rows if r.media == "video")}
    _FILTER[:] = [("ALL", f"All {len(rows)}", "Every template"), ("IMAGE", f"Image {counts['image']}", "Image templates"),
                  ("VIDEO", f"Video {counts['video']}", "Video templates")]
    return _FILTER


_FILTER = []


def _library_pick(self, context):
    """Choosing a row chooses its template for the form below."""
    rows = self.prompt_library
    if 0 <= self.prompt_library_index < len(rows):
        try:
            self.prompt_template = rows[self.prompt_library_index].template_id
        except TypeError:   # the template enum has not been refreshed with this id yet
            pass


def _tool_items(self, context):
    return [(t.name, t.name, t.summary) for t in runner.TOOLS.values()]


class StudioPlanArg(PropertyGroup):
    """One typed argument of a Studio action's plan (facelift contract 06: the plan form has no JSON field)."""
    key: StringProperty(name="Argument", description="The argument's name, as the Studio action names it (e.g. front, polycount)")
    kind: EnumProperty(name="Kind", items=[('TEXT', "Text", "Words"), ('NUMBER', "Number", "A number"),
                                           ('FILE', "File", "A file inside the project root"), ('FLAG', "Yes / no", "On or off")])
    text: StringProperty(name="Text")
    number: FloatProperty(name="Number")
    path: StringProperty(name="File", subtype='FILE_PATH', description="Inside the project root")
    flag: BoolProperty(name="On")


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
    prompt_template: EnumProperty(name="Template", items=_prompt_items, description="A prompt-library template (image or video)")
    prompt_library: CollectionProperty(type=PromptLibraryRow)
    prompt_library_index: IntProperty(default=0, update=_library_pick)
    prompt_library_filter: EnumProperty(name="Show", items=_library_filter_items)
    prompt_vars: CollectionProperty(type=PromptVar)
    prompt_model: StringProperty(name="Model", description="Render for this model (adapters rename references, cut phrases, warn on length); empty = the template's default")
    prompt_preview: StringProperty(name="Preview")
    prompt_job_id: StringProperty(name="Job id", description="The job to rate")
    prompt_rating: IntProperty(name="Rating", min=1, max=5, default=3)
    prompt_note: StringProperty(name="Note")
    studio_action: EnumProperty(name="Studio action", items=_studio_items)
    studio_args: StringProperty(name="Arguments", default="{}", description="The action's arguments as JSON, paths inside the project root")  # kept for old files; the panel draws studio_plan_args
    studio_plan_args: CollectionProperty(type=StudioPlanArg)
    studio_plan_args_index: IntProperty(default=0)
    feature: EnumProperty(name="Feature", items=[
        ("retopo", "Retopology", "A new all-quad mesh near a target face count"), ("uv_unwrap", "UV unwrap", "A packed UV layout on a new mesh"),
        ("segment_mesh", "Mesh segment", "Split into part objects"), ("auto_rig", "Auto rig", "A UE-named humanoid armature"),
        ("mesh_prep", "Mesh prep", "Branch, hash and repair defects"), ("asset_acceptance", "Asset acceptance", "Identity, orientation, geometry, materials gates"),
        ("detail_normals", "Detail normals", "Tiling detail normals on a textured_atlas material"),
        ("image_to_3d", "Image to 3D", "A mesh from views"), ("render_video", "Render video", "A turntable or fly-through")])
    feature_args: StringProperty(name="Options", description='The feature\'s other arguments as JSON, e.g. {"target_faces": 3000}; engine "studio:tripo" asks for approval and clicks nothing')
    tool_args: StringProperty(name="Arguments", description="The tool's arguments, space separated (paths relative to the project root)")
    clip_height: FloatProperty(name="Figure height (m)", default=0.0, min=0.0, description="0 = the deform mesh's rest height, else head bone to foot bone")
    last_message: StringProperty(name="Last result", default="")


classes = [PromptVar, StudioPlanArg, PromptLibraryRow, LampwayToolsProps]


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
