# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Wave 6 tool functions (specs/wiki and specs/mixar_docs contracts the captain released as Wave 6). Plain functions: ``api.py`` wraps every name in
``TOOLS`` with its ``@tool`` envelope, so they join the one door (``api.call``) with the same refusal shape. Each docstring is the agent-facing
description; the server's Def (agent/wave6_tools.py) carries the same text."""

from . import settings as S

TOOLS = ("modular_character", "character_pipeline", "playblast_capture", "lod_chain", "motion_experiment", "secondary_chain_rig", "cloth_garment_sim",
         "face_rig_validate", "glb_optimize", "traversal_check", "level_blockout", "part_budget_plan", "platform_budget_check", "print_check", "print_prep",
         "profile_revolve", "splat_world", "splat_collision_proxy", "vehicle_wheel_rig", "editor_connection_receipt", "terrain", "addon_read",
         "addon_stage_patch", "addon_commit", "addon_rollback", "material_palette")


def _root() -> str:
    return str(S.load().project_root)


def _p(path) -> str:
    return "" if path in (None, "") else str(S.resolve_in_root(path, _root()))


def modular_character(action="validate", character_id="", parts=None, armature=None, allowed_outfits=None, poses=None, out_dir="export_parts"):
    """A character's interchangeable parts as one typed record. manifest {character_id, parts: [{object, role: head|body|hands|hair|garment|accessory,
    fixed_or_deforming, wearer_side: left|right|center|paired, bone (required for a fixed part)}], armature, allowed_outfits: [[part ids]], poses: rest |
    wiki8 | [poses]} writes <root>/<character_id>/manifest.json with the template fields. validate: one shared armature (two armatures are refused), the
    rest pose unchanged since the manifest, equal scales, each part's measured side against its declared one (the figure faces -Y, its left is +X), and
    weight_audit on every deforming part. outfit_matrix: per allowed outfit (in each pose) the body faces it leaves uncovered of the region any outfit
    covers (a ray from each face along its normal) and the body vertices poking through it; pass = both zero. hidden_body makes `<body>_hidden`, a copy
    without the faces every outfit covers, and is refused before a passing matrix or after anything changed since it. export_parts writes one FBX per
    part with the same armature under out_dir/<character_id>/. The full body is never deleted."""
    from .features import modular_character as M
    return M.run(_root(), action, character_id, parts, armature, allowed_outfits, poses, out_dir, resolve=_p)


def character_pipeline(character_id, parts, mode="plan", target="unreal_mannequin", from_stage=1, to_stage=13, stage=None, gate=None, evidence="", stage_calls=None):
    """The character route as thirteen gated stages: 1 reference pack, 2 generate parts (tripo.mesh, a spend), 3 prep and segment, 4 assemble (fit),
    5 retopology to the part budgets, 6 UV, 7 bake, 8 projection texture (a spend), 9 auto rig, 10 weights, 11 secondary chains, 12 skeleton check and
    export, 13 retarget test. parts: [{name, budget (triangles), rigid_bone}]. mode plan lists the stages with their tools (missing_tools = not built
    yet), spend flags, credits and state. mode record {stage, gate: pass|fail, evidence} appends a gate; a stage needs the stage before it passed, and
    rigging (9-11) needs the assembly (4) passed: "fit before rigging". mode run executes stage_calls {"<n>": [{tool, args}]} for from_stage..to_stage,
    each a tool of that stage, and stops at the first failed gate, the first spend stage (needs_approval: the user's click confirms spends, never this
    tool) and a stage whose tools are not built. target metahuman adds the MetaHuman conform as a needs_decision UE leg. Run record:
    <root>/<character_id>/pipeline/run.json."""
    from .pipeline import character_pipeline as CP
    from . import api
    door = list(api.TOOL_FUNCS)
    if mode == "plan":
        return CP.plan(_root(), character_id, parts, target, from_stage, to_stage, tools=door)
    if mode == "record":
        return CP.record(_root(), character_id, stage, gate, evidence, by="agent", tools=door)
    if mode == "run":
        import json as _json
        return CP.run(_root(), character_id, parts, from_stage, to_stage, stage_calls, executor=lambda t, a: api.call(t, _json.dumps(a)), target=target, tools=door)
    raise ValueError(f"unknown mode {mode!r}; plan | record | run")


def playblast_capture(shots, out_dir="playblast", fps=24, width=640, height=360, engine="workbench", stills="both", target_duration_s=None, scene_objects=None):
    """Light-engine playblasts of the posed blockout, one per shot, for the video model and the framing review. shots: [{name, camera: a camera
    object's name or waypoints [{frame, location}], frames: [first, last], duration_s (the planned video length of this shot), look_at: object name or
    [x, y, z] (waypoint cameras)}]. Each shot renders frames first..last of YOUR scene (its animation plays; the scene is linked, never edited) to
    out_dir/<name>.mp4 (H.264) plus <name>_first.png and <name>_last.png (stills: first | last | both | none), and out_dir/shot_list.json lists every
    file with its sha256. Refused: a shot whose length differs from its duration_s (or target_duration_s) by more than one frame ("playblast length
    must match the planned video duration"), Cycles (workbench | eevee only), an unknown camera, a hidden object named in scene_objects, duplicate shot
    names, more than 1200 frames. The temporary scene and waypoint cameras are removed and your frame is restored."""
    from .features import playblast as PB
    return PB.playblast_capture(_root(), _p(out_dir), shots, fps, width, height, engine, stills, target_duration_s, scene_objects)


def lod_chain(object, ratios=None, protect=None, texture_scale=None, textures=None, naming="{name}_LOD{n}", preserve_uv_seams=True, out_dir="lods"):
    """LOD copies of a mesh by collapse decimation, each measured. ratios: the fraction of faces each LOD keeps, 0.05..0.9 and strictly decreasing
    (default [0.5, 0.25, 0.1]); protect: a vertex group whose vertices are never collapsed (joints, rims, an emblem); preserve_uv_seams (default true)
    also keeps every vertex where the UV layout splits. Per LOD (`<name>_LOD<n>`, a new object; the source is untouched; a re-run replaces this tool's
    own LODs): faces, max_deviation_rel (the symmetric vertex-to-surface distance over the source's bounding diagonal), silhouette_iou (front and left,
    the smaller), weight_audit_pass (skinned meshes; null otherwise) and `textures` downsized by texture_scale (one per ratio, default halving) to
    out_dir/<stem>_LOD<n>.png (materials are not rewired). Refused: ratios not strictly decreasing or outside 0.05..0.9, a texture_scale list of
    another length, a skinned mesh without `protect` ("protect the joint loops or run weight_audit after"). The engine import is the user's check."""
    from .features import lod_chain as L
    return L.lod_chain(_root(), object, ratios, protect, texture_scale, textures, naming, preserve_uv_seams, _p(out_dir), resolve=_p)


def motion_experiment(brief, armature, variants=None):
    """The wiki's A/B/C motion comparison from a typed brief. brief: {duration_s 0.5..10, start, end (poses: {bones: [{bone, rotate: [x, y, z] degrees]}},
    {bone: [x, y, z]} or a named pose: rest or a wiki8 pose), contact: {time_s, landmark, pose (optional)}, action, weapon_hand: left|right|null,
    preserve: [grip, foot_contact]}. variants: {A: keyed (made here: start at frame 1, the contact pose at its time, the end at the duration, the
    default interpolation; the landmark is a pose marker; action `<armature>_motion_A`, replaced on a re-run), B and C: the names of actions imported
    from an external tool}. B and C must start and end on the brief's poses (every named bone within 0.5 degrees) or the call is refused. Returns per
    variant the action and its measured audit (frames, duration, start/end/contact pose error, the largest bone angular speed and acceleration), the
    comparison table, and grade.smoothest (a measurement; a person picks). seed is not_exposed. Refused: a missing start or end pose ("explicit start
    and end poses are required"), foot_contact without a contact landmark, an unknown bone or action."""
    from .features import motion_experiment as ME
    return ME.motion_experiment(brief, armature, variants)


def secondary_chain_rig(object, armature, parent_bone, bones=4, naming="tail_", region=None, preview_constraint="damped_track", colliders=True):
    """A bone chain for a tail, hair, cape or coat under an existing bone, on COPIES (`<armature>_chain`, `<object>_chain`; the originals are kept; a
    re-run replaces this tool's copies). region: the geometry the chain drives, a world bounding box [[x, y, z], [x, y, z]] or a vertex group. The
    chain (bones 2..24, named <naming>01..) runs along the region's principal axis from the end nearer parent_bone outward, connected, its first bone a
    child of parent_bone. The region's vertices are weighted to the chain and the parent only (every other influence is removed and counted);
    preview_constraint damped_track chains DAMPED_TRACK constraints for posing; colliders adds a capsule proxy per body bone (radius = its farthest
    vertex from the bone, parented to it). No numeric physics presets are emitted: masses, damping and limits are tuned per appendage in the engine.
    Refused: more than 24 bones ("split into several chains"), an unknown parent_bone (the bones are listed), a region with under 4 vertices, a base
    rig that fails weight_audit."""
    from .features import secondary_chain as SC
    return SC.secondary_chain_rig(object, armature, parent_bone, bones, naming, region, preview_constraint, colliders)


def cloth_garment_sim(garment, body, pin_group, frames=60, thickness_m=0.005, max_distance_map=True, max_distance_m=0.1, material_class=None):
    """Drape a COPY of a garment (`<garment>_draped`) on a posed body with Blender cloth: pin_group (a vertex group) stays at its place, the body
    collides (a Collision modifier for the bake only), thickness_m 0.0005..0.02; frames 10..250 and a wall-clock budget bound the bake. The last
    frame becomes a static mesh (no cloth modifier, no cache left) and, with max_distance_map, the vertex group `max_distance` holds the engine-cloth
    map: 0 at the pins, rising with the distance to the nearest pin to 1 at max_distance_m. Returns the draped object and stats (max displacement,
    body penetrations, frames simulated). Refused: a metal garment (material_class metal or the object's lw_material_class: "metal parts are not cloth:
    rigid or segmented binding"), a garment with an Armature modifier (bind after the drape), an empty or missing pin group. Every numeric default is a
    placeholder: the sources give no usable numbers."""
    from .features import cloth_garment as CG
    return CG.cloth_garment_sim(garment, body, pin_group, frames, thickness_m, max_distance_map, max_distance_m, material_class)


def face_rig_validate(object, shape_key_profile="arkit", teeth=None, tongue=None, profile="generic", poses=None):
    """Check a face rig by measurement. keys: the head's shape keys against the ARKit 52 (arkit) or ARKit + 15 visemes (arkit+visemes): present,
    missing, extra. interior: separate teeth and tongue objects and an open mouth at neutral. expressions: the wiki's six (neutral_blink,
    asymmetric_brow, wide_mouth, lips_together, teeth_tongue_clearance, speech_line), each set on the shape keys and MEASURED on the evaluated mesh
    from the vertex groups lip_upper, lip_lower, brow_l, brow_r (lip gap, brow asymmetry) and the teeth surface (the smallest signed lip-to-teeth
    distance; negative = penetrating); poses [{name, keys: {key: value}}] replaces the six. Every shape value is restored. profile vrm reports the
    VRM expression bindings as not checked unless the VRM add-on's data is present. Refused: no shape keys ("generate them first (Faceit or
    manual)"), teeth or tongue given on a closed mouth ("open-mouth source needed or accept no interior check"). Thresholds are proposals."""
    from .features import face_rig as FR
    return FR.face_rig_validate(object, shape_key_profile, teeth, tongue, profile, poses)


def glb_optimize(glb, out, mesh_compression="draco", texture_px=1024, webp_quality=80, keep_animation=True):
    """A lighter GLB for web preview, with the proof it still holds the same asset: Blender's glTF add-on re-writes the GLB with Draco mesh compression
    (or none), its images downsized to texture_px (the longest side) and as WebP at webp_quality 1..100, the animations kept unless keep_animation is
    false. The output is re-imported and compared: vertex_deviation_rel (the farthest input vertex from the output surface over the bounding
    diagonal), texture_ssim (the input's first image downsized the same way against the output's), the animations (count, frame ranges, animated
    positions); bytes before and after. Your scene is untouched (everything imported is removed). Refused: out equal to the input, a path outside the
    root, meshopt (glTF Transform's, an external engine the captain may approve), webp_quality outside 1..100."""
    from .features import glb_optimize as GO
    return GO.glb_optimize(_p(glb), _p(out), mesh_compression, texture_px, webp_quality, keep_animation)


def traversal_check(route, collection, player, sightlines=None):
    """Sweep a player capsule along a route ([[x, y, z], ...]) over the meshes of a collection (the blockout or a collision proxy) and report each
    route point's state: ok, blocked (a step above max_step_m, or a wall at knee or mid height, or a passage narrower than the capsule), too_steep
    (the ground steeper than max_slope_deg), low_ceiling (headroom under capsule_height_m) or gap (no ground wider than jump_gap_m, or a far side
    higher than jump_height_m), with the detail and the blocked count; sightlines [{from, to}] say whether each straight line is clear. player is
    required: {capsule_radius_m, capsule_height_m, max_step_m, max_slope_deg, jump_height_m, jump_gap_m} (the project's values; none is built in).
    Read-only. Refused: a missing capsule value, an unknown collection, a route point outside the blockout's bounds."""
    from .features import traversal as TV
    return TV.traversal_check(route, collection, player, sightlines)


def level_blockout(layout, player=None, primitives=None, views=3, name="blockout"):
    """A primitive blockout at real gameplay scale before any art: layout {start, goal, route: [[x, y, z]], scale_anchor: {object: a primitive's
    name, length_m}} (the anchor turns layout units into metres; without it they are metres); primitives [{set: ground|route|obstacles|landmarks,
    kind: box|ramp|stair, size: [x, y, z], at: [x, y, z] (the centre), name}] go into the collections <name>_ground, _route, _obstacles, _landmarks
    under <name> (a stair's riser fits under the player's max_step), the route is the polyline <name>_route_path, three fixed cameras (top, from the
    start, from the goal), and traversal_check runs on the result. Nothing is deleted. Refused: no player dimensions ("project dimensions are required:
    the capsule decides what is traversable"), a scene not in metres (scale_to_measure first), an unknown set or kind, a blockout name in use."""
    from .features import level_blockout as LB
    return LB.level_blockout(layout, player, primitives, views, name)


def part_budget_plan(table=None, parts=None):
    """Check a character's parts against the CAPTAIN's budget table (none is built in). table: [{role, camera_distance_m: [min, max], max_tris,
    texture_px}]; parts: [{object, role, camera_distance_m}]. Per part: triangles (an n-gon counts n - 2), its budget, over_by, the largest texture its
    materials use against the budget, and pass. Read-only. Refused: no table ("the budget table is the captain's: none is built in"), a role not in
    the table, a distance no row of that role covers. Post-processing budgets only: Tripo generation runs at maximum polycount."""
    from .features import budgets as B
    return B.part_budget_plan(table, parts)


def platform_budget_check(object, platform, limits=None):
    """Check an asset against a platform's documented limits from a dated data table: roblox_rigid (4k triangles, 2048 texture, one watertight mesh),
    roblox_layered (4k triangles, 2048 texture, at most 4 bone weights per vertex, inner and outer cages), ue_static (no documented limit in the
    sources: use custom), custom (limits {max_tris, max_texture_px, watertight, max_weights, retrieved}). Returns each check (value, limit, pass), the
    date the limits were read and stale (older than 90 days: re-read the documentation). Read-only. Refused: an unknown platform (the known ones are
    listed), custom without limits."""
    from .features import budgets as B
    return B.platform_budget_check(object, platform, limits)


def print_check(object, min_wall_mm=None, overhang_deg=45.0, units_per_mm=None, printer_volume_mm=None):
    """Printability, measured in millimetres (the scene's unit scale, or units_per_mm): manifold (open and non-manifold edges), self-intersections
    (overlapping faces that share no vertex), isolated triangles, thin walls (a ray inward from every face: the walls under min_wall_mm, the thinnest
    first), the overhang area fraction (faces facing down within 90 - overhang_deg of straight down, not those on the build plate), floating parts
    (shells beyond the first), the size and whether it fits printer_volume_mm. Read-only. Refused: no min_wall_mm (the printer's), overhang_deg outside
    30..80."""
    from .features import printing as PR
    return PR.print_check(object, min_wall_mm, overhang_deg, units_per_mm, printer_volume_mm)


def print_prep(object, target_height_mm, min_wall_mm=None, base=None, max_faces=1000000, out_dir="print", split=None):
    """A physical-print derivative, kept apart from the game asset: a COPY of `object` (and of each object in split, at the same scale) with modifiers
    applied, an optional shared `base` unioned by Blender's exact boolean, merged and re-normalled, decimated to max_faces, scaled so its height is
    target_height_mm (5..500) and written in millimetres as one STL per part under out_dir; print_check gates it. The copies are removed. Refused: no
    min_wall_mm ("the wall limit is the printer's: give it"), an object with an armature ("print derivatives are static: pose it first and apply"), an
    open shell after repair, walls thinner than min_wall_mm at that size: nothing is written then. No slicer, supports or curing."""
    from .features import printing as PR
    return PR.print_prep(_root(), object, target_height_mm, min_wall_mm, base, max_faces, _p(out_dir), split)


def profile_revolve(profile, steps=64, angle_deg=360.0, bevel_m=0.0, name="lw_revolve"):
    """A watertight lathe object from a 2D side profile: profile [[r, z], ...] (2..64 points, r >= 0) in the XZ plane spun about Z in steps 8..256 over
    angle_deg 1..360; a full turn merges the seam and points on the axis weld into poles, so a profile that starts and ends on the axis closes into a
    solid; bevel_m 0..0.05 bevels the corner vertices first; normals point outward. Returns the object, faces, manifold, open_edges and bounds (a
    partial angle leaves the cut open and says so). Refused: a profile that crosses the axis (a negative radius), fewer than 2 or more than 64 points,
    steps or angle out of range."""
    from .features import profile_revolve as PRV
    return PRV.profile_revolve(profile, steps, angle_deg, bevel_m, name)


def splat_world(action="import", path="", max_points=200000, name="lw_world", **_ignored):
    """A Gaussian-splat environment in the scene: action import reads an SPZ (through the Client's own SPZ decoder, written as a 3DGS PLY beside it)
    or a 3DGS PLY into ONE point object with colour, opacity and radius attributes and a geometry-nodes view; a splat has no faces, so mesh tools
    refuse it. Generating a world (text or image to a splat) is the server's lampway_splat_world: a world-model job the user confirms."""
    if action != "import":
        raise ValueError("splat_world here imports a splat (action=import); generating one is the server tool lampway_splat_world (a spend the user confirms)")
    from .features import splat_proxy as SP
    return SP.splat_world_import(_root(), path, max_points, name, resolve=_p)


def splat_collision_proxy(object, voxel_m=0.1, min_opacity=0.5, min_density=8, name=None, export_for_ue=False, max_voxels=50000000):
    """A separate, named collision mesh for an imported splat, because visually dense splats do not imply physics surfaces: points whose opacity is at
    least min_opacity (0..1) are binned into voxels of voxel_m (0.02..1.0); a voxel with min_density of them is solid; the surface between solid and
    empty voxels is voxel-remeshed (closed and manifold) into the collection <splat>_collision as <splat>_collision, or UCX_<splat> for Unreal
    (export_for_ue). Returns faces, manifold, bounds and the share of the splat's opacity mass inside it. The splat is untouched. Refused: an object
    that is not a splat (no splat_opacity), more than 50 million voxels ("raise voxel_m"), values out of range."""
    from .features import splat_proxy as SP
    return SP.splat_collision_proxy(object, voxel_m, min_opacity, min_density, name, export_for_ue, max_voxels)


def vehicle_wheel_rig(body, wheels, axis="x", armature=None):
    """Prepare a generated car's wheels for an engine vehicle template: wheels [{object, name: wheel_fl|wheel_fr|wheel_rl|wheel_rr}], axis x | y (the
    axle direction). Each wheel's centre and radius come from a least-squares circle fit to its rim ring across its thinnest axis; a COPY named after
    the wheel gets its origin at the centre and is parented to a bone of that name (in `armature` or a new `<body>_wheels`); the originals keep their
    origins. Returns per wheel the centre, radius, fit residual, axle direction and how far the original origin was from the centre, and whether the
    four axles are parallel (within 2 degrees). Handling, wheel physics and collision stay engine-side. Refused: not exactly the four names, unapplied
    rotation or scale, a rim fit residual above 5 % of the radius ("this does not look like a wheel")."""
    from .features import vehicle as VH
    return VH.vehicle_wheel_rig(body, wheels, axis, armature)


def editor_connection_receipt(editor="blender", disposable=False, position=(0, 0, 0), transport="bridge", release="", facts=None):
    """Prove which editor, version and project you are really connected to before mutating anything, as a typed receipt under receipts/. blender
    (here): the version, the open file (it must be a saved copy under the project root, else nothing changes), the scene, the objects, then
    TestConnectionCube made at `position`, removed with its mesh, and the object list compared with the one before. unity | godot: pass the facts your
    own MCP connection read (editor_version, connector_release, project_path, scene, read_tool, undo_outcome); they are validated and stored. unreal:
    needs_decision (the UE editor leg waits on the Blender-to-UE render parity exploration). Refused: disposable not true ("the create-undo test runs in
    a disposable copy only"), an unsaved or outside-the-root file, missing facts ("not connected")."""
    from .features import editor_receipt as ER
    return ER.editor_connection_receipt(_root(), editor, disposable, position, transport, release, facts)


def terrain(action="heightfield", name="LW_Terrain_1", preset="hills", size_m=None, resolution=None, height_m=None, detail=None, detail_scale=None,
            warp=None, seed=None, channel=None, basin=None, water_level_m=None, biome=None, asset_objects=None, max_instances=None, heightmap=None):
    """A Blender landscape backdrop (no erosion simulation, no sky, no real-world data import). heightfield {name, preset mountains|hills|canyon|
    desert|flat, size_m 20..500, resolution 32..1024 (default 256), height_m, detail, detail_scale, warp, seed}: a grid with a geometry-nodes
    heightfield (LW_Terrain) whose height range is height_m and whose parameters stay live. carve {channel: {polyline: [[x, y]], width_m, depth_m,
    bank_m} | basin: {centre, radius_m, depth_m}}: COMMITS the terrain to vertices (stage two) and lowers the channel or basin by its depth with a smooth
    bank; nothing beyond the bank moves. water {water_level_m}: a water plane. vegetation {biome riparian|grassland|meadow|forest, asset_objects,
    water_level_m, max_instances, seed}: instances above the water and off steep ground, never more than max_instances. from_image {heightmap, size_m,
    resolution, height_m}: the grid displaced by a blurred heightmap. Refused: resolution above 1024 ("capped at 1024"), vegetation spread over more than
    200 m ("60-120 m reads lush"), a ground-level photo as a heightmap ("give a top-down height reference"), unknown actions."""
    from .features import terrain as TE
    kw = {k: v for k, v in dict(name=name, preset=preset, size_m=size_m, resolution=resolution, height_m=height_m, detail=detail, detail_scale=detail_scale,
                                warp=warp, seed=seed, channel=channel, basin=basin, water_level_m=water_level_m, biome=biome, asset_objects=asset_objects,
                                max_instances=max_instances, heightmap=heightmap).items() if v is not None}
    return TE.terrain(_root(), action, resolve=_p, **kw)


def addon_read(project, path):
    """Read one file of a Blender add-on project the Client links (its add-on projects folder; by project id or name). Refused: a project outside that
    folder ("works on projects inside that folder only"; the linked projects are listed)."""
    from .features import addon_tools as AT
    return AT.addon_read(project, path)


def addon_stage_patch(project, files, message="", expected_revision=None):
    """Stage a patch to a linked add-on project: files [{path, content}] (content null deletes the file), a message, and expected_revision (the
    revision addon_read returned: a project that changed since is refused; omitted, the current revision). Nothing changes on disk: the Client's
    service checks and stores the proposal and returns its patch_id. Show the patch to the user; they approve it in the Client."""
    from .features import addon_tools as AT
    return AT.addon_stage_patch(project, files, message, expected_revision)


def addon_commit(project, patch_id):
    """Commit an approved patch: the Client's transactional commit (rolled back on failing checks), then its checks and install (installed says
    whether the add-on loaded). Refused unless the user approved that very patch in the Client ("a patch is committed only after the captain approves
    it"); an agent's claim of approval is not one."""
    from .features import addon_tools as AT
    return AT.addon_commit(project, patch_id)


def addon_rollback(project, to, expected_revision=None):
    """Roll a linked add-on project back past one committed transaction (`to`, the transaction id from addon_commit), refused when the files changed
    since (the Client's revision check)."""
    from .features import addon_tools as AT
    return AT.addon_rollback(project, to, expected_revision)


def material_palette(image, n=9, locked=None, method="notable", alpha_min=0.05, max_pixels=262144, seed=0, make_materials=False, compare_to=None,
                     out_dir="palettes", pms=False):
    """Named dominant AND accent colours from an image (alpha-aware: transparent pixels never count), deterministic: method notable (area colours
    plus vivid accents by hue family, each new colour at least 8 CIELAB units from the others) or kmeans (seeded, may merge a small accent); n 2..24;
    locked [{name, hex}] colours are kept as given. Each colour: name, hex, sRGB, linear, coverage (summing to 1) and kind (area | accent | locked).
    compare_to a second image: the palette distance in CIELAB (mean, max, p90, pairs) so colour drift has a number. Writes out_dir/<image>.palette.json
    and a swatch PNG; make_materials adds Principled materials PAL_<image>_<i> (never overwriting one). Refused: n out of range, more locked colours than
    n, an image outside the root or without opaque pixels, pms (Pantone needs licensed books Lampway does not have)."""
    from .features import palette as PAL
    path = _p(image)
    out = PAL.extract(path, n, locked, method, alpha_min, max_pixels, seed, _p(compare_to) if compare_to else None, pms)
    import os
    stem = os.path.splitext(os.path.basename(path))[0]
    jp, sp = PAL.write(out, _p(out_dir), stem)
    out["files"] = [os.path.relpath(jp, _root()), os.path.relpath(sp, _root())]
    if make_materials:
        out["materials"] = PAL.make_materials(out, stem)
    return out
