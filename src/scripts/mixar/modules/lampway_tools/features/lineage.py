# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_lineage: where a derivative came from, so a repaired mesh cannot silently become an unrelated one. ``record`` stores three hashes (geometry, UV,
material), the transformation and THREE identity anchors (landmarks that must not move) on the object (``lw_lineage``) and appends the same line to
``<root>/<piece>/lineage.jsonl``; ``verify`` measures each anchor's nearest-point distance to the derivative; ``show`` returns the chain. The tool proposes
no anchors: which landmarks matter is the captain's call."""

import json
import time
import uuid
from pathlib import Path

import numpy as np

from . import common as C
from . import workflows as W

ACTIONS = ("record", "verify", "show")


def _hashes(ob) -> dict:
    return {"geometry": W.mesh_hash(ob), "uv": W.uv_hash(ob), "material": W.material_hash(ob)}


def _local_bounds(ob):
    co = np.empty(len(ob.data.vertices) * 3, dtype=np.float64)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)


def _anchors(raw, src) -> list:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise C.FeatureError("a lineage needs three identity anchors: pick landmarks that must not move ([{name, point: [x, y, z]}] in object space)")
    lo, hi = _local_bounds(src)
    out = []
    for a in raw:
        pt = [float(x) for x in (a or {}).get("point") or []]
        if len(pt) != 3 or not str((a or {}).get("name") or "").strip():
            raise C.FeatureError("each anchor is {name, point: [x, y, z]}")
        if np.any(np.array(pt) < lo - 1e-9) or np.any(np.array(pt) > hi + 1e-9):
            raise C.FeatureError(f"anchor {a['name']!r} lies outside the source's bounding box: an identity anchor is a point ON the piece")
        out.append({"name": str(a["name"]), "point": pt})
    return out


def _file(root, piece) -> Path:
    return Path(root) / piece / "lineage.jsonl"


def _chain(root, piece, lineage) -> list:
    rows = {}
    p = _file(root, piece)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                rows[row["id"]] = row
            except (ValueError, KeyError):
                continue
    out, cur = [], lineage
    while cur is not None and cur["id"] not in {c["id"] for c in out}:
        out.append(rows.get(cur["id"], cur))
        cur = rows.get(cur.get("parent_id")) if cur.get("parent_id") else None
    return list(reversed(out))


def run(action, object, root, source="", transform="", anchors=None, changed_region=None, tolerance_m=0.01, parent="", piece=""):
    if action not in ACTIONS:
        raise C.FeatureError("action is record|verify|show")
    ob = C.need_object(object)
    piece = piece or ob.name
    if action == "record":
        src = C.need_object(source) if source else ob
        existing = json.loads(ob["lw_lineage"]) if ob.get("lw_lineage") else None
        if existing and existing["id"] != parent:
            raise C.FeatureError(f"already derived from {existing['id']}; pass parent={existing['id']} to chain")
        lineage = {"id": str(uuid.uuid4()), "parent_id": parent or None, "source_hash": _hashes(src), "hash": _hashes(ob), "transform": str(transform),
                   "anchors": _anchors(anchors, src), "changed_region": changed_region, "side": ob.get("lw_side", "unknown"),
                   "created_at": time.time(), "piece": piece}
        ob["lw_lineage"] = json.dumps(lineage)
        p = _file(root, piece)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(lineage) + "\n")
        return {"object": ob.name, "lineage": lineage}
    if not ob.get("lw_lineage"):
        raise C.FeatureError("no lineage: call record on the approved source (three anchors) first")
    lineage = json.loads(ob["lw_lineage"])
    if action == "show":
        return {"object": ob.name, "lineage": lineage, "chain": _chain(root, lineage.get("piece") or piece, lineage)}
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([v.co.copy() for v in ob.data.vertices], [tuple(p.vertices) for p in ob.data.polygons])
    tol = float(tolerance_m)
    if not 0.0001 <= tol <= 0.05:
        raise C.FeatureError("tolerance_m is 0.0001 to 0.05 metres")
    moved = []
    for a in lineage["anchors"]:
        _loc, _n, _i, dist = tree.find_nearest(Vector(a["point"]))
        if dist > tol:
            moved.append({"name": a["name"], "distance_m": round(float(dist), 6)})
    return {"object": ob.name, "lineage": lineage, "verify": {"anchors_moved": moved, "pass": not moved, "tolerance_m": tol, "now": _hashes(ob)}}
