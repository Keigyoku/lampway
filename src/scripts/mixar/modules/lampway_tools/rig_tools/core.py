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
    """The angle between two rotations by the chord ||Ra - Rb||_F = 2 sqrt(2) sin(theta / 2): well conditioned near 0, where an arccos of
    the trace reads float32 rounding (a Blender rest) as ~0.02 deg."""
    c = float(np.linalg.norm(np.asarray(Ra, float) - np.asarray(Rb, float))) / (2.0 * math.sqrt(2.0))
    return float(np.degrees(2.0 * math.asin(min(1.0, c))))


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


# ---------------------------------------------------------------- rig_conform (canon 16 B.4-B.7, 17): the plan, applied by features/rig_conform
CONVENTIONS = {"blender": "y", "ue_axes": "x"}
ENGINE_FROM_BLENDER = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
# the continuation of every UE limb bone that has helper children beside its next joint (canon 01 C; canon_geom.bones.CONTINUATION)
CONTINUATION = dict({f"{a}_{s}": f"{b}_{s}" for s in ("l", "r") for a, b in (("clavicle", "upperarm"), ("upperarm", "lowerarm"), ("lowerarm", "hand"),
                                                                          ("thigh", "calf"), ("calf", "foot"), ("foot", "ball"), ("hand", "middle_01"))},
                    pelvis="spine_01", spine_03="spine_04", spine_05="neck_01", neck_01="neck_02", neck_02="head")
# UE's IK bones and the bone each one stands on (the mannequin's convention: ik_hand_gun on the right hand)
IK_TARGETS = {"ik_foot_root": "root", "ik_foot_l": "foot_l", "ik_foot_r": "foot_r", "ik_hand_root": "root", "ik_hand_gun": "hand_r",
              "ik_hand_l": "hand_l", "ik_hand_r": "hand_r"}
ROOT_LENGTH = 0.1                                     # metres: the length of a synthesized root (a root has no next joint to measure)


def _descendant(b, a, parents):
    seen = set()
    while b is not None and b not in seen:
        seen.add(b)
        b = parents.get(b)
        if b == a:
            return True
    return False


def _next_joint(b, heads, parents, kids, ref_kids):
    """The joint a bone points at: its named continuation, else its single reference child, else its single child (a distinct head), else
    its parent's line continued (a leaf); None when nothing defines a direction."""
    h = np.asarray(heads[b], float)
    c = CONTINUATION.get(b)
    if c in heads and _descendant(c, b, parents) and np.linalg.norm(np.subtract(heads[c], h)) > 1e-9:
        return np.asarray(heads[c], float)
    for group in (ref_kids.get(b, []), kids.get(b, [])):
        far = [k for k in group if k in heads and np.linalg.norm(np.subtract(heads[k], h)) > 1e-9]
        if len(far) == 1:
            return np.asarray(heads[far[0]], float)
    p = parents.get(b)
    if p is not None and np.linalg.norm(h - np.asarray(heads[p], float)) > 1e-9:
        return h + (h - np.asarray(heads[p], float))
    return None


def _up(candidates, along):
    for c in candidates:
        c = np.asarray(c, float)
        if abs(float(unit(c) @ along)) < 0.99:
            return c
    return None


def source_copy_plan(src, mapping, synthesized, convention, measured_convention, offsets=None, ik_bones=False):
    """An exact native rest copy, not reference fitting or engine calibration."""
    from ..canon_geom import native_topology as NT
    try:
        roster = NT.audit(src["parents"])
    except ValueError as error:
        raise RigRefused(str(error)) from None
    if not roster["complete"] or set(src["names"]) != set(NT.PARENTS):
        raise RigRefused("source_copy requires the complete verified native topology")
    if convention not in CONVENTIONS or measured_convention != convention:
        raise RigRefused(f"source_copy input convention is {measured_convention}, requested {convention}: inspect the untouched source; no frame conversion is performed")
    if (synthesized or offsets or ik_bones or any(slot != name or name not in src["parents"] for slot, name in mapping.items())):
        raise RigRefused("source_copy requires identity mapping, no synthesis, IK or offsets")
    bones = [{"name": name, "source": name, "kind": "mapped" if name in mapping else "unmapped",
              "parent": src["parents"][name], "head": src["heads"][name],
              "frame": src["frames"][name], "length": src["lengths"][name]} for name in src["names"]]
    return {"bones": bones, "renamed": {}, "synthesized": {}, "reparented": [],
            "frames": {}, "unreferenced": [], "convention": convention}


def native_reference_plan(src, mapping, synthesized, ref, convention, offsets, ik_bones):
    """Carry an independent native bind through the declared writer axes.

    This bounded calibration applies only to the complete native graph at the
    reference joints. It does not fit another body or infer helper directions.
    """
    from ..canon_geom import native_topology as NT
    if set(src["names"]) != set(NT.PARENTS) or src["parents"] != NT.PARENTS:
        raise RigRefused("native bind calibration requires the complete verified source topology")
    if len(ref["names"]) != len(NT.PARENTS) or set(ref["names"]) != set(NT.PARENTS) or ref["parents"] != NT.PARENTS:
        raise RigRefused("native bind calibration requires the complete independent native reference topology")
    if synthesized or offsets or ik_bones or any(n != s or n not in src["parents"] for n, s in mapping.items()):
        raise RigRefused("native bind calibration requires identity mapping, no synthesis, IK or offsets")
    bridge = ENGINE_FROM_BLENDER if convention == "blender" else np.eye(3)
    bones = []
    for n in src["names"]:
        head = np.asarray(src["heads"][n], float)
        reference_head = np.asarray(ref["heads"][n], float)
        R = np.asarray(ref["frames"][n], float)
        scale = np.asarray(ref.get("scales", {}).get(n, [1, 1, 1]), float)
        if scale.shape != (3,) or not np.isfinite(scale).all() or np.max(np.abs(scale - 1)) > BARS["scale"]:
            raise RigRefused(f"{n}: independent native reference scale exceeds the unchanged bind scale bar")
        if (head.shape != (3,) or reference_head.shape != (3,) or
                not np.isfinite(head).all() or not np.isfinite(reference_head).all() or
                np.linalg.norm(head - reference_head) * 100 > BARS["position_cm"]):
            raise RigRefused(f"{n}: native reference joints differ beyond the unchanged bind position bar; provide the matching native reference")
        if (R.shape != (3, 3) or not np.isfinite(R).all() or
                np.max(np.abs(R.T @ R - np.eye(3))) > 1e-6 or abs(np.linalg.det(R) - 1) > 1e-6):
            raise RigRefused(f"{n}: independent native reference frame is not a proper rigid rotation")
        bones.append({"name": n, "source": n, "kind": "mapped" if n in mapping else "unmapped",
                      "parent": src["parents"][n], "head": src["heads"][n],
                      "frame": R @ bridge.T, "length": src["lengths"][n]})
    return {"bones": bones, "renamed": {}, "synthesized": {}, "reparented": [],
            "frames": {n: 0.0 for n in src["names"]}, "unreferenced": [], "convention": convention,
            "reference_scope": "independent_native_bind"}


def reference_bind_convention(rig, receipt, fingerprint):
    """Declared writer convention, verified against every independent bind row.

    Joint alignment remains a separate diagnostic for authored native frames.
    This admits recipe routing, never an actual-engine acceptance claim.
    """
    from ..canon_geom import native_topology as NT
    if (receipt.get("schema") != "lampway.native-reference-bind/1" or
            receipt.get("output_rest") != fingerprint or rig["parents"] != NT.PARENTS or
            set(rig["names"]) != set(NT.PARENTS)):
        raise RigRefused("native reference bind receipt is stale or has unsupported topology; conform against the independent native reference again")
    convention = receipt.get("convention")
    reference_sha = receipt.get("reference_sha256", "")
    binds = receipt.get("binds", {})
    if (convention not in CONVENTIONS or len(reference_sha) != 64 or
            any(c not in "0123456789abcdef" for c in reference_sha) or
            set(binds) != set(NT.PARENTS) or receipt.get("binds_sha256") != sha(binds)):
        raise RigRefused("native reference bind receipt has invalid convention, source pin or bind rows")
    bridge = ENGINE_FROM_BLENDER if convention == "blender" else np.eye(3)
    for n in rig["names"]:
        expected = binds[n]
        head = np.asarray(expected["head_m"], float)
        R = np.asarray(expected["frame_engine"], float)
        scale = np.asarray(rig.get("scales", {}).get(n, [1, 1, 1]), float)
        if (head.shape != (3,) or R.shape != (3, 3) or not np.isfinite(head).all() or not np.isfinite(R).all() or
                np.max(np.abs(R.T @ R - np.eye(3))) > 1e-6 or abs(np.linalg.det(R) - 1) > 1e-6 or
                np.linalg.norm(np.asarray(rig["heads"][n]) - head) * 100 > BARS["position_cm"] or
                angle_deg(np.asarray(rig["frames"][n]) @ bridge, R) > BARS["rotation_deg"] or
                scale.shape != (3,) or not np.isfinite(scale).all() or np.max(np.abs(scale - 1)) > BARS["scale"]):
            raise RigRefused(f"{n}: native reference bind receipt exceeds an unchanged bind bar; conform against the independent native reference again")
    return convention


def conform_plan(src, mapping, synthesized, ref, convention="blender", offsets=None, ik_bones=False):
    """The conformed skeleton as a plan (no Blender): {bones: [{name, source, kind, parent, head, frame, length}] parents first, renamed,
    synthesized, reparented, frames: {bone: angle to the reference re-expressed in the convention, deg}, unreferenced}.

    src / ref: {names, parents, heads, frames (3x3, columns X Y Z)} in one space (src also lengths); mapping {slot: source bone};
    synthesized {slot: arc-length fraction on the torso}. Heads never move; frames come from the joints and the reference's Z (canon 17),
    never from the source's frame, so the input roll cannot survive."""
    if convention not in CONVENTIONS:
        raise RigRefused(f"convention is blender or ue_axes, not {convention!r}: one convention per rig (a mixed rig is never exported)")
    from ..canon_geom import native_topology as NT
    if set(src["names"]) == set(NT.PARENTS):
        return native_reference_plan(src, mapping, synthesized, ref, convention, offsets, ik_bones)
    along = CONVENTIONS[convention]
    offsets = dict(offsets or {})
    inv = {s: k for k, s in mapping.items()}
    missing = sorted(s for s in mapping.values() if s not in src["heads"])
    if missing:
        raise RigRefused(f"the map names bones the armature does not have: {', '.join(missing)}")
    slots = set(mapping) | set(synthesized) | (set(IK_TARGETS) | {"root"} if ik_bones else set())
    taken = set(slots) | set(src["names"])
    renamed = {}
    for b in src["names"]:
        if b in inv:
            renamed[b] = inv[b]
        elif b in slots:                                  # an unmapped bone named like a slot this rig will carry: out of the way first
            n, k = f"{b}_src", 1
            while n in taken:
                k += 1
                n = f"{b}_src{k}"
            taken.add(n)
            renamed[b] = n
    out = lambda b: renamed.get(b, b)                     # noqa: E731
    heads, kinds, source, lengths = {}, {}, {}, {}
    for b in src["names"]:
        n = out(b)
        heads[n], kinds[n], source[n], lengths[n] = tuple(float(x) for x in src["heads"][b]), "mapped" if b in inv else "unmapped", b, float(src["lengths"][b])
    synth_doc = {}
    if synthesized:
        present = [(s, src["heads"][mapping[s]]) for s in TORSO if s in mapping]
        made = synthesize_chain(present, dict(synthesized))
        for s in synthesized:
            heads[s], kinds[s], source[s] = tuple(float(x) for x in made[s]), "synthesized", None
            synth_doc[s] = {"rule": "torso arc-length fraction", "fraction": synthesized[s], "head": list(heads[s])}
    rparents = ref["parents"]
    if ik_bones:
        need = sorted({t for t in IK_TARGETS.values() if t != "root"} - set(heads))
        if need:
            raise RigRefused(f"ik_bones stand on {', '.join(need)}, which this rig does not carry: map them, or pass ik_bones=false")
        if "root" not in heads:
            heads["root"], kinds["root"], source["root"], lengths["root"] = (0.0, 0.0, 0.0), "synthesized", None, ROOT_LENGTH
            synth_doc["root"] = {"rule": "ik_bones: the reference's root at the armature origin", "head": [0.0, 0.0, 0.0]}
        for ik, t in IK_TARGETS.items():
            heads[ik], kinds[ik], source[ik] = heads[t], "ik", None
            synth_doc[ik] = {"rule": f"ik bone on {t}", "head": list(heads[t])}
    # parents: a reference slot hangs from its nearest reference ancestor this rig carries; everything else keeps its (renamed) parent
    parents = {}
    for n in heads:
        p = None
        if n in rparents or n in IK_TARGETS:
            a = rparents.get(n)
            while a is not None and a not in heads:
                a = rparents.get(a)
            p = a
        if p is None and source[n] is not None and src["parents"].get(source[n]) is not None:
            p = out(src["parents"][source[n]])
        parents[n] = p
    order, state = [], {}

    def visit(n, trail=()):
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            raise RigRefused(f"the reference hierarchy and the source's make a cycle through {' -> '.join(trail + (n,))}")
        state[n] = 1
        if parents[n] is not None:
            visit(parents[n], trail + (n,))
        state[n] = 2
        order.append(n)
    for n in heads:
        visit(n)
    reparented = [{"bone": n, "from": out(src["parents"][source[n]]) if src["parents"].get(source[n]) else None, "to": parents[n]}
                  for n in order if source[n] is not None and (out(src["parents"][source[n]]) if src["parents"].get(source[n]) else None) != parents[n]]
    kids, ref_kids = {}, {}
    for n, p in parents.items():
        if p is not None:
            kids.setdefault(p, []).append(n)
    for n, p in rparents.items():
        if p is not None:
            ref_kids.setdefault(p, []).append(n)
    rkids_present = {b: [k for k in v if k in heads] for b, v in ref_kids.items()}
    unknown = sorted(set(offsets) - set(heads))
    if unknown:
        raise RigRefused(f"offsets: no bone named {unknown[0]!r} in the conformed rig")
    ref_up = {}
    for n in order:                                      # the up hint: the reference bone's Z, else the nearest referenced ancestor's
        a = n
        while a is not None and a not in ref["frames"]:
            a = parents.get(a)
        ref_up[n] = a
    def ref_sign(n):
        """-1 where the reference's X points back along its limb (UE's mirrored side), for the ue_axes convention; else +1."""
        if along != "x" or n not in ref["frames"]:
            return 1.0
        rn = _next_joint(n, ref["heads"], rparents, ref_kids, ref_kids)
        return -1.0 if rn is not None and float(np.asarray(ref["frames"][n], float)[:, 0] @ (rn - np.asarray(ref["heads"][n], float))) < 0 else 1.0

    frames, angles, unreferenced = {}, {}, []
    for n in order:
        r = ref_up[n]
        if n in IK_TARGETS and IK_TARGETS[n] in frames:
            frames[n] = frames[IK_TARGETS[n]]
            continue
        nxt = _next_joint(n, heads, parents, kids, rkids_present)
        if nxt is None:
            if r is None:
                raise RigRefused(f"{n!r} has no next joint and no referenced ancestor: nothing defines its frame")
            R = np.asarray(ref["frames"][r], float)
        else:
            d = unit(nxt - np.asarray(heads[n], float))
            cand = [np.asarray(ref["frames"][r], float)[:, k] for k in (2, 0, 1)] if r is not None else []
            cand.append(np.asarray(src["frames"][source[n]], float)[:, 2] if source[n] is not None else (0.0, 0.0, 1.0))
            up = _up(cand, d)
            if up is None:
                raise RigRefused(f"{n!r} points along every up hint it has: pass an offset or map it")
            R = frame_from(heads[n], nxt, up, along=along, sign=ref_sign(n))
        roll = float(offsets.get(n, {}).get("roll_deg", 0.0))
        if roll:
            R = R @ rot(along, roll)
        frames[n] = R
        if n in ref["frames"] and nxt is not None:
            rn = _next_joint(n, ref["heads"], rparents, ref_kids, ref_kids)
            if rn is not None:
                Rr = frame_from(ref["heads"][n], rn, np.asarray(ref["frames"][n], float)[:, 2], along=along, sign=ref_sign(n))
                angles[n] = round(angle_deg(R, Rr), 6)
        elif n not in ref["frames"]:
            unreferenced.append(n)
        if n not in lengths:
            lengths[n] = float(np.linalg.norm(nxt - np.asarray(heads[n], float))) if nxt is not None else ROOT_LENGTH
    for n in order:
        if n in IK_TARGETS and n not in lengths:
            lengths[n] = lengths.get(IK_TARGETS[n], ROOT_LENGTH)
    bones = [{"name": n, "source": source[n], "kind": kinds[n], "parent": parents[n], "head": heads[n], "frame": frames[n], "length": lengths[n]}
             for n in order]
    return {"bones": bones, "renamed": {b: n for b, n in renamed.items() if b != n}, "synthesized": synth_doc, "reparented": reparented,
            "frames": angles, "unreferenced": unreferenced, "convention": convention}


# ---------------------------------------------------------------- rig_fit_template (canon 20): the joints ARE the fit
# TITAN rig-axi's REQUIRED_JOINTS (the body grammar a joints file must measure; rig-axi is the prior art, the list reused)
REQUIRED_JOINTS = (("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head")
                   + tuple(f"{b}_{s}" for s in ("l", "r") for b in ("clavicle", "upperarm", "lowerarm", "hand"))
                   + tuple(f"{b}_{s}" for s in ("l", "r") for b in ("thigh", "calf", "foot", "ball"))
                   + tuple(f"{f}_{k}_{s}" for s in ("l", "r") for f in ("thumb", "index", "middle", "ring", "pinky") for k in ("01", "02", "03")))
COPIED_TOL = 0.001                                    # canon 20 B.3: every bone length within 0.1 % of the template's = copied, not fitted


def _parents_first(names, parents):
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        if parents.get(n) is not None and parents[n] in names:
            visit(parents[n])
        order.append(n)
    for n in names:
        visit(n)
    return order


def fit_template(template, joints, required):
    """{heads, ratios, copied_not_fitted, residual, synthesized, measured, unused}: the template's joint heads set to the measured joints
    (canon 20 B.2; R06: residual 0), every other template bone placed by its nearest measured segment (the template's offset from the
    segment's start, carried by the similarity that takes the template segment onto the measured one) or, with no such segment above it,
    by the similarity of all measured joints. A required joint missing refuses: it is never borrowed from the template."""
    from ..canon_geom.rigid import apply_similarity, similarity_fit
    names = list(template["names"])
    T = {n: np.asarray(template["heads"][n], float) for n in names}
    parents = template["parents"]
    missing = [n for n in required if n in T and n not in joints]
    if missing:
        raise RigRefused(f"required joints missing from the joints file: {', '.join(missing)}; a joint is measured on the example, never "
                         "borrowed from the template")
    measured = {n: np.asarray(joints[n], float) for n in names if n in joints}
    heads = dict(measured)
    kids = {}
    for n in names:
        if parents.get(n) is not None:
            kids.setdefault(parents[n], []).append(n)

    def segment(a):
        c = CONTINUATION.get(a)
        if c not in measured:
            far = [k for k in kids.get(a, []) if k in measured and np.linalg.norm(T[k] - T[a]) > 1e-9]
            c = far[0] if len(far) == 1 else None
        if c is None or a not in heads or np.linalg.norm(T[c] - T[a]) < 1e-9 or np.linalg.norm(measured[c] - heads[a]) < 1e-9:
            return None
        return c

    glob = None
    synthesized = {}
    for n in _parents_first(names, parents):
        if n in heads:
            continue
        if n in IK_TARGETS and IK_TARGETS[n] in heads and IK_TARGETS[n] != "root":
            heads[n] = heads[IK_TARGETS[n]]
            synthesized[n] = {"rule": f"ik bone on {IK_TARGETS[n]}"}
            continue
        a = parents.get(n)
        while a is not None and segment(a) is None:
            a = parents.get(a)
        if a is not None:
            c = segment(a)
            up = np.asarray(template["frames"][a], float)[:, 2]
            dt, dm = T[c] - T[a], measured[c] - heads[a]
            if abs(float(unit(dt) @ unit(up))) > 0.99:
                up = np.asarray(template["frames"][a], float)[:, 0]
            Ft, Fm = frame_from(T[a], T[c], up), frame_from(heads[a], measured[c], up)
            s = float(np.linalg.norm(dm) / np.linalg.norm(dt))
            heads[n] = heads[a] + s * (Fm @ Ft.T @ (T[n] - T[a]))
            synthesized[n] = {"rule": f"segment {a} -> {c}", "scale": round(s, 9)}
        else:
            if glob is None:
                keys = sorted(measured)
                glob = similarity_fit([T[k] for k in keys], [measured[k] for k in keys])
            heads[n] = apply_similarity(glob, [T[n]])[0]
            synthesized[n] = {"rule": "similarity of all measured joints", "scale": round(glob["s"], 9)}
    ratios = {}
    for n in names:
        p = parents.get(n)
        if n in measured and p in measured:
            lt = float(np.linalg.norm(T[n] - T[p]))
            if lt > 1e-9:
                ratios[n] = float(np.linalg.norm(measured[n] - measured[p]) / lt)
    res = [float(np.linalg.norm(heads[n] - np.asarray(joints[n], float))) for n in measured]
    return {"heads": {n: tuple(float(x) for x in heads[n]) for n in names}, "ratios": ratios,
            "copied_not_fitted": bool(ratios) and all(abs(r - 1.0) <= COPIED_TOL for r in ratios.values()),
            "residual": {"rms_m": float(np.sqrt(np.mean(np.square(res)))) if res else 0.0, "max_m": max(res, default=0.0)},
            "synthesized": synthesized, "measured": sorted(measured), "unused": sorted(set(joints) - set(names))}


# ---------------------------------------------------------------- rig_retarget (canon 19 B.1, B.5)
def retarget_world(Ws, Rs_rest, Rt_rest):
    """The target bone's world rotation W_t = W_s R_s^-1 R_t: the source bone's world change applied to the target's rest (R04)."""
    return np.asarray(Ws, float) @ np.asarray(Rs_rest, float).T @ np.asarray(Rt_rest, float)


def local_from_world(W_child, W_parent, R_child_rest, R_parent_rest):
    """The pose basis rotation (rest-relative, parent-relative) giving W_child under a parent at W_parent."""
    rest_local = np.asarray(R_parent_rest, float).T @ np.asarray(R_child_rest, float)
    return rest_local.T @ (np.asarray(W_parent, float).T @ np.asarray(W_child, float))


def tilt_deg(R):
    """The angle between a transform's local Z and world Z."""
    z = np.asarray(R, float)[:3, 2]
    return float(np.degrees(2.0 * math.asin(min(1.0, float(np.linalg.norm(z - (0.0, 0.0, 1.0))) / 2.0))))


def root_from_pelvis(P, yaw="none", forward=(0.0, -1.0, 0.0)):
    """(root 4x4, pelvis-local 4x4), root @ local == P: the root at the pelvis's ground projection (x, y, 0), turned by nothing (none) or by
    the heading of the pelvis's forward axis on the ground (heading); never pitched or rolled (R05)."""
    P = np.asarray(P, float)
    root = np.eye(4)
    root[:2, 3] = P[:2, 3]
    if yaw == "heading":
        f = P[:3, :3] @ np.asarray(forward, float)
        root[:3, :3] = rot("z", float(np.degrees(np.arctan2(f[0], -f[1]))))
    elif yaw != "none":
        raise RigRefused(f"root_yaw is none | heading, not {yaw!r}")
    return root, np.linalg.inv(root) @ P


# ---------------------------------------------------------------- rig_rest_pose (canon 19 B.7, canon 04)
def return_cost(posed, rest, weights, mats, over_m=0.001):
    """What returning a baked rest would cost (R07): the blend of inverses sum_b w_b M_b^-1 v (a naive return through the new bind) against
    the exact inverse of the blend (canon 04), both measured from the posed points back to the original rest."""
    from ..canon_geom.lbs import lbs_inverse
    P, R0 = np.asarray(posed, float), np.asarray(rest, float)
    W, M = np.asarray(weights, float), np.asarray(mats, float)
    inv = np.linalg.inv(M)
    Ph = np.c_[P, np.ones(len(P))]
    naive = np.einsum("nb,bij,nj->ni", W, inv, Ph)[:, :3]
    err = np.linalg.norm(naive - R0, axis=1)
    exact = np.linalg.norm(lbs_inverse(P, W, M) - R0, axis=1)
    rigid = W.max(axis=1) > 1 - 1e-12
    return {"blend_of_inverses_max_m": float(err.max()) if len(err) else 0.0, "vertices_over_1mm": int((err > over_m).sum()),
            "exact_return_max_m": float(exact.max()) if len(exact) else 0.0,
            "rigid_vertices_error_m": float(err[rigid].max()) if rigid.any() else 0.0}
