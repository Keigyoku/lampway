# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon20 B5 / canon07 B7, reimplemented from Titan proc_body's body contract.

Elliptical quad limbs carry analytical weights. Each child owns the joint
width on both sides; a branch has no uniquely named tail weight partner.
"""

import math


def joint_blends(bones, frac=0.25):
    if not 0 < frac <= 0.5:
        raise ValueError("a joint blend fraction must be in (0, 0.5]")
    widths = {}
    for name, bone in bones.items():
        parent = bone["parent"]
        if parent is not None:
            if parent not in bones:
                raise ValueError(f"bone {name}: parent {parent} is not in the body")
            widths[name] = frac * min(bone["length"], bones[parent]["length"])
    return widths


def body(bones, stations=6, sides=12, blend=0):
    if stations < 2 or sides < 3:
        raise ValueError("a limb needs at least two stations and three sides")
    children = {n: [] for n in bones}
    widths = {n: b.get("blend", blend) for n, b in bones.items()}
    for n, b in bones.items():
        parent = b["parent"]
        if parent is not None:
            if parent not in bones:
                raise ValueError(f"bone {n}: parent {parent} is not in the body")
            children[parent].append(n)
    for n, b in bones.items():
        if not math.isfinite(b["length"]) or b["length"] <= 0:
            raise ValueError(f"bone {n}: positive finite length required")
        parent = b["parent"]
        if not math.isfinite(widths[n]) or widths[n] < 0:
            raise ValueError(f"bone {n}: nonnegative finite blend required")
        if parent is not None and (widths[n] > b["length"] / 2 or
                                   (len(children[parent]) == 1 and widths[n] > bones[parent]["length"] / 2)):
            raise ValueError(f"joint {parent}-{n}: blend longer than half a bone")
    out = {k: [] for k in ("verts", "faces", "uvs", "weights", "bone", "station")}
    for name in sorted(bones):
        b = bones[name]
        base = len(out["verts"])
        for station in range(stations):
            t = station / (stations - 1)
            d, e = t * b["length"], (1 - t) * b["length"]
            partner, distance, width = None, 0, 0
            if b["parent"] is not None and d < widths[name]:
                partner, distance, width = b["parent"], d, widths[name]
            elif len(children[name]) == 1 and e < widths[children[name][0]]:
                partner, distance, width = children[name][0], e, widths[children[name][0]]
            weights = {name: 1.0}
            if partner is not None:
                own = 0.5 + distance / (2 * width)
                weights = {name: own, partner: 1 - own}
            rx, rz = (a + (z - a) * t for a, z in zip(b["head"], b["tail"]))
            for side in range(sides):
                angle = side * math.tau / sides
                local = (rx * math.cos(angle), d, rz * math.sin(angle))
                out["verts"].append(tuple(sum(b["frame"][i][j] * local[j] for j in range(3)) + b["frame"][i][3] for i in range(3)))
                out["weights"].append(dict(weights))
                out["uvs"].append((side / sides, t))
                out["bone"].append(name)
                out["station"].append(t)
        for station in range(stations - 1):
            for side in range(sides):
                i, j = base + station * sides + side, base + station * sides + (side + 1) % sides
                out["faces"].append((i, j, j + sides, i + sides))
    return out
