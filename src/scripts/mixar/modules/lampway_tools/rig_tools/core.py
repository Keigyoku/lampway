# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig tools' pure core (canon pages 16-18 and 21; specs/canon/rig_tools): numpy only, no bpy. The Blender side (features/rig_tools.py)
reads an armature into names, heads, parents, rest frames and keys, and hands them here.

* canon 16 (mapping): the naming family is the table naming the most source bones (a tie refuses); slots map by the table, never by a
  substring; a missing joint is placed at the reference chain's arc-length fraction along the source polyline, never at a midpoint.
* canon 17 (rest frames): a frame is built from the joints and an up hint (Gram-Schmidt), never by tracking an existing frame (whose roll
  would survive); the convention is the angle between a bone's local Y (Blender) or X (UE axes) and its head -> next-joint line.
* canon 18 (units and scale): a uniform or non-uniform object scale is applied exactly (loc' = R'^T S R loc, R' the polar factor of S R);
  the unit factor is a known factor within 5 %, or a refusal.
* canon 21 (read-back): the bind_mismatch bars, 0.01 cm, 0.01 deg, 1e-4 scale, per bone.

The canon's reference implementations (specs/canon/goldens/rig_reference.py) are the source of the maths; the goldens R01-R03 are the tests."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

FAMILIES = Path(__file__).with_name("families")
# The UE5 mannequin slots (canon 16 B.1): MB's 79 slot targets, named as CreateRig renames them.
UE_SLOTS = ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head") + tuple(
    f"{b}_{s}" for s in ("l", "r") for b in (
        "clavicle", "upperarm", "upperarm_twist_01", "upperarm_twist_02", "lowerarm", "lowerarm_twist_01", "lowerarm_twist_02", "hand",
        "thigh", "thigh_twist_01", "thigh_twist_02", "calf", "calf_twist_01", "calf_twist_02", "foot", "ball",
        "thumb_01", "thumb_02", "thumb_03", "index_metacarpal", "index_01", "index_02", "index_03", "middle_metacarpal", "middle_01", "middle_02",
        "middle_03", "ring_metacarpal", "ring_01", "ring_02", "ring_03", "pinky_metacarpal", "pinky_01", "pinky_02", "pinky_03"))
REQUIRED = {
    "ue5_body": ("pelvis", "spine_01", "head") + tuple(f"{b}_{s}" for s in ("l", "r") for b in ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot")),
}
REQUIRED["ue5_body_fingers"] = REQUIRED["ue5_body"] + tuple(f"{f}_{n}_{s}" for s in ("l", "r") for f in ("thumb", "index", "middle", "ring", "pinky")
                                                            for n in ("01", "02", "03"))
REQUIRED["metahuman"] = REQUIRED["ue5_body_fingers"]
TORSO = ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05")
KNOWN_UNITS = {1.0: 1.0, 100.0: 0.01, 0.01: 100.0, 39.37007874: 0.0254, 3.280839895: 0.3048}
BARS = {"position_cm": 0.01, "rotation_deg": 0.01, "scale": 1e-4}


class RigRefused(ValueError):
    pass


def sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=float).encode()).hexdigest()


# ---------------------------------------------------------------- canon 16
def load_family(name):
    p = FAMILIES / f"{name}.json"
    if not p.exists():
        raise RigRefused(f"no shipped table for family {name!r}: the shipped families are {', '.join(families())}; pass a map file instead")
    return json.loads(p.read_text())


def families():
    return sorted(p.stem for p in FAMILIES.glob("*.json"))


def detect_family(names, tables):
    """(family, hits): the table naming the most source bones; a tie or no hit refuses (INV-16.5)."""
    s = set(names)
    hits = {fam: sum(1 for src in t.values() if src in s) for fam, t in tables.items()}
    best = max(hits.values()) if hits else 0
    top = sorted(f for f, h in hits.items() if h == best)
    if best == 0 or len(top) > 1:
        raise RigRefused(f"no single naming family matches (hits {hits}): pass family= or a map file")
    return top[0], hits


def map_slots(names, table, required):
    """({slot: source}, [missing required]) from a family table; never a substring guess."""
    s = set(names)
    m = {slot: src for slot, src in table.items() if src in s}
    return m, [r for r in required if r not in m]


def chain_fractions(chain):
    """{slot: arc-length fraction} along a reference chain [(slot, xyz)] ordered root -> tip."""
    pts = np.array([p for _s, p in chain], float)
    cum = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    if cum[-1] <= 0:
        raise RigRefused("the reference chain has no length")
    return {s: round(float(c / cum[-1]), 9) for (s, _p), c in zip(chain, cum)}


def synthesize_chain(present, fractions):
    """{slot: xyz} for every slot of the reference chain: the present ones as they are, the missing ones at their reference fraction of the
    source polyline (canon 16 B.4). Needs at least two mapped joints on the chain."""
    if len(present) < 2:
        raise RigRefused("a synthesized slot needs a chain with at least two mapped joints")
    pts = np.array([p for _s, p in present], float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    if cum[-1] <= 0:
        raise RigRefused("the source chain has no length")
    out = {s: np.asarray(p, float) for s, p in present}
    for slot, f in fractions.items():
        if slot in out:
            continue
        d = f * cum[-1]
        i = min(max(int(np.searchsorted(cum, d, side="right") - 1), 0), len(seg) - 1)
        out[slot] = pts[i] + (d - cum[i]) / seg[i] * (pts[i + 1] - pts[i])
    return out


# ---------------------------------------------------------------- canon 17
def rot(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise RigRefused("zero-length vector")
    return v / n


def angle_deg(Ra, Rb):
    return float(np.degrees(np.arccos(np.clip((np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0, -1.0, 1.0))))


def along_axis_angle(R_rest, head, child_head, axis="y"):
    k = "xyz".index(axis)
    return float(np.degrees(np.arccos(np.clip(np.asarray(R_rest)[:, k] @ unit(np.subtract(child_head, head)), -1, 1))))


def classify_convention(angles, tol=10.0):
    """'blender' (local Y along every limb), 'ue_axes' (X along: Y at 90 deg), or 'mixed' (refused downstream, never exported)."""
    a = np.asarray(angles, float)
    if not len(a):
        return "unknown"
    if (a <= tol).all():
        return "blender"
    if (np.abs(a - 90.0) <= tol).all():
        return "ue_axes"
    return "mixed"


def damped_track(R, axis, target_dir):
    """The upstream (MB CreateRig) method, kept as the falsifier: the minimal rotation onto target_dir keeps the input's roll."""
    k = "xyz".index(axis)
    a, b = R[:, k], unit(target_dir)
    v = np.cross(a, b)
    if np.linalg.norm(v) < 1e-12:
        return R.copy()
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return (np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + float(a @ b)))) @ R


def frame_from(head, child_head, up_hint, along="y", sign=1.0):
    a = sign * unit(np.subtract(child_head, head))
    u = unit(np.asarray(up_hint, float) - (np.asarray(up_hint, float) @ a) * a)
    R = np.column_stack([np.cross(a, u), a, u]) if along == "y" else np.column_stack([a, np.cross(u, a), u])
    if np.linalg.det(R) < 0:
        raise RigRefused("left-handed frame")
    return R


# ---------------------------------------------------------------- canon 18
def scaled_rest_rotation(R_rest, S):
    U, _s, Vt = np.linalg.svd(np.diag(S) @ np.asarray(R_rest, float))
    Q = U @ Vt
    if np.linalg.det(Q) < 0:
        U[:, -1] *= -1
        Q = U @ Vt
    return Q


def apply_scale_loc_exact(R_rest, S, loc):
    """(loc', R'): the same world offset in the new rest frame after the armature's scale S is applied (exact for any S)."""
    Rn = scaled_rest_rotation(R_rest, S)
    return Rn.T @ (np.diag(S) @ (np.asarray(R_rest, float) @ np.asarray(loc, float))), Rn


def unit_factor(measured_height, reference_height):
    """(factor, ratio): the factor that brings the rig to the reference's units, a known factor within 5 %, else refused."""
    if measured_height <= 0 or reference_height <= 0:
        raise RigRefused("a height is zero: nothing to measure the units from")
    ratio = float(measured_height / reference_height)
    for known, factor in KNOWN_UNITS.items():
        if abs(ratio / known - 1.0) <= 0.05:
            return factor, ratio
    raise RigRefused(f"the rig is {ratio:.4g} x the reference: not within 5 % of a known unit factor ({', '.join(f'{k:g}' for k in KNOWN_UNITS)}); "
                     "pass unit= explicitly or check the reference")


# ---------------------------------------------------------------- canon 21
def _qangle_deg(a, b):
    a, b = unit(a), unit(b)
    d = abs(float(np.dot(a, b)))
    return float(np.degrees(2 * math.acos(min(1.0, d))))


def readback_rows(reference, readback, bars=BARS):
    """Per-bone rows of the read-back against the reference ({bone: {translation cm, rotation xyzw, scale}}): over-tolerance rows named."""
    if set(reference) != set(readback):
        raise RigRefused(f"the read-back roster differs: missing {sorted(set(reference) - set(readback))}, extra {sorted(set(readback) - set(reference))}")
    rows, over = [], []
    for b in sorted(reference):
        r, g = reference[b], readback[b]
        row = {"bone": b, "position_cm": float(np.linalg.norm(np.subtract(g["translation"], r["translation"]))),
               "rotation_deg": _qangle_deg(r["rotation"], g["rotation"]), "scale": float(np.max(np.abs(np.subtract(g["scale"], r["scale"]))))}
        rows.append(row)
        if row["position_cm"] > bars["position_cm"] or row["rotation_deg"] > bars["rotation_deg"] or row["scale"] > bars["scale"]:
            over.append(row)
    return {"bones_compared": len(rows), "worst_position_cm": max(r["position_cm"] for r in rows), "worst_rotation_deg": max(r["rotation_deg"] for r in rows),
            "worst_scale": max(r["scale"] for r in rows), "over_tolerance": over, "bars": dict(bars), "rows": rows}
