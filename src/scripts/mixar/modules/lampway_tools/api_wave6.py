# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Wave 6 tool functions (specs/wiki and specs/mixar_docs contracts the captain released as Wave 6). Plain functions: ``api.py`` wraps every name in
``TOOLS`` with its ``@tool`` envelope, so they join the one door (``api.call``) with the same refusal shape. Each docstring is the agent-facing
description; the server's Def (agent/wave6_tools.py) carries the same text."""

from . import settings as S

TOOLS = ("modular_character", "character_pipeline", "playblast_capture", "lod_chain", "motion_experiment", "secondary_chain_rig")


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
