# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference implementations for the rig canon (pages 16-21) and their goldens R01-R07. numpy only.

Every function states the method it implements; the known-WRONG methods are kept as named falsifiers so the self-test can show
them failing. Frames: metres, body frame (Z up, faces -Y, wearer's left +X). A bone's rest frame is a 3x3 rotation whose COLUMNS
are the bone's local X, Y, Z axes in world (Blender convention: local Y runs from head to tail)."""
import numpy as np

# ----------------------------------------------------------------------------- small rotation helpers

def rot(axis, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def angle_deg(Ra, Rb):
    """Angle of the rotation taking Ra to Rb (degrees)."""
    c = (np.trace(Ra.T @ Rb) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return v / n

# ----------------------------------------------------------------------------- R01 skeleton mapping (canon 16)

def detect_family(names, tables):
    """The naming family whose table names the most of `names`; ties refuse (the agent must pass the family)."""
    s = set(names)
    hits = {fam: sum(1 for src in t.values() if src in s) for fam, t in tables.items()}
    best = max(hits.values())
    top = sorted(f for f, h in hits.items() if h == best)
    if best == 0 or len(top) > 1:
        raise ValueError(f"no single naming family matches (hits {hits}): pass family= or a map file")
    return top[0], hits


def map_slots(names, table, required):
    """slot -> source name, from a family table (UE slot -> that family's bone name). Refuses missing REQUIRED slots by name;
    never maps by substring (a substring rule maps 'LeftHandIndex1' onto the hand)."""
    s = set(names)
    m = {slot: src for slot, src in table.items() if src in s}
    missing = [r for r in required if r not in m]
    return m, missing


def substring_map(names, slot_words):
    """FALSIFIER: map each slot to the first bone whose lower-cased name contains every word. Ambiguous by construction."""
    out = {}
    for slot, words in slot_words.items():
        for n in names:
            if all(w in n.lower() for w in words):
                out[slot] = n
                break
    return out


def synthesize_chain(present, fractions):
    """Missing joints of one chain placed at the reference skeleton's arc-length FRACTIONS along the source polyline.
    present: [(slot, xyz)] ordered root->tip with the first and last slot present; fractions: {slot: f in [0,1]} for EVERY
    slot of the reference chain (from the reference skeleton, measured the same way). Returns {slot: xyz} for all slots."""
    pts = np.array([p for _s, p in present], float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    total = cum[-1]
    if total <= 0:
        raise ValueError("chain has no length")
    out = {s: np.asarray(p, float) for s, p in present}
    for slot, f in fractions.items():
        if slot in out:
            continue
        d = f * total
        i = int(np.searchsorted(cum, d, side="right") - 1)
        i = min(max(i, 0), len(seg) - 1)
        u = (d - cum[i]) / seg[i]
        out[slot] = pts[i] + u * (pts[i + 1] - pts[i])
    return out


def midpoint_synthesis(a, b):
    """FALSIFIER (MB CreateRig: a new bone at the cursor snapped to two selected bones): the midpoint, whatever the reference."""
    return (np.asarray(a, float) + np.asarray(b, float)) / 2.0

# ----------------------------------------------------------------------------- R02 rest frames and axis conventions (canon 17)

def along_axis_angle(R_rest, head, child_head, axis="y"):
    """Angle between the bone's local `axis` and the head->child direction: ~0 for a Blender-native bone (Y along the
    limb), ~90 for a bone carrying UE axes inside Blender (X along the limb, Y off-limb)."""
    k = "xyz".index(axis)
    return float(np.degrees(np.arccos(np.clip(R_rest[:, k] @ unit(np.asarray(child_head) - np.asarray(head)), -1, 1))))


def classify_convention(angles, tol=10.0):
    """'blender' when every measured angle is within tol of 0, 'ue_axes' when within tol of 90 (either sign of the along
    axis), 'mixed' otherwise: a mixed rig is refused, never exported."""
    a = np.asarray(angles, float)
    if (a <= tol).all():
        return "blender"
    if (np.abs(a - 90.0) <= tol).all():
        return "ue_axes"
    return "mixed"


def damped_track(R, axis, target_dir):
    """FALSIFIER (MB CreateRig: Damped Track / Locked Track then Apply Pose as Rest): the MINIMAL rotation turning the
    frame's `axis` column onto target_dir, applied to whatever frame came in - the result's roll is the input's roll."""
    k = "xyz".index(axis)
    a, b = R[:, k], unit(target_dir)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return R.copy()
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    Rm = np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))
    return Rm @ R


def frame_from(head, child_head, up_hint, along="y", sign=1.0):
    """A rest frame with `along` (y or x) pointing sign*(child-head) and the next axis from up_hint by Gram-Schmidt.
    Deterministic: depends only on the joint positions and the up hint (the reference skeleton's axis, transported)."""
    a = sign * unit(np.asarray(child_head, float) - np.asarray(head, float))
    u = np.asarray(up_hint, float) - (np.asarray(up_hint, float) @ a) * a
    u = unit(u)
    if along == "y":          # columns X, Y, Z with Y along, Z = up hint
        X = np.cross(a, u)
        R = np.column_stack([X, a, u])
    else:                     # UE axes in Blender: X along, Z = up hint
        Y = np.cross(u, a)
        R = np.column_stack([a, Y, u])
    if np.linalg.det(R) < 0:
        raise ValueError("left-handed frame")
    return R

# ----------------------------------------------------------------------------- R03 apply object scale (canon 18)

def scaled_rest_rotation(R_rest, S):
    """The rotation a bone keeps after its armature's scale S (3x3 diagonal) is applied to the rest: the polar factor of S R."""
    U, _s, Vt = np.linalg.svd(np.diag(S) @ R_rest)
    Q = U @ Vt
    if np.linalg.det(Q) < 0:
        U[:, -1] *= -1
        Q = U @ Vt
    return Q


def apply_scale_loc_exact(R_rest, S, loc):
    """New pose-bone location after applying object scale S: the same world offset expressed in the new rest frame:
    loc' = R'^T S R loc. Exact for any S and any bone orientation."""
    Rn = scaled_rest_rotation(R_rest, S)
    return Rn.T @ (np.diag(S) @ (R_rest @ np.asarray(loc, float))), Rn


def apply_scale_loc_componentwise(S, loc):
    """FALSIFIER (GRT addition/utils.py:110-123): multiply each location channel by the OBJECT scale of the same index."""
    return np.asarray(S, float) * np.asarray(loc, float)

# ----------------------------------------------------------------------------- R04 retarget (canon 19)

def retarget_world(Ws, Rs_rest, Rt_rest):
    """Target world rotation W = Ws Rs_rest^-1 Rt_rest: the source bone's world change applied to the target's rest
    (Lampway features/animation.py:7-8, 234)."""
    return Ws @ Rs_rest.T @ Rt_rest


def retarget_local_copy(Ws, Rs_rest, Rt_rest):
    """FALSIFIER (a Copy Rotation in local space, or a key copy): the source's rest-relative rotation applied in the
    TARGET's own local frame: W = Rt_rest (Rs_rest^-1 Ws). Right only when the rests coincide."""
    return Rt_rest @ (Rs_rest.T @ Ws)


def local_from_world(W_child, W_parent, R_child_rest, R_parent_rest):
    """Pose-bone basis rotation (rest-relative, parent-relative) that produces world W_child under a parent at W_parent."""
    rest_local = R_parent_rest.T @ R_child_rest
    return rest_local.T @ (W_parent.T @ W_child)

# ----------------------------------------------------------------------------- R05 root motion (canon 19)

def root_from_pelvis(P, yaw="none", forward_local=(0.0, -1.0, 0.0)):
    """Root motion from a pelvis world transform P (4x4): root translation = the pelvis's ground projection (x, y, 0); root
    rotation = identity (yaw='none') or the heading of the pelvis forward axis projected on the ground (yaw='heading');
    never pitch or roll. Returns (root 4x4, pelvis-local 4x4) with root @ local == P exactly."""
    Rt = np.eye(4)
    Rt[:2, 3] = P[:2, 3]
    if yaw == "heading":
        f = P[:3, :3] @ np.asarray(forward_local, float)
        h = np.arctan2(f[0], -f[1])           # heading of -Y forward in the ground plane, radians
        Rt[:3, :3] = rot("z", np.degrees(h))
    elif yaw != "none":
        raise ValueError("yaw is none | heading")
    local = np.linalg.inv(Rt) @ P
    return Rt, local


def root_copy_full_rotation(P):
    """FALSIFIER: the root copies the pelvis's whole rotation (pitch and roll included) - the root tilts."""
    Rt = np.eye(4)
    Rt[:2, 3] = P[:2, 3]
    Rt[:3, :3] = P[:3, :3]
    return Rt


def tilt_deg(R):
    """Angle between the transform's local Z and world Z."""
    return float(np.degrees(np.arccos(np.clip(R[:3, 2] @ np.array([0, 0, 1.0]), -1, 1))))

# ----------------------------------------------------------------------------- R06 template fit (canon 20)

def fit_template(template_heads, parents, target_heads):
    """Place every template joint at the measured target joint (the joints ARE the fit) and report per-bone length ratios
    target/template. A missing target joint refuses (it is never borrowed from the template or another body)."""
    missing = [n for n in template_heads if n not in target_heads]
    if missing:
        raise ValueError(f"target joints missing: {missing}")
    heads = {n: np.asarray(target_heads[n], float) for n in template_heads}
    ratios = {}
    for n, p in parents.items():
        if p is None:
            continue
        lt = np.linalg.norm(np.asarray(template_heads[n]) - np.asarray(template_heads[p]))
        lf = np.linalg.norm(heads[n] - heads[p])
        ratios[n] = lf / lt
    return heads, ratios


def copied_not_fitted(ratios, tol=0.001):
    """True when every bone length equals the template's within tol (0.1 %): the joints were copied from the template's own
    body (the 2026-09-28 defect), not measured on the example."""
    return bool(all(abs(r - 1.0) <= tol for r in ratios.values()))

# ----------------------------------------------------------------------------- shared

def rms(a):
    a = np.asarray(a, float)
    return float(np.sqrt((a ** 2).mean()))
