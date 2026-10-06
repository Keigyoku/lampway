"""The Wave 6 Lampway tool definitions that run in Blender (one api.call each, the same door as lampway_tools.DEFS). Kept apart from lampway_tools.py so
that file stays reviewable; lampway_tools appends these to DEFS, so BY_NAME, SPECS and the MCP offer see them like any other Def."""

from .lampway_tools import Def, P

_PATHS = " Paths are relative to the project root; a path outside it is refused."
_OBJ = {"type": "object"}

DEFS = [
    Def("lampway_modular_character", "A character's interchangeable parts as one typed record. manifest {character_id, parts: [{object, role: head|body|hands|hair|"
        "garment|accessory, fixed_or_deforming, wearer_side: left|right|center|paired, bone (required for a fixed part)}], armature, allowed_outfits: [[part ids]], "
        "poses: rest | wiki8 | [poses]} writes <root>/<character_id>/manifest.json with the template fields. validate: one shared armature (two armatures are "
        "refused), the rest pose unchanged since the manifest, equal scales, each part's measured side against its declared one (the figure faces -Y, its left is "
        "+X), and weight_audit on every deforming part. outfit_matrix: per allowed outfit (in each pose) the body faces it leaves uncovered of the region any outfit "
        "covers and the body vertices poking through it; pass = both zero. hidden_body makes `<body>_hidden`, a copy without the faces every outfit covers, and is "
        "refused before a passing matrix or after anything changed since it. export_parts writes one FBX per part with the same armature under "
        "out_dir/<character_id>/. The full body is never deleted." + _PATHS,
        [P("action", desc="manifest | validate | outfit_matrix | hidden_body | export_parts", required=True), P("character_id", required=True),
         P("parts", "array", "manifest: [{object, role, fixed_or_deforming, wearer_side, bone}]", items=_OBJ), P("armature"),
         P("allowed_outfits", "array", "[[part ids]]", items={"type": "array", "items": {"type": "string"}}),
         P("poses", "string", "rest | wiki8 (default: the manifest's)"), P("out_dir")], api="modular_character"),
    Def("lampway_character_pipeline", "The character route as thirteen gated stages: 1 reference pack, 2 generate parts (tripo.mesh, a spend), 3 prep and segment, "
        "4 assemble (fit), 5 retopology to the part budgets, 6 UV, 7 bake, 8 projection texture (a spend), 9 auto rig, 10 weights, 11 secondary chains, 12 skeleton "
        "check and export, 13 retarget test. parts: [{name, budget (triangles), rigid_bone}]. mode plan lists the stages with their tools (missing_tools = not built "
        "yet), spend flags, credits and state. mode record {stage, gate: pass|fail, evidence} appends a gate; a stage needs the stage before it passed, and rigging "
        "(9-11) needs the assembly (4) passed: 'fit before rigging'. mode run executes stage_calls {\"<n>\": [{tool, args}]} for from_stage..to_stage, each a tool of "
        "that stage, and stops at the first failed gate, the first spend stage (needs_approval: the user's click confirms spends, never this tool) and a stage whose "
        "tools are not built. target metahuman adds the MetaHuman conform as a needs_decision UE leg. Run record: <root>/<character_id>/pipeline/run.json.",
        [P("character_id", required=True), P("parts", "array", "[{name, budget, rigid_bone}]", required=True, items=_OBJ), P("mode", desc="plan | record | run"),
         P("target", desc="unreal_mannequin | metahuman | mixamo | vrm"), P("from_stage", "integer"), P("to_stage", "integer"), P("stage", "integer"),
         P("gate", desc="pass | fail"), P("evidence"), P("stage_calls", "object", "{\"<n>\": [{tool, args}]}")], api="character_pipeline"),
    Def("lampway_playblast_capture", "Light-engine playblasts of the posed blockout, one per shot, for the video model and the framing review. shots: [{name, camera: a "
        "camera object's name or waypoints [{frame, location}], frames: [first, last], duration_s (the planned video length of this shot), look_at: object name or "
        "[x, y, z] (waypoint cameras)}]. Each shot renders frames first..last of YOUR scene (its animation plays; the scene is linked, never edited) to "
        "out_dir/<name>.mp4 (H.264) plus <name>_first.png and <name>_last.png (stills: first | last | both | none), and out_dir/shot_list.json lists every file with "
        "its sha256. Refused: a shot whose length differs from its duration_s (or target_duration_s) by more than one frame ('playblast length must match the "
        "planned video duration'), Cycles (workbench | eevee only), an unknown camera, a hidden object named in scene_objects, duplicate shot names, more than 1200 "
        "frames. The temporary scene and waypoint cameras are removed and your frame is restored." + _PATHS,
        [P("shots", "array", "[{name, camera, frames: [a, b], duration_s, look_at}]", required=True, items=_OBJ), P("out_dir"), P("fps", "integer"), P("width", "integer"),
         P("height", "integer"), P("engine", desc="workbench | eevee"), P("stills", desc="first | last | both | none"), P("target_duration_s", "number"),
         P("scene_objects", "array", "objects that must be visible")], api="playblast_capture"),
    Def("lampway_lod_chain", "LOD copies of a mesh by collapse decimation, each measured. ratios: the fraction of faces each LOD keeps, 0.05..0.9 and strictly "
        "decreasing (default [0.5, 0.25, 0.1]); protect: a vertex group whose vertices are never collapsed (joints, rims, an emblem); preserve_uv_seams (default true) "
        "also keeps every vertex where the UV layout splits. Per LOD (`<name>_LOD<n>`, a new object; the source is untouched; a re-run replaces this tool's own LODs): "
        "faces, max_deviation_rel (the symmetric vertex-to-surface distance over the source's bounding diagonal), silhouette_iou (front and left, the smaller), "
        "weight_audit_pass (skinned meshes; null otherwise) and `textures` downsized by texture_scale (one per ratio, default halving) to out_dir/<stem>_LOD<n>.png "
        "(materials are not rewired). Refused: ratios not strictly decreasing or outside 0.05..0.9, a texture_scale list of another length, a skinned mesh without "
        "`protect` ('protect the joint loops or run weight_audit after'). The engine import is the user's check." + _PATHS,
        [P("object", required=True), P("ratios", "array", items={"type": "number"}), P("protect", desc="vertex group never collapsed"),
         P("texture_scale", "array", items={"type": "number"}), P("textures", "array", "texture files to downsize per LOD"), P("naming", desc="default {name}_LOD{n}"),
         P("preserve_uv_seams", "boolean"), P("out_dir")], api="lod_chain"),
    Def("lampway_motion_experiment", "The wiki's A/B/C motion comparison from a typed brief. brief: {duration_s 0.5..10, start, end (poses: {bones: [{bone, rotate: "
        "[x, y, z] degrees]}}, {bone: [x, y, z]} or a named pose: rest or a wiki8 pose), contact: {time_s, landmark, pose (optional)}, action, weapon_hand: left|right|null, "
        "preserve: [grip, foot_contact]}. variants: {A: keyed (made here: start at frame 1, the contact pose at its time, the end at the duration, the default "
        "interpolation; the landmark is a pose marker; action `<armature>_motion_A`, replaced on a re-run), B and C: the names of actions imported from an external "
        "tool}. B and C must start and end on the brief's poses (every named bone within 0.5 degrees) or the call is refused. Returns per variant the action and its "
        "measured audit (frames, duration, start/end/contact pose error, the largest bone angular speed and acceleration), the comparison table, and grade.smoothest (a "
        "measurement; a person picks). seed is not_exposed. Refused: a missing start or end pose ('explicit start and end poses are required'), foot_contact without "
        "a contact landmark, an unknown bone or action.",
        [P("brief", "object", "{duration_s, start, end, contact: {time_s, landmark, pose}, action, weapon_hand, preserve}", required=True), P("armature", required=True),
         P("variants", "object", "{A: keyed, B: action name, C: action name}")], api="motion_experiment"),
    Def("lampway_secondary_chain_rig", "A bone chain for a tail, hair, cape or coat under an existing bone, on COPIES (`<armature>_chain`, `<object>_chain`; the "
        "originals are kept; a re-run replaces this tool's copies). region: the geometry the chain drives, a world bounding box [[x, y, z], [x, y, z]] or a vertex "
        "group. The chain (bones 2..24, named <naming>01..) runs along the region's principal axis from the end nearer parent_bone outward, connected, its first bone a "
        "child of parent_bone. The region's vertices are weighted to the chain and the parent only (every other influence is removed and counted); preview_constraint "
        "damped_track chains DAMPED_TRACK constraints for posing; colliders adds a capsule proxy per body bone (radius = its farthest vertex from the bone, parented to "
        "it). No numeric physics presets are emitted: masses, damping and limits are tuned per appendage in the engine. Refused: more than 24 bones ('split into "
        "several chains'), an unknown parent_bone (the bones are listed), a region with under 4 vertices, a base rig that fails weight_audit.",
        [P("object", required=True), P("armature", required=True), P("parent_bone", required=True), P("bones", "integer", "2..24, default 4"),
         P("naming", desc="tail_ | cape_ | hair_ ..."), P("region", "array", "[[x, y, z], [x, y, z]] world bounding box (or pass a vertex group name)", items={"type": "array"}),
         P("preview_constraint", desc="damped_track | none"), P("colliders", "boolean")], api="secondary_chain_rig"),
]
