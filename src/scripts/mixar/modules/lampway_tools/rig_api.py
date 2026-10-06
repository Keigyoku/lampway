# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig tools' api functions (specs/canon/rig_tools; STATUS O36). ``api`` star-imports this module just before it freezes TOOL_FUNCS,
as it does orphans_api. The rig front door (inspect, map, normalize) accepts a raw armature: these tools ARE the skeleton's normalization
(no other skeleton normalizer exists), and every one after rig_inspect requires its stamp."""

from .api import _p, _settings, tool  # noqa: F401  (api is mid-import here: these names are already bound)
from .canon_door import NONE, Need

__all__ = []
ALL = ("real", "generator_normalised", "unknown")
RIG_RAW = {"armature": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)}
REAL = ("real",)


def _export(fn):
    __all__.append(fn.__name__)
    return fn


@_export
@tool(consumes=RIG_RAW)
def rig_inspect(armature, reference="", family="auto", profile="ue5_body"):
    """Read any skeleton and say what it is: bones, deform, roots, the naming family by table hits, mapped and missing slots, the frame
    convention (blender | ue_axes | mixed) from each bone's axis against its head -> next joint, units against the reference, animation keys,
    constraints, B-Bones, leaf and helper bones, input sha256. Never refuses on a defect of the rig: it reports it. Stamps the armature."""
    from .features import rig_tools as _RT
    return _RT.inspect(armature, reference, family, profile)


@_export
@tool(consumes=RIG_RAW)
def rig_map(armature, out, family="auto", profile="ue5_body", synthesize=True, dry_run=False):
    """map.json: every UE slot -> the source bone (by the family table), the torso slots synthesized at the reference's arc-length fractions,
    the unmapped bones kept, the collision renames planned, the hashes that reproduce it."""
    from .features import rig_tools as _RT
    return _RT.map_(armature, out, str(_settings().project_root), family, profile, synthesize, dry_run)


@_export
@tool(consumes=RIG_RAW)
def rig_normalize(armature, unit="auto", apply_scale=True, dry_run=True):
    """Units and object scale applied without moving anything: rest joints and location keys scaled, rotation keys untouched; a non-uniform
    scale only on an unanimated rig; 8 frames checked, rolled back above 1e-6 m."""
    from .features import rig_tools as _RT
    return _RT.normalize(armature, unit, apply_scale, dry_run)


@_export
@tool(consumes={"reference": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)})
def rig_readback(fbx, reference):
    """The rig_export_ue read-back: import the FBX (canon_io, automatic bone orientation off) and compare every bone's rest to the reference
    armature at the bind_mismatch bars (0.01 cm, 0.01 deg, 1e-4 scale); PASS or FAIL with the rows over tolerance."""
    from .features import rig_tools as _RT
    return _RT.readback(fbx, reference, str(_settings().project_root))


@_export
@tool(consumes=RIG_RAW)
def rig_export_ue(armature, out, meshes=None, actions=None, reference="", recipe="titan_cm_native", readback=True):
    """Write the FBX with a recipe that states every exporter argument, read it back raw (automatic bone orientation off, no axis correction)
    and publish it only when every bone matches the reference at the bind_mismatch bars; the file's UnitScaleFactor read from the FBX and gated;
    a failing file moved to export/rejected/."""
    from .features import rig_export as _RE
    return _RE.export_ue(armature, out, str(_settings().project_root), meshes, actions, reference, recipe, readback)


@_export
@tool(consumes={"example": Need(kind=("mesh", "part", "rigged_mesh"), scale=REAL)})
def rig_fit_template(example, joints, template="", hands="none", hidden=None, convention="blender", weights="procedural", allow_outside=None, out="",
                     dry_run=False):
    """Rig the fitted example at its OWN joints (canon 20): the template's heads written to the joints measured on the example (residual 0),
    the other bones placed by their measured segments, frames by canon 17, six axis rays per joint inside the example, the example's own
    weights from the fitted segments on a copy; refuses copied joints (copied_not_fitted), a joints file from another mesh, a missing joint."""
    from .features import rig_fit as _RF
    return _RF.fit(example, joints, str(_settings().project_root), template, hands, hidden, convention, weights, allow_outside, out, dry_run)


@_export
@tool(consumes={"control": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)})
def rig_game_extract(control, name="", extract="deform", hierarchy="keep", constraint="lotrot", root_scale_from="auto", bbones="refuse",
                     rebind_meshes=True, collection="Deform", dry_run=False):
    """An engine-clean deform rig from any control rig (canon 19 B.4; GRT's Generate Game Rig re-implemented with its defects fixed): kept
    bones by extract mode, hierarchy keep | rigify_fix | flat, every kept bone in one collection, constraints to the control twin (lotrot |
    transform | none), B-Bones refused or converted per segment, meshes re-pointed with their world matrix kept; the follow error measured."""
    from .features import rig_game as _RG
    return _RG.extract(control, name, extract, hierarchy, constraint, root_scale_from, bbones, rebind_meshes, collection, dry_run)


@_export
@tool(consumes={"driver": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True),
                "target": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)})
def rig_bake(driver, target, actions, frames="action", name=None, overwrite=False, offset_to_one=False, push_to_nla=True, channels=None,
             dry_run=False):
    """A driver's actions to plain keys on the target (canon 19 B.6; GRT's Action Bakery semantics): the target's evaluated pose sampled per
    frame and written as LOCAL keys against the sampled parent, played back with the constraints muted and compared frame by frame (over
    1e-4 m or 0.01 deg the action is removed); naming, frame ranges, overwrite, offset and NLA as GRT; the driver's action restored."""
    from .features import rig_bake as _RB
    return _RB.bake(driver, target, actions, frames, name, overwrite, offset_to_one, push_to_nla, channels, dry_run)


@_export
@tool(consumes={"target": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)})
def rig_retarget(source, target, action="", map="auto", method="matrix", root_motion="keep", root_yaw="none", scale="auto", frames="action", fps=None,
                 check_objects=None, name="", dry_run=False):
    """Motion from one skeleton onto another (canon 19 B.1-B.3, B.5): W_t = W_s R_s^-1 R_t per mapped bone, parent-first LOCAL keys, rotation
    only below the pelvis (no bone length changes), the pelvis travel scaled by the pelvis-height ratio, and root_motion=root_bone writes a
    root from the pelvis (on the ground, never tilted, recomposing exactly; yaw none | heading); measured after writing."""
    from .features import rig_retarget as _RR
    return _RR.retarget(source, target, str(_settings().project_root), action, map, method, root_motion, root_yaw, scale, frames, fps, check_objects,
                        name, dry_run)


@_export
@tool(consumes=RIG_RAW)
def rig_convert(verb, input="", profile="", target_profile="", rules="", target="", out="", armature="", action="", duration="", name="",
                basis=None, centimeters_per_unit=100.0, channels=None):
    """The external rig-conversion and normalization tool (O36, canon 22): profile (an inspected armature -> titan.animation-profile/1) |
    extract (an action -> native samples on the 30 fps rational schedule) | normalize | adapt | retarget | compare | verify (the A1 bars).
    Every output is an immutable publication with a receipt; the wire ids are a stable contract shared with TITAN."""
    from .features import rig_convert_tool as _RC, rig_tools as _RT
    return _RC.convert(verb, str(_settings().project_root), input, profile, target_profile, rules, target, out, armature, action, duration, name,
                       basis, centimeters_per_unit, channels, inspected=_RT._inspected)


@_export
@tool(consumes=RIG_RAW)
def rig_conform(armature, map, reference="", convention="blender", ik_bones=False, offsets=None, merge_weights=None, out_name="", dry_run=True):
    """Turn a mapped rig into the project's skeleton ON A COPY (canon 16 B.4-B.7, 17): UE names from map.json, missing torso bones at their
    fractions, the reference's hierarchy, frames from the joints and the reference's Z (blender | ue_axes), vertex groups following their bones,
    merge_weights only when named; heads, rest skin and a world-space test pose verified; the source never touched."""
    from .features import rig_conform as _RF
    return _RF.conform(armature, map, str(_settings().project_root), reference, convention, ik_bones, offsets, merge_weights, out_name, dry_run)


@_export
@tool(consumes=NONE("reads canonical JSON documents (meshes, joints, weights, poses) by path: no scene asset"))
def rig_skin(verb, input, out, space="", joints="", weights="", pose="", joint_map="", geometry_only=False):
    """WIP skin and morph (canon 22 B.10 and canon 07 DRAFT): mesh_normalize | mesh_adapt (unrigged mesh with morphs, canonical cm) | capture
    (canonical mesh + global binds + named weights) | rebind | evaluate (P * inverse(B)). Receipts and refusals carry the WIP badge."""
    from .features import rig_convert_tool as _RC
    return _RC.skin(verb, str(_settings().project_root), input, space, joints, weights, pose, joint_map, out, geometry_only)
