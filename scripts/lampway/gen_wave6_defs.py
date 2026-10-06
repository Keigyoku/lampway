# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write server/lampway_server/agent/wave6_tools.py from api_wave6.py's docstrings (one text, two places) and the param table below.

    python3 scripts/lampway/gen_wave6_defs.py

The pin is tests/lampway_tools/test_wave6_door.py (a description that is not its function's docstring fails)."""
import ast, sys
from pathlib import Path
W = Path(__file__).resolve().parents[2]
src = (W / "src/scripts/mixar/modules/lampway_tools/api_wave6.py").read_text()
tree = ast.parse(src)
docs = {n.name: " ".join(ast.get_docstring(n).split()) for n in tree.body if isinstance(n, ast.FunctionDef) and ast.get_docstring(n)}
tools = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TOOLS")
PATHS = {"motion_generate", "scene_from_image", "modular_character", "playblast_capture", "lod_chain", "glb_optimize", "print_prep", "splat_world", "terrain", "material_palette", "editor_connection_receipt"}
O = "items=_OBJ"
N = 'items={"type": "number"}'
ARR = 'items={"type": "array"}'
PARAMS = {
 "modular_character": ['P("action", desc="manifest | validate | outfit_matrix | hidden_body | export_parts", required=True)', 'P("character_id", required=True)',
    f'P("parts", "array", "manifest: [{{object, role, fixed_or_deforming, wearer_side, bone}}]", {O})', 'P("armature")',
    'P("allowed_outfits", "array", "[[part ids]]", items={"type": "array", "items": {"type": "string"}})', 'P("poses", "string", "rest | wiki8 (default: the manifest\'s)")', 'P("out_dir")'],
 "character_pipeline": ['P("character_id", required=True)', f'P("parts", "array", "[{{name, budget, rigid_bone}}]", required=True, {O})', 'P("mode", desc="plan | record | run")',
    'P("target", desc="unreal_mannequin | metahuman | mixamo | vrm")', 'P("from_stage", "integer")', 'P("to_stage", "integer")', 'P("stage", "integer")',
    'P("gate", desc="pass | fail")', 'P("evidence")', 'P("stage_calls", "object", "{\\"<n>\\": [{tool, args}]}")'],
 "playblast_capture": [f'P("shots", "array", "[{{name, camera, frames: [a, b], duration_s, look_at}}]", required=True, {O})', 'P("out_dir")', 'P("fps", "integer")', 'P("width", "integer")',
    'P("height", "integer")', 'P("engine", desc="workbench | eevee")', 'P("stills", desc="first | last | both | none")', 'P("target_duration_s", "number")',
    'P("scene_objects", "array", "objects that must be visible")'],
 "lod_chain": ['P("object", required=True)', f'P("ratios", "array", {N})', 'P("protect", desc="vertex group never collapsed")', f'P("texture_scale", "array", {N})',
    'P("textures", "array", "texture files to downsize per LOD")', 'P("naming", desc="default {name}_LOD{n}")', 'P("preserve_uv_seams", "boolean")', 'P("out_dir")'],
 "motion_experiment": ['P("brief", "object", "{duration_s, start, end, contact: {time_s, landmark, pose}, action, weapon_hand, preserve}", required=True)', 'P("armature", required=True)',
    'P("variants", "object", "{A: keyed, B: action name, C: action name}")'],
 "secondary_chain_rig": ['P("object", required=True)', 'P("armature", required=True)', 'P("parent_bone", required=True)', 'P("bones", "integer", "2..24, default 4")',
    'P("naming", desc="tail_ | cape_ | hair_ ...")', f'P("region", "array", "[[x, y, z], [x, y, z]] world bounding box", {ARR})', 'P("preview_constraint", desc="damped_track | none")', 'P("colliders", "boolean")'],
 "cloth_garment_sim": ['P("garment", required=True)', 'P("body", required=True)', 'P("pin_group", required=True)', 'P("frames", "integer", "10..250")', 'P("thickness_m", "number")',
    'P("max_distance_map", "boolean")', 'P("max_distance_m", "number")', 'P("material_class", desc="metal is refused")'],
 "face_rig_validate": ['P("object", required=True)', 'P("shape_key_profile", desc="arkit | arkit+visemes | none")', 'P("teeth")', 'P("tongue")', 'P("profile", desc="generic | vrm")',
    f'P("poses", "array", "[{{name, keys: {{key: value}}}}]", {O})'],
 "glb_optimize": ['P("glb", required=True)', 'P("out", required=True)', 'P("mesh_compression", desc="draco | none")', 'P("texture_px", "integer")', 'P("webp_quality", "integer", "1..100")',
    'P("keep_animation", "boolean")'],
 "traversal_check": [f'P("route", "array", "[[x, y, z], ...]", required=True, {ARR})', 'P("collection", required=True)',
    'P("player", "object", "{capsule_radius_m, capsule_height_m, max_step_m, max_slope_deg, jump_height_m, jump_gap_m}", required=True)', f'P("sightlines", "array", "[{{from, to}}]", {O})'],
 "level_blockout": ['P("layout", "object", "{start, goal, route, scale_anchor: {object, length_m}}", required=True)', 'P("player", "object", "the capsule values")',
    f'P("primitives", "array", "[{{set, kind, size, at, name}}]", {O})', 'P("views", "integer")', 'P("name")'],
 "part_budget_plan": [f'P("table", "array", "[{{role, camera_distance_m: [min, max], max_tris, texture_px}}]", {O})', f'P("parts", "array", "[{{object, role, camera_distance_m}}]", {O})'],
 "platform_budget_check": ['P("object", required=True)', 'P("platform", desc="roblox_rigid | roblox_layered | ue_static | custom", required=True)', 'P("limits", "object", "custom limits")'],
 "print_check": ['P("object", required=True)', 'P("min_wall_mm", "number", "the printer\'s minimum wall")', 'P("overhang_deg", "number", "30..80")', 'P("units_per_mm", "number")',
    f'P("printer_volume_mm", "array", "[x, y, z]", {N})'],
 "print_prep": ['P("object", required=True)', 'P("target_height_mm", "number", "5..500", required=True)', 'P("min_wall_mm", "number")', 'P("base")', 'P("max_faces", "integer")', 'P("out_dir")',
    'P("split", "array", "more part objects at the same scale")'],
 "profile_revolve": [f'P("profile", "array", "[[r, z], ...]", required=True, {ARR})', 'P("steps", "integer")', 'P("angle_deg", "number")', 'P("bevel_m", "number")', 'P("name")'],
 "splat_world": ['P("action", desc="import")', 'P("path", desc=".spz or 3DGS .ply", required=True)', 'P("max_points", "integer")', 'P("name")'],
 "splat_collision_proxy": ['P("object", required=True)', 'P("voxel_m", "number")', 'P("min_opacity", "number")', 'P("min_density", "integer")', 'P("name")', 'P("export_for_ue", "boolean")'],
 "vehicle_wheel_rig": ['P("body", required=True)', f'P("wheels", "array", "[{{object, name}}]", required=True, {O})', 'P("axis", desc="x | y")', 'P("armature")'],
 "editor_connection_receipt": ['P("editor", desc="blender | unity | godot | unreal")', 'P("disposable", "boolean", required=True)', f'P("position", "array", "[x, y, z]", {N})',
    'P("transport", desc="bridge | mcp_stdio | mcp_http | other")', 'P("release")', 'P("facts", "object", "unity/godot: what your MCP read")'],
 "terrain": ['P("action", desc="heightfield | carve | water | vegetation | from_image", required=True)', 'P("name")', 'P("preset")', 'P("size_m", "number")', 'P("resolution", "integer")',
    'P("height_m", "number")', 'P("detail", "number")', 'P("detail_scale", "number")', 'P("warp", "number")', 'P("seed", "integer")', 'P("channel", "object")', 'P("basin", "object")',
    'P("water_level_m", "number")', 'P("biome")', 'P("asset_objects", "array")', 'P("max_instances", "integer")', 'P("heightmap")'],
 "addon_read": ['P("project", required=True)', 'P("path", required=True)'],
 "addon_stage_patch": ['P("project", required=True)', f'P("files", "array", "[{{path, content}}]", required=True, {O})', 'P("message")', 'P("expected_revision")'],
 "addon_commit": ['P("project", required=True)', 'P("patch_id", required=True)'],
 "addon_rollback": ['P("project", required=True)', 'P("to", required=True)', 'P("expected_revision")'],
 "scene_from_image": ['P("image", required=True)', 'P("masks", "array", "mask PNGs (white = the part)")', 'P("max_objects", "integer", "1..16")', 'P("name")',
    'P("engine", desc="pipeline | studio:tripo")', 'P("scene_width_m", "number")', 'P("scene_depth_m", "number")'],
 "motion_generate": ['P("prompt")', 'P("engine", desc="library | model:kimodo | model:unimate")', 'P("action", desc="generate | index")', 'P("library", desc="project folder of clips, default anims")',
    'P("duration", "number", "0.5..10 s")', 'P("skeleton", desc="model engines only")', 'P("fps", "integer")', 'P("seed", "integer")', 'P("num_samples", "integer")'],
 "material_palette": ['P("image", required=True)', 'P("n", "integer")', f'P("locked", "array", "[{{name, hex}}]", {O})', 'P("method", desc="notable | kmeans")', 'P("alpha_min", "number")',
    'P("max_pixels", "integer")', 'P("seed", "integer")', 'P("make_materials", "boolean")', 'P("compare_to")', 'P("out_dir")', 'P("pms", "boolean")'],
}
DEFNAME = {"splat_world": "lampway_splat_world_import"}
missing = [t for t in tools if t not in PARAMS or t not in docs]
if missing:
    sys.exit(f"missing params or docstrings: {missing}")
out = ['"""The Wave 6 Lampway tool definitions that run in Blender (one api.call each, the same door as lampway_tools.DEFS). Kept apart from lampway_tools.py so',
       'that file stays reviewable; lampway_tools appends these to DEFS, so BY_NAME, SPECS and the MCP offer see them like any other Def.',
       '',
       'Each description is the api_wave6 function\'s docstring, word for word (GENERATED by scripts/lampway/gen_wave6_defs.py and pinned by tests/lampway_tools/test_wave6_door.py):',
       'change the docstring and regenerate, never one side alone."""',
       '', 'from .tool_defs import Def, P', '',
       '_PATHS = " Paths are relative to the project root; a path outside it is refused."', '_OBJ = {"type": "object"}', '', 'DEFS = [']
for t in tools:
    d = docs[t].replace("\\", "\\\\").replace('"', '\\"')
    chunks, line = [], ""
    for w in d.split(" "):
        if len(line) + len(w) + 1 > 150:
            chunks.append(line + " ")
            line = w
        else:
            line = (line + " " + w) if line else w
    chunks.append(line)
    desc = "\n        ".join(f'"{c}"' for c in chunks) + (" + _PATHS" if t in PATHS else "")
    params = ",\n         ".join(PARAMS[t])
    out.append(f'    Def("{DEFNAME.get(t, "lampway_" + t)}", {desc},\n        [{params}], api="{t}"),')
out.append("]\n")
(W / "server/lampway_server/agent/wave6_tools.py").write_text("\n".join(out))
print(len(tools), "defs")
