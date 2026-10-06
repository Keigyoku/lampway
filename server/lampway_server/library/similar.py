"""Find assets like a selection (specs/asset_library/asset_similar.md): shape, look and name axes, deterministic and local.

Shape is the D2/A3/D1 descriptor (scale removed on purpose; ``dim_*`` stays a filter). Look is the colour histogram plus the difference hash (or a bundled local image model when
one is built). Name is the text index. ``score`` is the weighted sum of the axes that exist for BOTH probe and candidate, with the weights renormalised over those axes, so a
missing axis is never a penalty. A probe that has no descriptor yet gets one computed on demand; an image-file probe is read, never ingested."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from . import embed as EM
from . import query as Q
from . import spaces as SP
from .store import AssetLibrary, LibraryError

DEFAULT_WEIGHTS = {"shape": 0.5, "look": 0.3, "name": 0.2}
AXES = ("shape", "look", "name")


def _shape_sims(mat: np.ndarray, q: np.ndarray) -> np.ndarray:
    cuts = (0, SP.D2_BINS, SP.D2_BINS + SP.A3_BINS, SP.D2_BINS + SP.A3_BINS + SP.D1_BINS)
    d = np.mean([np.abs(mat[:, s:e] - q[s:e]).sum(1) for s, e in zip(cuts, cuts[1:])], axis=0)
    return 1 - d / 2


def _cos(mat, q):
    n = float(np.linalg.norm(q))
    return np.clip(mat @ (q / n if n else q), 0, 1)


def _ham(mat, q):
    return 1 - np.count_nonzero((mat > 0) != (q > 0), axis=1) / mat.shape[1]


def similar(lib: AssetLibrary, selection: dict, axes=AXES, weights: Optional[dict] = None, kinds=None, k: int = 12, min_score: Optional[float] = None, exclude_self: bool = True) -> dict:
    t0 = time.time()
    axes = list(axes)
    bad = [a for a in axes if a not in AXES]
    if bad:
        raise LibraryError(f"unknown axis {bad}; axes: {list(AXES)} (motion is not built)")
    sel_ids = list(selection.get("asset_ids") or [])
    if not (sel_ids or selection.get("image_path") or selection.get("text")):
        raise LibraryError("selection is empty")
    k = max(1, min(int(k), 100))
    svc = EM.Embed(lib)
    kinds_sel = [lib.get(a)["kind"] for a in sel_ids]
    if axes == ["shape"] and any(kd != "mesh" for kd in kinds_sel):
        raise LibraryError("shape applies to meshes only")
    sims: dict = {}                   # axis -> {asset_id: similarity 0..1}
    coherence = 1.0
    probe_kind = "mesh" if kinds_sel and all(kd == "mesh" for kd in kinds_sel) else (kinds_sel[0] if len(set(kinds_sel)) == 1 else "mixed") if kinds_sel else ("image" if selection.get("image_path") else "text")
    have = set(lib.embedding_spaces())

    def probe_vecs(space):
        out = []
        for a in sel_ids:
            vid = lib.version_of(a)
            row = lib._reader().execute("SELECT vec FROM embedding WHERE version_id=? AND space=? AND sub_key=''", (vid, space)).fetchone()
            if row is None:
                try:
                    svc.ensure(a, space)
                except LibraryError:
                    continue
                row = lib._reader().execute("SELECT vec FROM embedding WHERE version_id=? AND space=? AND sub_key=''", (vid, space)).fetchone()
            out.append(np.frombuffer(row[0], "<f4"))
        return out

    if "shape" in axes and any(kd == "mesh" for kd in kinds_sel):
        pv = probe_vecs("shape_d2")
        if pv:
            ids, mat = lib.load_space("shape_d2")
            q = np.mean(pv, axis=0)
            sims["shape"] = dict(zip(ids, _shape_sims(mat, q))) if ids else {}
            if len(pv) > 1:
                coherence = float(np.mean([_shape_sims(np.stack([b]), a)[0] for i, a in enumerate(pv) for b in pv[i + 1:]]))
    if "look" in axes:
        look: list = []
        for space, fn in (("image_hist", _cos), ("image_dhash", _ham)):
            if sel_ids:
                pv = [v for v in probe_vecs(space)] if any(kd in EM.IMAGE_KINDS for kd in kinds_sel) else []
            elif selection.get("image_path"):
                pv = [(SP.image_hist if space == "image_hist" else SP.image_dhash)(selection["image_path"])]
            else:
                pv = []
            if pv:
                ids, mat = lib.load_space(space)
                if ids:
                    look.append(dict(zip(ids, fn(mat, np.mean(pv, axis=0)))))
        if look:                                                # each candidate on the look spaces it HAS: a space nobody indexed is never a veto
            every = set().union(*[set(d) for d in look])
            sims["look"] = {i: float(np.mean([d[i] for d in look if i in d])) for i in every}
    if "name" in axes:
        text = selection.get("text") or " ".join(lib.get(a)["name"] for a in sel_ids)
        if text.strip():
            res = Q.query(lib, {"text": text, "limit": 200})
            sims["name"] = {it["id"]: it["score"] for it in res["items"]}
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    cand = set().union(*[set(d) for d in sims.values()]) if sims else set()
    if exclude_self:
        cand -= set(sel_ids)
    meta = {r["id"]: r for r in lib._reader().execute("SELECT id,name,kind FROM asset WHERE status='active'").fetchall()}
    items = []
    for cid in cand:
        if cid not in meta or (kinds and meta[cid]["kind"] not in kinds):
            continue
        present = {a: float(sims[a][cid]) for a in axes if a in sims and cid in sims[a]}
        if not present:
            continue
        tot = sum(w[a] for a in present)
        score = sum(w[a] * v for a, v in present.items()) / tot if tot else 0.0
        items.append({"id": cid, "name": meta[cid]["name"], "score": round(score, 6), "axes": {a: (round(present[a], 6) if a in present else None) for a in AXES} | {"motion": None}, "thumb": None})
    items.sort(key=lambda it: (-it["score"], it["id"]))
    note = None
    if min_score is not None:
        keep = [it for it in items if it["score"] >= min_score]
        if not keep:
            note = f"no similar asset above min_score {min_score:g}: lower min_score or check the filters"
            keep = items[:3]
        items = keep
    return {"ok": True, "probe": {"kind": probe_kind, "coherence": round(coherence, 6)}, "items": items[:max(k, 3) if note else k], "took_ms": round((time.time() - t0) * 1000, 2), **({"note": note} if note else {})}
