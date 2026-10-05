# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_texel_density: set and equalise texel density per island, then repack, and report the density actually achieved (specs/resources/uv_texel_density.md).

The scale rule is TexTools-Blender's (franMarz, GPL-3.0-or-later; op_texel_density_set.py: scale about the island's UV centroid by target / density), reimplemented over bmesh and
numpy with no ``bpy.ops.uv`` selection state, so it runs headless and from the agent. Density of an island = texture_size x sqrt(sum UV area / sum 3D area), area-weighted. The
repack is ours (rows of islands, no rotation, one margin) followed by ONE uniform scale that fits the layout into 0..1 but never enlarges it, so the ratios between islands
(density_i / density_j = weight_i / weight_j) survive and the achieved absolute density is whatever fits: ``shortfall`` = achieved / requested says so honestly. The source
object keeps its UVs; the result is a NEW object ``<object>_td``."""

import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np

from . import common as C
from . import uv_islands as UI

MAX_ISLANDS = 20000


def _is_pow2(n: int) -> bool:
    return 256 <= n <= 16384 and (n & (n - 1)) == 0


def _textured(ob) -> bool:
    for slot in ob.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image and node.image.source != "GENERATED" and node.outputs["Color"].links:
                return True
    return False


def _island_data(bm, uvl):
    """(face -> island id, per island: faces list, UV area, 3D area, UV centroid)."""
    ids = UI.island_ids(bm, uvl)
    n = int(ids.max() + 1) if len(ids) else 0
    au, a3 = np.zeros(n), np.zeros(n)
    cx, cy, cw = np.zeros(n), np.zeros(n), np.zeros(n)
    for fc in bm.faces:
        i = ids[fc.index]
        loops = fc.loops
        uvs = np.array([l[uvl].uv[:] for l in loops])
        x, y = uvs[:, 0], uvs[:, 1]
        au[i] += 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        a3[i] += fc.calc_area()
        cx[i] += x.sum()
        cy[i] += y.sum()
        cw[i] += len(loops)
    return ids, au, a3, np.stack([cx / np.maximum(cw, 1), cy / np.maximum(cw, 1)], 1)


def _weights(ob, bm, ids, weights) -> np.ndarray:
    w = np.ones(int(ids.max() + 1))
    if not weights:
        return w
    mats = [s.material.name if s.material else "" for s in ob.material_slots]
    groups = {g.name: g.index for g in ob.vertex_groups}
    dl = bm.verts.layers.deform.active
    for key, factor in weights.items():
        if not 0.1 <= float(factor) <= 4:
            raise C.FeatureError(f"weight {factor} for {key!r} is outside 0.1..4")
        name = key.split(":", 1)[1] if ":" in key else key
        hit = np.zeros(len(w))
        tot = np.zeros(len(w))
        for fc in bm.faces:
            i = ids[fc.index]
            tot[i] += 1
            if key.startswith("island:") and name.isdigit():
                hit[i] += 1 if int(name) == i else 0
            elif name in mats and fc.material_index < len(mats) and mats[fc.material_index] == name:
                hit[i] += 1
            elif name in groups and dl is not None and all(groups[name] in v[dl] and v[dl][groups[name]] > 0.5 for v in fc.verts):
                hit[i] += 1
        if not (name in mats or name in groups or key.startswith("island:")):
            raise C.FeatureError(f"weights key {key!r} is not a material, a vertex group or island:<index>")
        w[hit / np.maximum(tot, 1) >= 0.5] = float(factor)
    return w


def _stats(d, w, texture_size, uvmin, uvmax):
    norm = d / w
    mean = float(d.mean()) if len(d) else 0.0
    return {"islands": int(len(d)), "density_px_per_m_mean": round(mean, 2), "density_cv": round(float(norm.std() / norm.mean()), 4) if len(d) and norm.mean() > 0 else 0.0,
            "uv_min": [round(float(uvmin[0]), 4), round(float(uvmin[1]), 4)], "uv_max": [round(float(uvmax[0]), 4), round(float(uvmax[1]), 4)]}


def _read(ob, size, weights):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    uvl = bm.loops.layers.uv.active
    ids, au, a3, cen = _island_data(bm, uvl)
    d = size * np.sqrt(np.where(a3 > 1e-12, au / np.maximum(a3, 1e-12), 0.0))
    w = _weights(ob, bm, ids, weights)
    return bm, uvl, ids, d, w, cen


def _pack(bm, uvl, ids, margin):
    """Rows of islands, upright, then one uniform scale that fits the layout into 0..1 (never enlarged). Returns the scale applied."""
    n = int(ids.max() + 1)
    lo, hi = np.full((n, 2), np.inf), np.full((n, 2), -np.inf)
    for fc in bm.faces:
        i = ids[fc.index]
        for l in fc.loops:
            u = np.array(l[uvl].uv[:])
            lo[i], hi[i] = np.minimum(lo[i], u), np.maximum(hi[i], u)
    size = hi - lo
    total = float((size[:, 0] * size[:, 1]).sum())
    row_w = max(math.sqrt(total / 0.75), float(size[:, 0].max()))
    order = np.argsort(-size[:, 1])
    pos = np.zeros((n, 2))
    x = y = row_h = 0.0
    for i in order:
        if x > 0 and x + size[i, 0] > row_w:
            x, y, row_h = 0.0, y + row_h + margin, 0.0
        pos[i] = (x, y)
        x += size[i, 0] + margin
        row_h = max(row_h, size[i, 1])
    layout_w = float(max(pos[i, 0] + size[i, 0] for i in range(n)))
    layout_h = float(y + row_h)
    f = min(1.0, (1 - 2 * margin) / layout_w, (1 - 2 * margin) / layout_h)
    for fc in bm.faces:
        i = ids[fc.index]
        for l in fc.loops:
            u = np.array(l[uvl].uv[:])
            l[uvl].uv = ((u - lo[i]) + pos[i]) * f + margin
    return f


def run(object, texture_size=2048, target="auto", weights=None, mode="island", repack=True, margin=0.005, name="", discard_texture=False, root=""):
    ob = C.need_object(object)
    texture_size = int(texture_size)
    if not _is_pow2(texture_size):
        raise C.FeatureError(f"texture_size {texture_size} is not a power of two (256..16384: 2048, 4096)")
    if not ob.data.uv_layers:
        raise C.FeatureError(f"no UV layer on {ob.name}: run lampway_uv_unwrap first")
    if _textured(ob) and not discard_texture:
        raise C.FeatureError(f"{ob.name} is textured; a UV change discards the texture. Run this on the pre-texture copy, or pass discard_texture=true")
    if mode not in ("island", "all"):
        raise C.FeatureError("mode is island | all")
    bm, uvl, ids, d, w, cen = _read(ob, texture_size, weights)
    n = len(d)
    if n == 0 or not (d > 0).any():
        raise C.FeatureError(f"{ob.name} has no UV area to scale")
    if n > MAX_ISLANDS:
        raise C.FeatureError(f"island count {n} > {MAX_ISLANDS}: split the mesh (lampway_segment_mesh) first")
    before = _stats(d, w, texture_size, *_bounds(bm, uvl))
    before["off_density_2x"] = UI.measure_object(ob, 512).get("off_density_2x")
    if target == "auto":
        goal = float(d[d > 0].mean())
    else:
        m = str(target).replace("px/cm", "").strip()
        goal = float(m) * (100.0 if "px/cm" in str(target) else 1.0)
    if goal <= 0:
        raise C.FeatureError("target must be a positive px/metre (or 'N px/cm', or 'auto')")
    scale = np.where(d > 0, goal * w / np.where(d > 0, d, 1.0), 1.0) if mode == "island" else np.full(n, goal / float(d[d > 0].mean()))
    for fc in bm.faces:
        i = ids[fc.index]
        for l in fc.loops:
            u = np.array(l[uvl].uv[:])
            l[uvl].uv = cen[i] + (u - cen[i]) * scale[i]
    fit = _pack(bm, uvl, ids, float(margin)) if repack else 1.0
    new = C.duplicate(ob, "_td")
    if name:
        new.name = name
        new.data.name = name
    me = new.data
    bm.transform(ob.matrix_world.inverted())
    bm.to_mesh(me)
    ids2 = ids
    d_after = d * scale * fit
    achieved = float((d_after[d > 0]).mean())
    after = _stats(d_after, w, texture_size, *_bounds(bm, uvl))
    bm.free()
    m = UI.measure_object(new, 512)
    after.update(coverage=m["utilization"], overlap_fraction=m["overlap"], off_density_2x=m["off_density_2x"])
    out = {"object": new.name, "source": ob.name, "before": before, "after": after, "requested_target": round(goal, 2), "achieved_target": round(achieved, 2),
           "shortfall": round(min(1.0, achieved / goal), 4), "islands_scaled": [{"island": int(i), "weight": float(w[i]), "scale": round(float(scale[i] * fit), 4),
                                                                                "density_before": round(float(d[i]), 2), "density_after": round(float(d_after[i]), 2)} for i in range(n)]}
    if root:
        p = Path(root) / "texel_density.json"
        p.write_text(json.dumps(out, indent=1))
    return out


def _bounds(bm, uvl):
    pts = np.array([l[uvl].uv[:] for fc in bm.faces for l in fc.loops])
    return pts.min(axis=0), pts.max(axis=0)
