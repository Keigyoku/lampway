# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_check (specs/mixar_docs/uv_check.md): read-only UV measurements per island, and two small reversible edits on the object's ACTIVE UV layer.

measure            per island: faces, UV and 3D area, texel density sqrt(UV area / 3D area) x texture_size in px/m, UV bbox and the UDIM tiles it touches; the tiles used and
                   the islands that cross a tile border (a UDIM finding: a bake reads one tile per island)
select_by_density  selects the faces of islands whose density is off target by more than ``tolerance`` (a fraction)
overlaps           rasterised per tile at ``res``: the overlapping fraction of covered texels and the overlapping island pairs, split into ``stacked`` (the two islands share
                   their UV outline: deliberate, e.g. mirrored twins) and ``accidental``
space_usage        coverage of tile 1001 (and of every used tile) and the count of empty cells on a 16 x 16 grid
orientation        ``flipped``: islands whose UV winding disagrees with the majority; ``mirrored``: island pairs whose 3D geometry mirrors across ``mirror_axis`` (symmetric Chamfer
                   <= match_tolerance metres): the stack candidates
udim_move          moves ``islands`` by whole tiles to ``tile_to`` (1001..1099) [UNVERIFIED limit]
stack              puts each mirrored twin on its partner's UVs vertex by vertex (uv_layout's stack_mirrored); a named pair that is not mirrored is refused
The edits are dry runs unless dry_run=false, change only the active UV layer, refuse a textured object (texturing comes last; discard_texture overrides) and push one
undo step named lampway_uv_check. Island ids are uv_islands' (first face order), the same ids uv_score and uv_layout use."""

import bmesh
import bpy
import numpy as np

from . import common as C
from . import uv_islands as UI
from .uv_layout import _chamfer, _signed_area, _verts, stack_mirrored
from .uv_rectify import _faces_by_island
from .uv_texel import _textured

ACTIONS = ("measure", "select_by_density", "overlaps", "space_usage", "orientation", "udim_move", "stack")
AXES = {"x": 0, "y": 1, "z": 2}
MAX_TRIS = 1_000_000
GRID = 16


def tile_of(u: float, v: float) -> int:
    return 1001 + int(np.floor(u)) + 10 * int(np.floor(v))


def _tiles(lo, hi) -> list:
    u0, v0 = int(np.floor(lo[0] + 1e-9)), int(np.floor(lo[1] + 1e-9))
    u1, v1 = int(np.floor(hi[0] - 1e-9)), int(np.floor(hi[1] - 1e-9))
    return sorted(1001 + u + 10 * v for u in range(u0, max(u0, u1) + 1) for v in range(v0, max(v0, v1) + 1))


def _tris(faces, uvl, mw=None):
    tu, t3 = [], []
    for fc in faces:
        ls = list(fc.loops)
        for k in range(1, len(ls) - 1):
            tu.append([ls[0][uvl].uv[:], ls[k][uvl].uv[:], ls[k + 1][uvl].uv[:]])
            if mw is not None:
                t3.append([mw @ ls[0].vert.co, mw @ ls[k].vert.co, mw @ ls[k + 1].vert.co])
    return np.array(tu, dtype=np.float64).reshape(-1, 3, 2), np.array(t3, dtype=np.float64).reshape(-1, 3, 3)


def _island_rows(groups, uvl, mw, size):
    rows = []
    for i in sorted(groups):
        tu, t3 = _tris(groups[i], uvl, mw)
        au = float(np.abs((tu[:, 1, 0] - tu[:, 0, 0]) * (tu[:, 2, 1] - tu[:, 0, 1]) - (tu[:, 2, 0] - tu[:, 0, 0]) * (tu[:, 1, 1] - tu[:, 0, 1])).sum() / 2)
        a3 = float(np.linalg.norm(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]), axis=1).sum() / 2)
        p = tu.reshape(-1, 2)
        lo, hi = p.min(axis=0), p.max(axis=0)
        rows.append({"index": i, "faces": len(groups[i]), "area_uv": round(au, 8), "area_3d_m2": round(a3, 8),
                     "density_px_m": round(float(np.sqrt(au / a3)) * size, 3) if a3 > 0 else None,
                     "bbox": [round(float(x), 6) for x in (*lo, *hi)], "tiles": _tiles(lo, hi)})
    return rows


def _rasters(groups, uvl, ids, res):
    """{island: {tile: bool mask}} rasterised per tile the island touches."""
    out = {}
    for i in ids:
        tu, _ = _tris(groups[i], uvl)
        p = tu.reshape(-1, 2)
        masks = {}
        for t in _tiles(p.min(axis=0), p.max(axis=0)):
            du, dv = (t - 1001) % 10, (t - 1001) // 10
            masks[t] = UI._raster(tu - np.array([du, dv]), res) > 0
        out[i] = masks
    return out


def _same_outline(groups, uvl, a, b, tol=1e-4) -> bool:
    pa = np.array(sorted({tuple(round(c, 6) for c in l[uvl].uv) for fc in groups[a] for l in fc.loops}))
    pb = np.array(sorted({tuple(round(c, 6) for c in l[uvl].uv) for fc in groups[b] for l in fc.loops}))
    if len(pa) == 0 or len(pb) == 0:
        return False
    d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
    return float(max(d.min(axis=1).max(), d.min(axis=0).max())) <= tol


def _overlaps(groups, uvl, res):
    ids = sorted(groups)
    ras = _rasters(groups, uvl, ids, res)
    tiles = sorted({t for m in ras.values() for t in m})
    covered = overlapped = 0
    pairs = []
    for t in tiles:
        cnt = np.zeros((res, res), np.int32)
        for i in ids:
            if t in ras[i]:
                cnt += ras[i][t]
        covered += int((cnt > 0).sum())
        overlapped += int((cnt > 1).sum())
    for ai, a in enumerate(ids):
        for b in ids[ai + 1:]:
            if any(t in ras[b] and bool((ras[a][t] & ras[b][t]).any()) for t in ras[a]):
                pairs.append([a, b])
    stacked = [p for p in pairs if _same_outline(groups, uvl, *p)]
    return {"fraction": round(overlapped / max(covered, 1), 6), "pairs": pairs, "stacked": stacked, "accidental": [p for p in pairs if p not in stacked],
            "res": res}, ras


def _mirrored_pairs(groups, vco, axis, tol):
    data = {i: _verts(f, vco) for i, f in groups.items()}
    order = sorted(groups)
    cands = []
    for ai, a in enumerate(order):
        for b in order[ai + 1:]:
            if len(data[a][0]) != len(data[b][0]) or len(data[a][0]) > 2000:
                continue
            m = data[a][1].copy()
            m[:, axis] *= -1.0
            ch, _ = _chamfer(m, data[b][1])
            if ch <= tol:
                cands.append((ch, a, b))
    used, out = set(), []
    for ch, a, b in sorted(cands):
        if a in used or b in used:
            continue
        used.update((a, b))
        out.append((a, b, ch))
    return sorted(out)


def _pair_chamfer(groups, vco, axis, a, b) -> float:
    pa, pb = _verts(groups[a], vco)[1], _verts(groups[b], vco)[1]
    m = pa.copy()
    m[:, axis] *= -1.0
    return _chamfer(m, pb)[0]


def _undo():
    try:
        bpy.ops.ed.undo_push(message="lampway_uv_check")
    except RuntimeError:                              # no window context (headless): the change stands, there is no undo stack to push to
        pass


def run(object, action="measure", target_density_px_m=None, texture_size=2048, tolerance=0.15, tile_from=None, tile_to=None, islands=None, dry_run=True,
        mirror_axis="x", match_tolerance=0.003, res=512, discard_texture=False, limit=50, offset=0, full=False):
    ob = C.need_object(object)
    if action not in ACTIONS:
        raise C.FeatureError("action is " + " | ".join(ACTIONS))
    if ob.mode == "EDIT":
        raise C.FeatureError(f"{ob.name} is in Edit Mode: switch to Object Mode first (the UVs are read from the mesh data)")
    if not ob.data.uv_layers or ob.data.uv_layers.active is None:
        raise C.FeatureError(f"no UV layer on {ob.name}: unwrap first (lampway_uv_unwrap)")
    if mirror_axis not in AXES:
        raise C.FeatureError("mirror_axis is x | y | z")
    size = int(texture_size)
    if size <= 0:
        raise C.FeatureError("texture_size is a positive pixel count")
    res = int(res)
    if not 64 <= res <= 4096:
        raise C.FeatureError("res is 64..4096")
    if sum(max(0, len(p.vertices) - 2) for p in ob.data.polygons) > MAX_TRIS:
        raise C.FeatureError(f"{ob.name} has over {MAX_TRIS} triangles: too large to rasterise: decimate or check a copy")
    edit = action in ("udim_move", "stack")
    if edit and not dry_run and _textured(ob) and not discard_texture:
        raise C.FeatureError(f"{ob.name} is textured; a UV change discards the texture (texturing comes last). Edit the pre-texture copy, or pass discard_texture=true")
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        uvl = bm.loops.layers.uv.active
        mw = ob.matrix_world
        groups = _faces_by_island(bm, uvl)
        out = {"object": ob.name, "action": action, "uv_layer": ob.data.uv_layers.active.name, "island_count": len(groups)}
        if action == "measure":
            rows = _island_rows(groups, uvl, mw, size)
            lim, off = max(1, int(limit)), max(0, int(offset))       # audit F8: a page of islands; the tiles and density below cover every island
            out["islands"] = rows if full else rows[off:off + lim]
            out["next_offset"] = None if full or off + lim >= len(rows) else off + lim
            out["texture_size"] = size
            out["udim"] = {"tiles": sorted({t for r in rows for t in r["tiles"]}), "crossing": [r["index"] for r in rows if len(r["tiles"]) > 1]}
            d = np.array([r["density_px_m"] for r in rows if r["density_px_m"]], dtype=np.float64)
            out["density"] = {"mean": round(float(d.mean()), 3), "cv": round(float(d.std() / d.mean()), 4)} if len(d) else {}
            return out
        if action == "select_by_density":
            rows = _island_rows(groups, uvl, mw, size)
            target = target_density_px_m
            if target in (None, "auto"):
                target = float(np.mean([r["density_px_m"] for r in rows if r["density_px_m"]]))
            target, tol = float(target), float(tolerance)
            if target <= 0 or not 0 <= tol < 1:
                raise C.FeatureError("target_density_px_m is > 0 and tolerance is a fraction in [0, 1)")
            off = [r for r in rows if r["density_px_m"] is None or abs(r["density_px_m"] - target) > tol * target]
            faces = sorted(fc.index for r in off for fc in groups[r["index"]])
            fs = set(faces)
            for p in ob.data.polygons:
                p.select = p.index in fs
            out.update({"target_density_px_m": round(target, 3), "tolerance": tol, "islands": off, "selected": faces})
            return out
        if action == "overlaps":
            out["overlap"], _ = _overlaps(groups, uvl, res)
            return out
        if action == "space_usage":
            _, ras = _overlaps(groups, uvl, res)
            tiles = sorted({t for m in ras.values() for t in m} | {1001})
            per = {}
            free = 0
            for t in tiles:
                m = np.zeros((res, res), bool)
                for r in ras.values():
                    if t in r:
                        m |= r[t]
                per[str(t)] = round(float(m.mean()), 6)
                if t == 1001:
                    cell = res // GRID
                    free = int(sum(1 for y in range(GRID) for x in range(GRID) if not m[y * cell:(y + 1) * cell, x * cell:(x + 1) * cell].any()))
            out["usage"] = {"coverage": per["1001"], "tiles": per, "free_blocks": free, "grid": GRID}
            return out
        vco = {v.index: np.array(mw @ v.co) for v in bm.verts}
        axis = AXES[mirror_axis]
        tol = float(match_tolerance)
        if not 0.0005 <= tol <= 0.05:
            raise C.FeatureError("match_tolerance is 0.0005..0.05 metres")
        if action == "orientation":
            sg = {i: _signed_area(f, uvl) for i, f in groups.items()}
            maj = 1.0 if sum(sg.values()) >= 0 else -1.0
            out["orientation"] = {"flipped": sorted(i for i, s in sg.items() if s * maj < 0),
                                  "mirrored": [[a, b] for a, b, _ in _mirrored_pairs(groups, vco, axis, tol)], "mirror_axis": mirror_axis}
            return out
        if action == "udim_move":
            if tile_to is None:
                raise C.FeatureError("udim_move needs tile_to (and islands)")
            tt = int(tile_to)
            if not 1001 <= tt <= 1099:
                raise C.FeatureError("UDIM tiles run 1001..1099 in this build [UNVERIFIED limit]")
            ids = [int(i) for i in (islands or [])]
            bad = [i for i in ids if i not in groups]
            if not ids or bad:
                raise C.FeatureError(f"islands names the islands to move (ids 0..{len(groups) - 1}; measure lists them){': unknown ' + str(bad) if bad else ''}")
            moved = []
            for i in ids:
                p = np.array([l[uvl].uv[:] for fc in groups[i] for l in fc.loops])
                cur = tile_of(*(p.min(axis=0) + 1e-9))
                if tile_from is not None and cur != int(tile_from):
                    continue
                du = (tt - 1001) % 10 - (cur - 1001) % 10
                dv = (tt - 1001) // 10 - (cur - 1001) // 10
                moved.append({"island": i, "from": cur, "to": tt, "offset": [du, dv]})
                if not dry_run:
                    for fc in groups[i]:
                        for l in fc.loops:
                            l[uvl].uv = (l[uvl].uv[0] + du, l[uvl].uv[1] + dv)
            out.update({"moved": moved, "applied": not dry_run})
        else:                                                       # stack
            if islands:
                ids = [int(i) for i in islands]
                if len(ids) % 2 or any(i not in groups for i in ids):
                    raise C.FeatureError("islands for stack are pairs of island ids [a, b, c, d ...] (orientation lists the mirrored pairs)")
                for a, b in zip(ids[0::2], ids[1::2]):
                    ch = _pair_chamfer(groups, vco, axis, a, b) if len(groups[a]) == len(groups[b]) else float("inf")
                    if ch > tol:
                        raise C.FeatureError(f"islands {a} and {b} are not mirror twins across {mirror_axis} (Chamfer {ch:.4f} m > {tol}): stacking them would lay "
                                             "different surfaces on one texture; refused")
                sel = {i: groups[i] for i in ids}
            else:
                sel = groups
            if dry_run:
                pairs = [{"a": a, "b": b, "chamfer_m": round(ch, 6)} for a, b, ch in _mirrored_pairs(sel, vco, axis, tol)]
            else:
                pairs = stack_mirrored(sel, uvl, vco, axis, tol)
            out.update({"stacked": pairs, "applied": not dry_run})
        if not dry_run:
            bm.to_mesh(ob.data)
            ob.data.update()
            _undo()
        return out
    finally:
        bm.free()
