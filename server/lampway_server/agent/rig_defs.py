"""The rig tools' Defs (specs/canon/rig_tools; STATUS O36): the agent-facing rewrite of the GPL rig add-ons and the external rig conversion
ported from TITAN. A rig arrives -> rig_inspect; never edit bone names, rolls or parents by hand -> rig_map (+ rig_conform); never apply object
scale by hand -> rig_normalize; to the engine -> rig_export_ue, and its read-back (rig_readback) is the claim."""

from .lampway_tools import Def, P, _PATHS

RIG_DEFS = [
    Def("lampway_rig_inspect", "Read any skeleton and say what it is, before any other rig tool touches it (canon 16-18): bones, deform count, roots, "
        "the naming family by table hits (shipped tables: mixamo, rigify; a tie is reported, not guessed), the UE slots mapped and the REQUIRED ones "
        "missing for the profile (ue5_body | ue5_body_fingers | metahuman), the frame convention (blender: local Y along each limb; ue_axes: X along; "
        "mixed: refused by every exporter) measured as each bone's axis against its head -> next joint, the units (height against the UE5 Manny "
        "reference, a known factor within 5 % or a note), object scale, animation (actions, frame ranges, rotation / location / scale key counts), "
        "constraints, B-Bones, leaf and helper bones, and the input sha256. It never refuses on a defect of the rig: it reports it. It stamps the "
        "armature: rig_map and rig_normalize refuse an armature it did not read, or one that changed since.",
        [P("armature", required=True, desc="the armature object"), P("family", desc="auto (default) | mixamo | rigify"),
         P("profile", desc="ue5_body (default) | ue5_body_fingers | metahuman"), P("reference", desc="(reserved) the reference; default the UE5 Manny profile")],
        api="rig_inspect"),
    Def("lampway_rig_map", "Write map.json, the mapping receipt every later rig tool reads (canon 16): every UE slot -> the source bone that fills it "
        "BY THE FAMILY TABLE (never by substring), the torso slots the source lacks (spine_03 / spine_04 ...) synthesized at the reference skeleton's "
        "arc-length fractions along the source chain (never a midpoint), the unmapped source bones (kept, never deleted), the collision renames a "
        "conform would need, the required set it ran against, and the sha256 of the source rest, the reference rest and the tables. Re-running on "
        "the same inputs reproduces it byte for byte; an existing different out is refused. Refused: an armature rig_inspect did not read (or "
        "changed since), a family tie, a REQUIRED slot missing (named), a chain with fewer than two mapped joints to synthesize along, two slots on "
        "one bone. family: auto | mixamo | rigify | a map JSON {family, map: {slot: source}}." + _PATHS,
        [P("armature", required=True), P("out", required=True, desc="e.g. rig/<name>.map.json"), P("family", desc="auto (default) | mixamo | rigify | <map.json>"),
         P("profile", desc="ue5_body (default) | ue5_body_fingers | metahuman"), P("synthesize", "boolean", "place missing torso joints (default true)"),
         P("dry_run", "boolean", "return the map without writing it")],
        api="rig_map"),
    Def("lampway_rig_normalize", "Units and object scale applied WITHOUT moving anything (canon 18): the armature's rest joints are scaled and every "
        "pose-bone location key (and handle) scaled with them; rotation keys are untouched. A non-uniform scale is applied only to an unanimated rig "
        "(the rests re-orthonormalised by the polar factor, the pose locations by loc' = R'^T S R loc); on an animated rig it is refused, naming the "
        "bones with rotation keys. 8 frames are evaluated before and after; a joint that moves more than 1e-6 m rolls the whole call back. unit: auto "
        "(no unit change) | m | cm | in. dry_run (default true) reports the plan. Refused: an armature rig_inspect did not read, a negative scale. "
        "Upstream behaviour is the falsifier: per-channel location scaling (GRT) misplaces a bone by 0.22 m under a non-uniform scale.",
        [P("armature", required=True), P("unit", desc="auto (default) | m | cm | in"), P("apply_scale", "boolean", "apply the object scale (default true)"),
         P("dry_run", "boolean", "default true: report only")],
        api="rig_normalize"),
    Def("lampway_rig_readback", "The rig_export_ue read-back, the claim an export makes (canon 21): import the FBX through canon_io with automatic "
        "bone orientation OFF and compare every bone's rest (position cm, rotation, scale) with the reference armature at the bind_mismatch bars "
        "(0.01 cm, 0.01 deg, 1e-4 scale). PASS or FAIL with the worst row of each kind and every row over tolerance; a roster difference is refused "
        "by name. The imported objects are removed afterwards; the reference is not touched." + _PATHS,
        [P("fbx", required=True, desc="the exported FBX under the project root"), P("reference", required=True, desc="the reference armature object")],
        api="rig_readback"),
    Def("lampway_rig_convert", "The external rig-conversion and normalization tool (O36, canon 22; the game reads only its output). verb profile: an "
        "armature rig_inspect read -> a COMPLETE native profile (titan.animation-profile/1: every bone's bind and reference, the adapter basis, cm "
        "per unit; the to-blender adapter reflects Blender's right-handed frame across Y, metres = 100 cm per unit, the UE5 Manny's basis unless "
        "basis is given; the armature object stands as the root when the root bone is off the origin; rules = authored alignment {bone, toward, "
        "direction} for the T reference, else the bind). verb extract: an action -> native samples on the 30 fps rational schedule plus the exact "
        "terminal time (duration in seconds). verb normalize: native samples (or a canonical packet, validated idempotently) + profile -> the "
        "canonical packet titan.animation/1 (q_c = b q q_ref^-1 b^-1, t_c = units * rotate(b, t)). adapt: canonical -> native, onto the ORIGINAL "
        "profile only. retarget: canonical + target_profile + rules {map (one-to-one, every source bone), reference_follow (every other target "
        "bone), translation_scales, anchors} -> canonical on the target. compare (input vs target): the worst translation, rotation, scale. verify: "
        "a native emission (target) against the canonical packet (input) + profile at the A1 bars (0.1 cm, 0.1 deg, 1e-5 scale), both hashes, the "
        "bones over the bars. Every output is an immutable publication with <out>.receipt.json (input, profile, rules, output sha256, the owner "
        "modules' sha256); an identical repeat keeps the bytes, a different existing output is refused. Refused: an incomplete or non-rebuilding "
        "profile, a non-uniform scale, a schedule that is not 30 fps rational + terminal, an incomplete retarget map, a roster mismatch. The wire ids "
        "(titan.animation/1 ...) are a stable contract shared with TITAN: never renamed." + _PATHS,
        [P("verb", required=True, desc="profile | extract | normalize | adapt | retarget | compare | verify"), P("input", desc="a packet file"),
         P("profile", desc="profile.json"), P("target_profile", desc="retarget: the target profile.json"), P("rules", desc="retarget rules or profile alignment rules"),
         P("target", desc="compare / verify: the second sample file"), P("out", desc="the published output"), P("armature", desc="profile / extract"),
         P("action", desc="extract: the action"), P("duration", desc="extract: seconds, a decimal or rational"), P("name", desc="profile: its name"),
         P("basis", "array", "profile: the adapter basis quaternion xyzw (default the UE5 Manny's)"), P("centimeters_per_unit", "number", "profile: default 100 (metres)"),
         P("channels", "object", "extract: notifies, curves, root motion flags carried as data")],
        api="rig_convert"),
    Def("lampway_rig_skin", "WIP: skin and morph tooling (canon 22 B.10 and canon 07 are DRAFT; the TITAN crews dogfood and improve it through "
        "Lampway). verb mesh_normalize: an unrigged mesh document {meshes: [{name, verts, faces, loop_uv, materials, face_mat, morphs}]} + space "
        "{unit_cm, basis_to_canonical (orthogonal)} -> canonical cm (titan.canonical-mesh/1; a reflection reverses winding, UVs and corner normals; "
        "morph deltas converted, native morph names kept); mesh_adapt: back through the inverse space. capture: a CANONICAL mesh + joints [{name, "
        "parent, bind (global affine 4x4)}] + weights {mesh: [[[joint, w], ...] per vertex]} -> a native-bind skin packet (weights normalized to "
        "exact ratios, no implicit influence cap). rebind: onto target joints by an explicit joint_map naming every weighted joint (many-to-one "
        "merges reported). evaluate: posed positions and morph directions P * inverse(B) for a pose {joint: 4x4} (a shaded packet needs "
        "geometry_only). Receipts and refusals carry the WIP badge." + _PATHS,
        [P("verb", required=True, desc="mesh_normalize | mesh_adapt | capture | rebind | evaluate"), P("input", required=True), P("out", required=True),
         P("space", desc="mesh_*: the space JSON"), P("joints", desc="capture / rebind: joints JSON"), P("weights", desc="capture: weights JSON"),
         P("pose", desc="evaluate: pose JSON"), P("joint_map", desc="rebind: joint map JSON"), P("geometry_only", "boolean", "evaluate a shaded packet without normals")],
        api="rig_skin", wip=True),
    Def("lampway_rig_conform", "Turn a mapped rig into the project's skeleton (canon 16 B.4-B.7, 17; the rewrite of MB's Create UE5 Rig, nothing "
        "ported), always ON A COPY (out_name, default <armature>_ue, with its meshes copied as <mesh>_<out_name>): mapped bones take their UE names "
        "from map.json (a colliding unmapped bone is renamed <name>_src first), the torso bones the map synthesized are created at their arc-length "
        "fractions, every UE slot hangs from its nearest reference ancestor (unmapped bones keep their renamed parent), and every frame is built from "
        "the joints (head -> next joint) and the reference bone's Z in ONE convention (blender: Y along the limb; ue_axes: X along, mirrored where the "
        "reference points back), so the input roll cannot survive. Heads never move (bit for bit); vertex groups follow their bones; merge_weights "
        "{group: bone} adds a group into a bone's and removes it, only when named. Verified before it returns: the rest skin against an untouched "
        "copy (float32 bar printed), and a world-space test pose on both rigs (a vertex group that did not follow its bone fails it). The copy "
        "carries no animation (rig_retarget / rig_convert carry motion). ik_bones adds UE's ik_* bones (and a root at the armature origin when the "
        "rig has none). offsets {bone: {roll_deg}} turns a frame about its own axis. reference: a titan.animation-profile/1 (default UE5 Manny). "
        "dry_run (default true) returns the plan. Refused: an armature rig_inspect did not read (or changed since), no map, a map made from another "
        "rest, an object scale (run rig_normalize), a mixed convention, an existing out_name." + _PATHS,
        [P("armature", required=True), P("map", required=True, desc="the rig_map out, e.g. rig/<name>.map.json"),
         P("reference", desc="a titan.animation-profile/1 JSON; default the shipped UE5 Manny"), P("convention", desc="blender (default) | ue_axes"),
         P("ik_bones", "boolean", "add UE's ik_* bones (default false)"), P("offsets", "object", "{bone: {roll_deg}}"),
         P("merge_weights", "object", "{vertex group: bone}"), P("out_name", desc="the copy's name; default <armature>_ue"),
         P("dry_run", "boolean", "default true: return the plan")],
        api="rig_conform"),
    Def("lampway_rig_export_ue", "Write the FBX the engine reads and prove it bone by bone (canon 21): the recipe states EVERY exporter argument "
        "(titan_cm_native, the default: centimetre-native, FBX_SCALE_NONE + apply_unit_scale, primary Z / secondary X, deform only, no leaf bones; "
        "or a recipe JSON - shipped: cm_native_blender_convention (primary X / secondary -Y, measured for a rig with local Y along the limb) and "
        "cm_native_ue_axes (primary Y / secondary X, for X along)); the written file is imported back RAW (automatic bone orientation off, no axis "
        "correction) and every bone compared with the reference at the bind_mismatch bars (0.01 cm, 0.01 deg, 1e-4 scale); the file's own "
        "UnitScaleFactor is read from the FBX (Blender's importer hides the x100 a metre-scaled file gives UE) and gated by the recipe. reference: "
        "empty = the armature itself in engine axes; an armature object; or a reference FBX. Published only on PASS; otherwise the file moves to "
        "export/rejected/ and the rows over tolerance are named. Refused before writing: an armature rig_inspect did not read, a mixed convention, "
        "constraints, leaf bones, a vertex group naming a bone the reference lacks, a deform hierarchy differing from the reference, more than one "
        "action (one clip per file), an existing out, readback=false. The receipt carries the recipe, convention, read-back worst rows, corner "
        "normals, UnitScaleFactor and the sha256 of the file, the reference and the armature's rest." + _PATHS,
        [P("armature", required=True), P("out", required=True, desc="e.g. export/<name>.fbx"), P("meshes", "array", "mesh objects; default every mesh it deforms"),
         P("actions", "array", "at most one action name (one clip per file)"), P("reference", desc="empty (the armature in engine axes) | armature | <reference>.fbx"),
         P("recipe", desc="titan_cm_native (default) | a recipe JSON path"), P("readback", "boolean", "must stay true")],
        api="rig_export_ue"),
    Def("lampway_rig_fit_template", "Rig the fitted example at its OWN joints, the rig step of the three-input pipeline (canon 20; TITAN rig-axi's "
        "design): joints from a titan.rig-joints/1 file MEASURED on the example (its example_sha256 must equal the example's: the scene mesh's "
        "geometry sha256, or the file's when example is a .glb/.fbx/.obj) or 'rig:<armature>' (the example's own deforming rig); the template "
        "(default the UE5 Manny profile, 161 bones) gets its heads written to the measured joints (residual 0), every other bone placed by its "
        "nearest measured segment (twists, metacarpals, correctives, ik bones on their targets; parentless ones by the similarity of all joints), "
        "frames by canon 17 (blender | ue_axes), an inside check of six axis rays per joint, and the example's OWN weights on the body grammar "
        "from the fitted segments (canon 07 falloff, 3 cm margin; never copied from the native body). Writes <example>_rig and a weighted copy "
        "<example>_rigged (the example is untouched) and saves both to out (.blend). Refused: copied_not_fitted (every bone length within 0.1 % "
        "of the template's: joints taken from the template's body, the 2026-09-28 defect), a joints file measured on another mesh, a required "
        "joint missing (TITAN's 55: body + fingers), joints outside the example unless allow_outside names them, joints or hands from views (the "
        "pose environment is not installed), an existing output. The receipt: residual, ratios, synthesized with their rule, hidden, outside, "
        "rays per joint, weights, sha256 of example, joints, template and out." + _PATHS,
        [P("example", required=True, desc="the example mesh object, or a .glb/.fbx/.obj"), P("joints", required=True, desc="joints.json | rig:<armature> | views"),
         P("template", desc="a titan.animation-profile/1; default UE5 Manny"), P("hands", desc="none (views needs the pose environment)"),
         P("hidden", "array", "joints under armour or cloth to name (default pelvis, thigh_l, thigh_r)"), P("convention", desc="blender (default) | ue_axes"),
         P("weights", desc="procedural (default) | none"), P("allow_outside", "array", "joints allowed outside the example"),
         P("out", desc="default rig/<example>.rig.blend"), P("dry_run", "boolean", "return the fit without writing")],
        api="rig_fit_template"),
    Def("lampway_rig_game_extract", "An engine-clean deform rig from any control rig (Rigify, a tweak rig, a constraint stack; canon 19 B.4; Game "
        "Rig Tools' Generate Game Rig re-implemented, its measured defects fixed): the control is copied as name (default <control>_game), the "
        "bones extract keeps (deform | selected | selected_deform | deform_and_selected) stay, hierarchy keep (nearest kept ancestor) | "
        "rigify_fix (an ORG- ancestor's DEF- twin first; ambiguous twins refuse) | flat, every bone disconnected, shapes, custom properties, "
        "animation and EVERY constraint dropped, ALL kept bones in one collection (GRT left 1 of 5), each game bone constrained to its control "
        "twin (lotrot: Copy Location + Copy Rotation, the default; transform: Copy Transforms; none), root_scale_from adds a Copy Scale (auto: onto "
        "the game rig's own root bone, when it kept one; <bone>: from that control bone onto every top bone). B-Bones are refused, or converted: one bone per segment copying the bendy bone at its "
        "segment start along the curve, the bendy bone's mesh weights split between its segments. Meshes deformed by (or parented to) the "
        "control are re-pointed to the game rig with their world matrix kept (rebind_meshes). The receipt: kept and dropped bones, hierarchy "
        "changes, constraints added, meshes re-pointed, collection members (= kept), the follow error of the game rig against the control, "
        "sha256 of both rests. Refused: an armature rig_inspect did not read, B-Bones with bbones=refuse, a mesh hanging from a dropped bone, "
        "a taken name. Next: lampway_rig_bake to turn the constraints into keys.",
        [P("control", required=True, desc="the control armature"), P("name", desc="default <control>_game"),
         P("extract", desc="deform (default) | selected | selected_deform | deform_and_selected"), P("hierarchy", desc="keep (default) | rigify_fix | flat"),
         P("constraint", desc="lotrot (default) | transform | none"), P("root_scale_from", desc="auto (default) | <bone> | none"),
         P("bbones", desc="refuse (default) | convert"), P("rebind_meshes", "boolean", "re-point the control's meshes (default true)"),
         P("collection", desc="the bone collection of the game rig (default Deform)"), P("dry_run", "boolean", "return the plan only")],
        api="rig_game_extract"),
    Def("lampway_rig_bake", "Constraint-driven motion to plain keys, action by action (canon 19 B.6; Game Rig Tools' Action Bakery semantics, "
        "the bake re-implemented): for each listed action of the driver (e.g. the control rig after lampway_rig_game_extract), the target's "
        "constraints are unmuted, its evaluated pose sampled every frame and written as LOCAL keys against the sampled parent (parent-first: "
        "independent of constraint order; linear keys), then the baked action is played with the constraints MUTED and compared with the "
        "samples frame by frame - over 1e-4 m or 0.01 deg the action is removed and reported failed (no partial action stays). frames: action "
        "| [start, end] | trim:[a, b] (inclusive end); name {mode: suffix | prefix | replace | local, value, to} (default suffix _baked); "
        "overwrite replaces an existing baked action by rename-remap-remove; offset_to_one moves the keys to start at frame 1; push_to_nla "
        "puts each on a track of its own name (a stale one replaced); channels location / rotation (the bone's own mode) / scale. The "
        "driver's previous action is restored (even none); the target's constraints stay muted so the keys play. Refused: an armature "
        "rig_inspect did not read, a driver with no animation data, an action that drives no driver bone, an empty frame range, a baked name "
        "equal to its source, an existing baked name without overwrite, target bones nothing drives. Receipt per action: source, baked, "
        "frames, offset, keys, max world error (m, deg), NLA track, status.",
        [P("driver", required=True), P("target", required=True), P("actions", "array", "the driver's action names", required=True),
         P("frames", desc="action (default) | [start, end] | trim:[a, b]"), P("name", "object", "{mode, value, to}"), P("overwrite", "boolean"),
         P("offset_to_one", "boolean"), P("push_to_nla", "boolean", "default true"), P("channels", "array", "location, rotation, scale"),
         P("dry_run", "boolean")],
        api="rig_bake"),
    Def("lampway_rig_retarget", "Motion from one skeleton onto another, with a root bone when asked (canon 19 B.1-B.3, B.5; the canonical "
        "upgrade of lampway_animation_retarget, which stays as it is): every mapped target bone's WORLD rotation is the source bone's world "
        "change applied to the target's rest (W_t = W_s R_s^-1 R_t; a local key copy misses by 55.7 deg on R04), solved parent-first into a "
        "NEW action of LOCAL keys; bones below the pelvis key rotation only, so no bone length changes; the pelvis travels by the source "
        "pelvis's displacement times the pelvis-height ratio (scale auto, or a number), in_place zeroes the ground components, root_bone "
        "writes the target's root bone from the pelvis (on the ground, never pitched or rolled, recomposing the pelvis exactly; root_yaw none "
        "| heading). map: auto (the target's own names on the source, else a shipped family table) or a rig_map file (its source sha must "
        "match). The action is played back and measured: world-rotation error per mapped bone, bone-length change, edge stretch of "
        "check_objects, the root's tilt and recomposition. source: an armature or a project .fbx/.bvh/.glb (imported through canon_io and "
        "removed after). Refused: method other than matrix (constraints: lampway_rig_bake), root_bone on a target with no root bone (or a "
        "pelvis not under it), a map from another rest, a source without animation, an existing action name, an armature rig_inspect did not "
        "read." + _PATHS,
        [P("source", required=True), P("target", required=True), P("action", desc="an action of the source; default its active one"),
         P("map", desc="auto (default) | rig/<x>.map.json"), P("method", desc="matrix"), P("root_motion", desc="keep (default) | in_place | root_bone"),
         P("root_yaw", desc="none (default) | heading"), P("scale", desc="auto (pelvis-height ratio) or 0.01..100"), P("frames", desc="action | [a, b]"),
         P("fps", "number", "resample to this rate"), P("check_objects", "array", "meshes to measure edge stretch on"),
         P("name", desc="default <action>_rt"), P("dry_run", "boolean")],
        api="rig_retarget"),
    Def("lampway_rig_rest_pose", "Make a pose the rest, once, ON A COPY, and say what it cost (canon 19 B.7-B.8, canon 04; MB's helperT / PoseUE "
        "behaviour re-implemented without its joins, UV renames and action deletions): the copy armature <armature><out_suffix> takes the pose "
        "as its rest; each skinned mesh is copied (<mesh><out_suffix>, no join, UV layers untouched) with its vertices moved to LBS_P(v0) over "
        "the normalized deform weights; each listed action (all = every action keying the armature's bones) is copied <action><out_suffix> "
        "with every key AND handle re-expressed (basis' = rest'_local^-1 rest_local basis), so the copy moves exactly as the original did. "
        "pose: action:<name>:<frame> or a lampway.pose/1 JSON ({bones: {name: {matrix_basis}}}); 'reference' is not built. The copy is stamped: "
        "its rest is never changed again (no chaining; return through the original, which is kept). The receipt: pose, original and new rest "
        "sha256, per mesh the largest move, the actions rewritten, and the RETURN COST - the blend of inverses a naive return through the new "
        "bind gives (R07: 12.5 mm on 46 vertices) against the exact inverse (0). Refused: an armature rig_inspect did not read, a rest already "
        "changed by this tool, shape keys, a non-uniform scale (rig_normalize), Euler-keyed rotations (set QUATERNION), keep_original=false, "
        "existing outputs. dry_run (default true) returns the plan." + _PATHS,
        [P("armature", required=True), P("pose", required=True, desc="action:<name>:<frame> | pose.json"), P("meshes", "array", "default every mesh it deforms"),
         P("actions", "array", "names, or all (default)"), P("keep_original", "boolean", "must stay true"), P("out_suffix", desc="default _rest2"),
         P("dry_run", "boolean", "default true")],
        api="rig_rest_pose"),
]
