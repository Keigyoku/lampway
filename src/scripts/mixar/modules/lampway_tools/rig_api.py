# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig tools' api functions (specs/canon/rig_tools; STATUS O36). ``api`` star-imports this module just before it freezes TOOL_FUNCS,
as it does orphans_api. The rig front door (inspect, map, normalize) accepts a raw armature: these tools ARE the skeleton's normalization
(no other skeleton normalizer exists), and every one after rig_inspect requires its stamp."""

from .api import _p, _settings, tool  # noqa: F401  (api is mid-import here: these names are already bound)
from .canon_door import Need

__all__ = []
ALL = ("real", "generator_normalised", "unknown")
RIG_RAW = {"armature": Need(kind=("skeleton", "rigged_mesh"), scale=ALL, accept_raw=True)}


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
