# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""segment_mesh's labels mode (specs/mixar_docs/segment_mesh.md): part names on UV islands as vertex groups ``<object>_<label>``, the shape the Client's Mesh
Segment applies from a ``mesh_segment`` job's ``result.island_labels``. The island enumeration IS the Client's (``mesh_segment.core.mesh_labeler.get_uv_islands``,
called, not copied), so an island index means one thing on both sides of the wire, and the groups are written by the Client's own ``apply_labels_to_mesh``.

mode map     ``island_labels`` {"<island>": "<label>"} given (checked against the recipe's part names when a recipe is given)
mode recipe  each island takes the recipe part that owns the majority of its faces in ``owner`` (a .npy, one part index per polygon; default the mesh's int face
             attribute ``part``); an island whose majority share is under ``min_share`` (0.6) or whose owner is -1 is UNLABELLED and named, never guessed
Free text (Mixar's ``description``) is refused: the labels are the recipe's vocabulary. A label set that leaves more than ``max_unlabeled`` (0.3) of the faces
unlabelled is refused before anything is written. Nothing is split; the object keeps its geometry."""

import json
from pathlib import Path

import numpy as np

from . import common as C

MODES = ("map", "recipe")


def _recipe_parts(path) -> list:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"recipe {path} not found")
    rec = json.loads(p.read_text(encoding="utf-8"))
    parts = rec.get("parts") if isinstance(rec, dict) else None
    if not parts:
        raise C.FeatureError(f"recipe {p.name} has no 'parts'")
    return list(parts)


def _owner(ob, owner_path):
    n = len(ob.data.polygons)
    if owner_path:
        arr = np.load(owner_path)
    else:
        attr = ob.data.attributes.get("part")
        if attr is None or attr.domain != "FACE":
            raise C.FeatureError(f"mode recipe needs `owner` (a .npy of one part index per polygon) or an int face attribute 'part' on {ob.name}")
        arr = np.empty(n, dtype=np.int64)
        attr.data.foreach_get("value", arr)
    arr = np.asarray(arr).reshape(-1)
    if len(arr) != n:
        raise C.FeatureError(f"the owner map has {len(arr)} entries; {ob.name} has {n} polygons (one part index per polygon)")
    return arr.astype(np.int64)


def _island_faces(ob, islands_verts):
    """island -> polygon indices (a polygon belongs to the island holding all its vertices; the Client's enumeration is per face, its output per vertex)."""
    v2i = {}
    for i, vs in islands_verts.items():
        for v in vs:
            v2i.setdefault(v, set()).add(i)
    out = {i: [] for i in islands_verts}
    for p in ob.data.polygons:
        common = set.intersection(*(v2i.get(v, set()) for v in p.vertices)) if len(p.vertices) else set()
        if common:
            out[min(common)].append(p.index)
    return out


def label(object, labels, recipe_path="", owner_path=""):
    from mixar.modules.mesh_segment.core.mesh_labeler import apply_labels_to_mesh, get_uv_islands
    ob = C.need_object(object)
    spec = dict(labels or {})
    mode = spec.get("mode", "map")
    if mode not in MODES:
        raise C.FeatureError("labels.mode is map | recipe: the labels are the recipe's part names (free-text description is not built: name the parts)")
    if not ob.data.uv_layers or ob.data.uv_layers.active is None:
        raise C.FeatureError(f"segmentation labels key off UV islands: the mesh {ob.name} has no UV map (unwrap first: lampway_uv_unwrap)")
    islands = get_uv_islands(ob)
    vocab = _recipe_parts(recipe_path)
    faces = _island_faces(ob, islands)
    total = max(1, len(ob.data.polygons))
    evidence, out = {}, {}
    if mode == "map":
        given = {str(k): str(v) for k, v in (spec.get("island_labels") or {}).items()}
        if not given:
            raise C.FeatureError("mode map needs island_labels {\"<island>\": \"<label>\"}; segment_mesh(labels={mode: recipe, ...}) derives them from an owner map")
        bad_ids = [k for k in given if not k.isdigit() or int(k) not in islands]
        if bad_ids:
            raise C.FeatureError(f"no island {bad_ids[0]} on {ob.name}: the islands are 0..{len(islands) - 1}")
        if vocab:
            off = sorted({v for v in given.values() if v not in vocab})
            if off:
                raise C.FeatureError(f"label {off[0]!r} is not a part of the recipe ({', '.join(vocab)}): use the recipe's names")
        out = given
        evidence = {k: {"how": "given"} for k in given}
    else:
        if not vocab:
            raise C.FeatureError("mode recipe needs `recipe` (the parts json) for the part names")
        own = _owner(ob, owner_path)
        share_min = float(spec.get("min_share", 0.6))
        for i in sorted(islands):
            fs = faces[i]
            vals = own[fs] if fs else np.array([], dtype=np.int64)
            if not len(vals):
                evidence[str(i)] = {"how": "no faces"}
                continue
            u, c = np.unique(vals, return_counts=True)
            k = int(np.argmax(c))
            part, share = int(u[k]), float(c[k]) / len(vals)
            ev = {"how": "owner vote", "part_index": part, "share": round(share, 4), "faces": len(vals)}
            if part < 0 or part >= len(vocab):
                ev["unlabeled_because"] = "the owner map gives no part"
            elif share < share_min:
                ev["unlabeled_because"] = f"majority share {share:.2f} < min_share {share_min}"
            else:
                out[str(i)] = vocab[part]
            evidence[str(i)] = ev
    unlabeled = sorted(int(i) for i in islands if str(i) not in out)
    unl_faces = sum(len(faces[i]) for i in unlabeled)
    max_unl = float(spec.get("max_unlabeled", 0.3))
    if unl_faces / total > max_unl:
        raise C.FeatureError(f"{unl_faces} of {total} faces would stay unlabelled (> {max_unl:.0%}): nothing was applied; islands {unlabeled} need a label "
                             "(fix the owner map or give them in mode map)")
    created, names = apply_labels_to_mesh(ob, out)
    return {"object": ob.name, "mode": mode, "island_labels": out, "unlabeled_islands": unlabeled, "unlabeled_face_fraction": round(unl_faces / total, 4),
            "groups": sorted(f"{ob.name}_{v}" for v in set(out.values())), "groups_created": created, "evidence": evidence,
            "islands": {str(i): {"verts": sorted(vs), "faces": faces[i]} for i, vs in sorted(islands.items())}, "enumeration": "mesh_labeler.get_uv_islands (the Client's)"}
