# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_pose: the closest pose for a piece. Chest and the captain-accepted canon 08 helmet proposal have complete tables. Other kinds retain explicit questions for the ranges not specified by canon; callers can supply a complete DOF list."""

KINDS = ("chest", "helmet", "waist", "boots", "gauntlets")

PROPOSALS = {
    "helmet": "neck_01, neck_02 and head: pitch and roll -8..8 step 4",
    "waist": "spine_01 and pelvis pitch -8..8; thigh flexion/abduction as the piece's lower edge needs",
    "boots": "calf and foot: ankle pitch and roll, knee flexion a small range; the shaft rides the calf",
    "gauntlets": "forearm twist, wrist flexion; finger curl fractions 80/95/60 degrees for fingers 01/02/03 (armour-poses recipe)",
}


def fit_pose(kind, **_):
    if kind not in KINDS:
        raise ValueError("kind is " + " | ".join(KINDS))
    if kind == "chest":
        return {"ok": True, "route": "pose_clearance",
                "how": "run_tool('pose_clearance', [...]): both upper arms lowered/swung, then the spine_01, spine_03, neck_01 pitch chain, as the shelf's chest pose sweep"}
    if kind in TABLES:
        return {"ok": True, "route": "pose_solve", "table": TABLES[kind], "how": "supply piece, body and armature or use the named DOF table"}
    return {"ok": False, "needs_decision": {
        "what": f"fit_pose degrees of freedom for {kind}",
        "question": f"which bones, axes and ranges may the body move through to find the closest pose for a {kind}, and which poses count as natural?",
        "why": "pose the body to the piece before clearance, fit or weights: a sweep rewards whatever the ranges allow, so the ranges are a ruling, not a default",
        "proposal": PROPOSALS[kind], "proposal_status": "[UNVERIFIED] a proposal from the contract; nothing has been run on a real piece",
        "needs_from_user": "the DOF list (bone, axis, range, step) or 'accept the proposal'"}}


# canon 08 B.4, the chest (CANONICAL, measured): both arms lowered 0..40 step 5 x swung -10..10 step 5 (one DOF each, mirrored to the
# right arm), then hips, chest and neck pitch -8..8 step 4 in turn. Axes in the joint grammar of the body frame (front -Y): a left arm
# lowers about -forward (+Y; the sign check proves it), swings about up, the spine pitches about lateral. Regions by bone: the arms
# count samples over 10 mm, the torso and the neck the fraction over 2 mm (B.3). G08.4 (the recorded chest 166/207 -> 90/103, neck
# 0.2538 -> 0.0639) needs the shelf's chest inputs, which are not in the repository.
CHEST = {
    "dofs": [{"bone": "upperarm_l", "axis": "-forward", "range": [0, 40], "step": 5, "mirror": True,
              "expect": {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}},
             {"bone": "upperarm_l", "axis": "up", "range": [-10, 10], "step": 5, "mirror": True}],
    "chain": [{"bone": "spine_01", "axis": "lateral", "range": [-8, 8], "step": 4}, {"bone": "spine_03", "axis": "lateral", "range": [-8, 8], "step": 4},
              {"bone": "neck_01", "axis": "lateral", "range": [-8, 8], "step": 4}],
    "regions": {"arm_l": {"bones": ["upperarm_l", "lowerarm_l"], "threshold_m": 0.010}, "arm_r": {"bones": ["upperarm_r", "lowerarm_r"], "threshold_m": 0.010},
                "torso": {"bones": ["spine_01", "spine_02", "spine_03", "spine_04", "spine_05"], "threshold_m": 0.002},
                "neck": {"bones": ["neck_01", "neck_02", "head"], "threshold_m": 0.002}},
}

# Canon 08 H.1's complete helmet proposal, accepted by the captain's issue-2 instruction.
# Pitch is lateral and roll is forward in the canonical joint frame; the first neck
# probe must carry head forward. The existing neck penetration threshold is unchanged.
HELMET = {
    "dofs": [{"bone": "neck_01", "axis": "lateral", "range": [-8, 8], "step": 4,
              "expect": {"joint": "head", "along": "forward", "min_cm": 0}}],
    "chain": [{"bone": b, "axis": a, "range": [-8, 8], "step": 4}
              for b, a in (("neck_01", "forward"), ("neck_02", "lateral"), ("neck_02", "forward"), ("head", "lateral"), ("head", "forward"))],
    "regions": {"neck": {"bones": ["neck_01", "neck_02", "head"], "threshold_m": 0.002}},
}
TABLES = {"chest": CHEST, "helmet": HELMET}

MAX_SAMPLES = 20000          # skin samples per solve (a stride over the body's vertices beyond that: a bound on the sweep's cost)


def _bvh_hits(origins, dirs, max_t, V, T):
    """The engine's ray caster over a Blender BVH (same signature as pose_solve.numpy_hits)."""
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([tuple(v) for v in V], [tuple(int(i) for i in t) for t in T])
    out = np.full(len(origins), np.inf)
    for i, (o, d) in enumerate(zip(origins, dirs)):
        if max_t[i] > 0:
            loc, _n, _k, dist = tree.ray_cast(Vector(o), Vector(d), float(max_t[i]))
            if loc is not None:
                out[i] = dist
    return out


def solve_scene(kind, piece, body, armature, dofs, chain=(), regions=None, out="", root=".", curl_side="", curl_fractions=None):
    """canon 08 on scene objects (pipeline.pose_solve): the armature's rest frames (component space), the body's vertices each riding
    its strongest bone, the placed piece's triangles, a BVH ray caster; writes pose.json (lampway.fit-pose/1) to ``out``."""
    import json
    from pathlib import Path
    import bpy
    import numpy as np
    from .features import rig as _rig
    from .pipeline import pose_solve as PS
    if kind not in KINDS:
        raise ValueError("kind is " + " | ".join(KINDS))
    arm, bod, pc = (bpy.data.objects.get(n) for n in (armature, body, piece))
    for name, ob, t in ((armature, arm, "ARMATURE"), (body, bod, "MESH"), (piece, pc, "MESH")):
        if ob is None or ob.type != t:
            raise ValueError(f"{name!r} is not a {t.lower()} object in the scene")
    W = arm.matrix_world
    ref = {}
    for b in arm.data.bones:                                     # bones come parents first
        M = W @ b.matrix_local
        q = M.to_quaternion()
        ref[b.name] = {"parent": b.parent.name if b.parent else None, "rot": (q.x, q.y, q.z, q.w), "pos": tuple(M.translation)}
    me = bod.data
    names = {g.index: g.name for g in bod.vertex_groups if g.name in ref}
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    P = (co.reshape(-1, 3) @ np.array(bod.matrix_world)[:3, :3].T) + np.array(bod.matrix_world)[:3, 3]
    step = max(1, len(me.vertices) // MAX_SAMPLES)
    samples = []
    for i in range(0, len(me.vertices), step):
        gs = [(g.weight, names[g.group]) for g in me.vertices[i].groups if g.group in names and g.weight > 0]
        if gs:
            samples.append((tuple(P[i]), max(gs)[1]))
    if not samples:
        raise ValueError(f"{body!r} has no vertex weighted to a bone of {armature!r}: bind it first")
    V, T = _rig._body_mesh(pc)
    res = PS.solve(ref, {"up": (0.0, 0.0, 1.0), "forward": (0.0, -1.0, 0.0)}, samples, (V, T), list(dofs), list(chain or ()),
                   regions=regions, hits=_bvh_hits, curl_side=curl_side, curl_fractions=curl_fractions)
    res.update(kind=kind, piece=piece, body=body, armature=armature, samples=len(samples), sample_stride=step)
    if out:
        p = Path(root) / out
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=1, sort_keys=True))
        res["out"] = out
    return res
