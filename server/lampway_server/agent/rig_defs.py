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
]
