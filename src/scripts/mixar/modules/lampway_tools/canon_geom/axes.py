# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 05 B.9 / INV-05.6: poses named from the body's JOINTS, never Euler angles on a rig's local axes.

Ported from Titan tools/armour_validate.py (its tests ported beside it), maths unchanged:
* quaternions are (x, y, z, w);
* ``resolve_axis``: 'up', 'forward', 'lateral' (= up x forward), a leading '-' negates; {'line': [a, b]} = b - a;
  {'perp': [a, b], 'to': <axis>} = (b - a) x axis; or an explicit 3-vector;
* ``pose_cs``: component-space bone transforms of a pose - an entry rotates a bone and everything below it about an axis given
  in component space AT REST, through that bone's joint; bones without an entry keep their rest local transform;
* ``expand_pose``: a finger curl {side, fraction} over the recipe's fingers about one axis;
* ``check_expect``: the pose's declared effect measured on the posed JOINTS - displacement along a named axis or approach to
  another joint - never the commanded angle read back (INV-05.5);
* ``control_shift``: the positive crossing control's push - along the closest (piece vertex, skin point) pair, as far as that
  skin point plus min(depth, half the piece's extent along the push) (golden C14);
* ``segment_box_overlap``: the slab test that selects a body edge crossing a piece's box with both ends outside it."""

import json
import math


def _finite(v):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)


def unit(v, what="vector"):
    v = tuple(float(x) for x in v)
    n = math.sqrt(sum(x * x for x in v)) if _finite(v) else 0.0
    if n <= 1e-12:
        raise ValueError(f"{what} has no direction")
    return tuple(x / n for x in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qinv(q):
    return (-q[0], -q[1], -q[2], q[3])


def qrot(q, v):
    x, y, z, _ = qmul(qmul(q, (v[0], v[1], v[2], 0.0)), qinv(q))
    return (x, y, z)


def qaxis(axis, deg):
    a = unit(axis, "axis")
    s = math.sin(math.radians(deg) / 2)
    return (a[0] * s, a[1] * s, a[2] * s, math.cos(math.radians(deg) / 2))


def resolve_axis(spec, joints, frame):
    """A component-space unit axis from a name, a joint line, a perpendicular or an explicit vector."""
    if isinstance(spec, str):
        sign, name = (-1.0, spec[1:]) if spec.startswith("-") else (1.0, spec)
        base = {"up": frame["up"], "forward": frame["forward"], "lateral": cross(frame["up"], frame["forward"])}.get(name)
        if base is None:
            raise ValueError(f"unknown axis name {spec!r}")
        return tuple(sign * x for x in unit(base, spec))
    if isinstance(spec, dict) and "line" in spec:
        a, b = (joints[j] for j in spec["line"])
        return unit(tuple(y - x for x, y in zip(a, b)), f"line {spec['line']}")
    if isinstance(spec, dict) and "perp" in spec:
        a, b = (joints[j] for j in spec["perp"])
        return unit(cross(tuple(y - x for x, y in zip(a, b)), resolve_axis(spec["to"], joints, frame)), f"perp {spec['perp']}")
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        return unit(spec, "axis")
    raise ValueError(f"unknown axis {spec!r}")


def pose_cs(ref, entries):
    """Posed component-space {bone: {rot, pos}} from the rest ``ref`` ({bone: {parent, rot (x,y,z,w), pos}}, parents before
    children) and pose ``entries`` [{bone, axis (component space, at rest, a 3-vector), deg}]."""
    local = {}
    for e in entries:
        if e.get("bone") not in ref:
            raise ValueError(f"pose names an unknown bone {e.get('bone')!r}")
        if not (isinstance(e.get("deg"), (int, float)) and math.isfinite(e["deg"])):
            raise ValueError(f"pose angle for {e['bone']} must be a finite number of degrees")
        r = ref[e["bone"]]["rot"]
        local[e["bone"]] = qmul(qmul(qinv(r), qaxis(e["axis"], e["deg"])), r)          # the rest-frame axis, in the bone
    out = {}
    for b, t in ref.items():
        p = t["parent"]
        if p is None:
            rot, pos = tuple(t["rot"]), tuple(t["pos"])
        else:
            if p not in out:
                raise ValueError(f"bone {b} comes before its parent {p}")
            pr, pp = ref[p]["rot"], ref[p]["pos"]
            rel_rot = qmul(qinv(pr), t["rot"])
            rel_pos = qrot(qinv(pr), tuple(a - c for a, c in zip(t["pos"], pp)))
            rot = qmul(out[p]["rot"], rel_rot)
            pos = tuple(a + c for a, c in zip(out[p]["pos"], qrot(out[p]["rot"], rel_pos)))
        if b in local:
            rot = qmul(rot, local[b])
        out[b] = {"rot": rot, "pos": pos}
    return out


def expand_pose(pose, recipe):
    """A pose's bone entries: its own ``bones``, or a ``curl`` {side l|r, fraction} expanded over the recipe's fingers,
    01/02/03 at fraction x the recipe's degrees, all about the recipe's axis with {s} the side."""
    if "curl" not in pose:
        return list(pose.get("bones", []))
    side, frac = pose["curl"].get("side"), pose["curl"].get("fraction")
    if side not in ("l", "r") or not (isinstance(frac, (int, float)) and math.isfinite(frac)):
        raise ValueError("a curl needs side l|r and a finite fraction")
    c = recipe["curl"]
    axis = json.loads(json.dumps(c["axis"]).replace("{s}", side))
    return [{"bone": f"{f}_{k}_{side}", "axis": axis, "deg": frac * c["deg"][k]} for f in c["fingers"] for k in ("01", "02", "03")]


def check_expect(expect, rest, posed, frame, scale_to_cm=1.0):
    """(ok, measured cm) for {'joint', 'along': <axis>, 'min_cm'} (the joint's displacement along the axis) or {'joint',
    'closer_to': <joint>, 'min_cm'} (how much nearer it came), measured on posed joint POSITIONS. ``scale_to_cm`` turns the
    joints' units into centimetres (100 for metres): the recipes state their minimums in cm."""
    j = expect.get("joint")
    if j not in rest or j not in posed:
        raise ValueError(f"the expectation names joint {j!r}, which the pose does not have")
    if "along" in expect:
        axis = resolve_axis(expect["along"], rest, frame)
        got = sum((b - a) * x for a, b, x in zip(rest[j], posed[j], axis))
    elif "closer_to" in expect:
        k = expect["closer_to"]
        got = math.dist(rest[j], rest[k]) - math.dist(posed[j], posed[k])
    else:
        raise ValueError(f"an expectation needs along or closer_to, has {sorted(expect)}")
    got = float(got) * float(scale_to_cm)
    return bool(got >= expect.get("min_cm", 0.0)), got


def segment_box_overlap(a, b, lo, hi):
    """Whether the segment a-b meets the axis-aligned box [lo, hi] anywhere along its length (slab test)."""
    t0, t1 = 0.0, 1.0
    for k in range(3):
        d = b[k] - a[k]
        if abs(d) < 1e-12:
            if a[k] < lo[k] or a[k] > hi[k]:
                return False
            continue
        u, v = (lo[k] - a[k]) / d, (hi[k] - a[k]) / d
        if u > v:
            u, v = v, u
        t0, t1 = max(t0, u), min(t1, v)
        if t0 > t1:
            return False
    return True


def control_shift(pairs, depth):
    """The positive control's shift vector from (piece vertex, its nearest skin point) pairs: along the CLOSEST pair, as
    far as that skin point plus min(depth, half the piece's extent along the push) - a thin piece straddles the skin
    instead of sinking through it (a buried piece crosses nothing)."""
    if not pairs:
        raise ValueError("no piece vertices to push")
    v, s = min(pairs, key=lambda q: math.dist(q[0], q[1]))
    d = tuple(b - a for a, b in zip(v, s))
    L = math.sqrt(sum(x * x for x in d))
    if L <= 1e-12:
        raise ValueError("a piece vertex lies on the skin: no direction to push it")
    u = tuple(x / L for x in d)
    along = [sum(a * b for a, b in zip(q[0], u)) for q in pairs]
    return tuple(x * (L + min(depth, (max(along) - min(along)) / 2)) for x in u)
