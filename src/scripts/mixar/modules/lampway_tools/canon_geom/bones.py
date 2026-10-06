# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 01 C: bone directions and the finger axes (ported from Titan tools/proc_body.py, maths unchanged).

A Blender-imported UE bone's head->tail is NOT its direction: the glTF import lays it about 90 deg off its limb (measured
2026-09-29 on two rigs). A bone runs from its head to the head of its continuation child (``chain_ends``); a named
continuation picks among several children; a leaf continues its parent's line by ``leaf`` of their distance. Fingers flex
about the knuckle line index_01 -> pinky_01 (``finger_axis``), never about bone x palm."""

import math

import numpy as np

from .axes import cross, unit

MAIN_CHILD = {"pelvis": "spine_01", "spine_05": "neck_01", "hand_l": "middle_01_l", "hand_r": "middle_01_r"}
LEAF = 0.8

# The continuation of every UE limb bone that carries twist / corrective / helper children beside its next joint (UE5
# Manny and MetaHuman bone NAMES), plus the spine top of Lampway's own auto-rig (features/rig._bone_table: spine_03 ->
# neck_01 beside both clavicles). MAIN_CHILD (the canon's table) wins where both name a bone.
CONTINUATION = dict({f"{a}_{s}": f"{b}_{s}" for s in ("l", "r") for a, b in (("clavicle", "upperarm"), ("upperarm", "lowerarm"),
                                                                              ("lowerarm", "hand"), ("thigh", "calf"), ("calf", "foot"),
                                                                              ("foot", "ball"))},
                    spine_03="neck_01", neck_01="neck_02", neck_02="head", **MAIN_CHILD)


def _descends(bone, ancestor, parents):
    seen = set()
    while bone is not None and bone not in seen:
        seen.add(bone)
        bone = parents.get(bone)
        if bone == ancestor:
            return True
    return False


def chain_ends(heads, parents, leaf=LEAF, main_child=None):
    """{bone: end point}: the child's head (the named continuation where there are several - a direct child, or a deeper
    descendant such as MetaHuman's middle_01 under middle_metacarpal), or - a last bone - the parent's line continued by
    ``leaf``. Several children and no named continuation is refused."""
    main = MAIN_CHILD if main_child is None else main_child
    kids = {}
    for b, p in parents.items():
        if p is not None and b in heads:
            kids.setdefault(p, []).append(b)
    out = {}
    for b, h in heads.items():
        k = kids.get(b, [])
        if len(k) == 1:
            out[b] = tuple(heads[k[0]])
        elif k:
            m = main.get(b)
            if m not in heads or not _descends(m, b, parents):
                raise ValueError(f"bone {b!r} has children {', '.join(sorted(k))} and no named continuation")
            out[b] = tuple(heads[m])
        else:
            p = parents.get(b)
            if p is None or p not in heads:
                raise ValueError(f"bone {b!r} has neither a child nor a parent to continue")
            out[b] = tuple(x + leaf * (x - y) for x, y in zip(h, heads[p]))
    return out


def bone_segments(heads, parents, leaf=LEAF, main_child=None):
    """{bone: (head (3,), end (3,))} as numpy arrays: the segment a bone covers for distance-based weighting."""
    ends = chain_ends(heads, parents, leaf, main_child)
    return {b: (np.asarray(heads[b], float), np.asarray(ends[b], float)) for b in heads}


def flex_axis(bone_dir, hand, index, middle, pinky, side):
    """The axis a finger bone closes about: across the finger and in the palm's plane, signed so a positive turn takes the
    tip towards the palm. The palm faces along (middle - hand) x (pinky - index) on the right hand, the reverse on the left."""
    if side not in ("l", "r"):
        raise ValueError(f"side must be l or r, not {side!r}")
    d = tuple(m - h for m, h in zip(middle, hand))
    a = tuple(p - i for p, i in zip(pinky, index))
    palm = cross(d, a) if side == "r" else cross(a, d)
    return unit(cross(bone_dir, palm), "flex axis")


def finger_axis(hand, index, middle, pinky, side):
    """The knuckle-line axis the four fingers flex about: ``flex_axis`` of the hand's own direction (wrist -> middle
    knuckle), fixed by the hand so it does not flip as a finger curls past the palm's normal."""
    return flex_axis(tuple(m - h for m, h in zip(middle, hand)), hand, index, middle, pinky, side)


def curl_delta(parent_dir, bone_dir, axis, target_deg):
    """The turn (degrees, about ``axis``) that brings a finger joint TO ``target_deg`` of curl: its current curl is the
    signed angle from the bone behind it to the bone, both seen across the axis."""
    a = unit(axis, "axis")

    def across(v):
        d = sum(x * y for x, y in zip(v, a))
        return [x - d * y for x, y in zip(v, a)]
    p, b = across(parent_dir), across(bone_dir)
    cur = math.degrees(math.atan2(sum(x * y for x, y in zip(a, cross(p, b))), sum(x * y for x, y in zip(p, b))))
    return target_deg - cur
