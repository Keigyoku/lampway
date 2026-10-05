# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""seed_audit, the deterministic half: measure every seed of a piece, then rank them by the captain's law - PROPORTIONS first, defects second, V3 fidelity third.

The measures are the auditors' scratch scripts promoted (seed_audit/<piece>/fold.py and meas.py): the count of interior edges whose two faces fold back by more than 120 / 90 degrees
(dot of unit normals < -0.5 / < 0), the boundary and non-manifold edge counts, the connected components, and the CLOSED BOWL detector (a floor across a limb's opening: the first surface a
ray meets going down from the rim, over the opening's footprint). The model judge reads the numbers and the lineup renders; only the captain's ``record`` writes a verdict. Pure numpy."""

import json
import time
from pathlib import Path

import numpy as np

from . import imgops

TIE = 0.05                   # [UNVERIFIED] score_rms within 5 % of the best is a tie: the Boots1 auditor measured a 3.9 % rms spread as noise (every ratio within ~1.2 % across variants)
CAP_DEPTH = (0.02, 0.35)     # a floor between 2 % and 35 % of the height below the rim is a bowl; deeper is the sole
RIM_BAND = 0.05          # the rolled cuffs of the real boots are not level: a 1.5 % band is not a ring, 5 % is


class AuditError(ValueError):
    pass


def load_mesh(path):
    d = np.load(path)
    return d["V"].astype(float), d["T"]


def folds(V, T) -> dict:
    """The auditors' fold.py: interior edges by the dot of their faces' unit normals."""
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    ar = np.linalg.norm(n, axis=1)
    ok = ar > 1e-12
    n = n / np.where(ok, ar, 1)[:, None]
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    fi = np.tile(np.arange(len(T)), 3)
    key = np.sort(E, 1)
    o = np.lexsort((key[:, 1], key[:, 0]))
    key, fi = key[o], fi[o]
    same = (key[1:] == key[:-1]).all(1)
    a, b = fi[:-1][same], fi[1:][same]
    dot = (n[a] * n[b]).sum(1)
    return {"folds_gt120": int((dot < -0.5).sum()), "folds_gt90": int((dot < 0).sum()), "degenerate_faces": int((~ok).sum()), "interior_edges": int(len(a))}


def topology(V, T) -> dict:
    e = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    e.sort(1)
    u, c = np.unique(e, axis=0, return_counts=True)
    n = len(V)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in u:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    counts = np.bincount(np.unique(roots, return_inverse=True)[1])
    return {"edges_bnd": int((c == 1).sum()), "edges_nm": int((c > 2).sum()), "components": int(len(counts)), "comp_sizes_top": sorted(counts.tolist(), reverse=True)[:8]}


def caps(V, T, grid: int = 96) -> list:
    """Closed bowls across an opening at the top (z up): the footprint is the hole inside the rim ring (the cells with surface in the top RIM_BAND of the height); a cap is a floor
    over most of that footprint at a depth of CAP_DEPTH of the height. Returns [{where, depth_frac, floor_z, coverage}]."""
    lo, hi = V.min(axis=0), V.max(axis=0)
    h = hi[2] - lo[2]
    if h <= 0:
        return []
    span = max(hi[0] - lo[0], hi[1] - lo[1])
    cell = span / grid
    ix = lambda x: np.clip(((x - lo[0]) / cell).astype(int), 0, grid - 1)               # noqa: E731
    iy = lambda y: np.clip(((y - lo[1]) / cell).astype(int), 0, grid - 1)               # noqa: E731
    rim_z = hi[2] - RIM_BAND * h
    top = np.zeros((grid, grid), bool)
    depth = np.full((grid, grid), -np.inf)
    k = 7                                                                               # barycentric samples per triangle edge: a floor sheet has few vertices, so sample its surface
    bary = np.array([(i / k, j / k, (k - i - j) / k) for i in range(k + 1) for j in range(k + 1 - i)])
    for chunk in np.array_split(np.arange(len(T)), max(1, len(T) // 20000)):
        P = np.einsum("sb,tbc->tsc", bary, V[T[chunk]]).reshape(-1, 3)
        ci, cj = iy(P[:, 1]), ix(P[:, 0])
        np.maximum.at(depth, (ci, cj), P[:, 2])
        m = P[:, 2] >= rim_z
        top[ci[m], cj[m]] = True
    ring = imgops.binary_opening(top, 0) if False else top
    filled = imgops.fill_holes(ring)
    opening = filled & ~ring
    if opening.sum() < 20:
        return []
    below = depth < rim_z                                                               # cells whose highest surface lies below the rim
    floored = opening & below & np.isfinite(depth)
    coverage = float(floored.sum() / opening.sum())
    if coverage < 0.5:
        return []
    floor_z = float(np.median(depth[floored]))
    frac = (hi[2] - floor_z) / h
    if not CAP_DEPTH[0] <= frac <= CAP_DEPTH[1]:
        return []
    zs = depth[floored]
    return [{"where": f"z {np.percentile(zs, 10):.3f}..{np.percentile(zs, 90):.3f} of {lo[2]:.3f}..{hi[2]:.3f}", "kind": "opening", "depth_frac": round(frac, 3),
             "floor_z": round(floor_z, 4), "coverage": round(coverage, 3)}]


def measure_mesh(path) -> dict:
    V, T = load_mesh(path)
    row = {"faces": int(len(T)), **folds(V, T), **topology(V, T)}
    row["caps"] = caps(V, T)
    return row


def rank(per_seed: dict) -> dict:
    """Proportions first (score_rms, lower is better; seeds within TIE of the best tie), defects second (folds per 1000 faces, caps, non-manifold edges), fidelity third (higher better)."""
    ids = list(per_seed)
    rms = {i: per_seed[i].get("score_rms") for i in ids}
    known = [v for v in rms.values() if v is not None]
    best = min(known) if known else None

    def tier(i):
        if best is None or rms[i] is None:
            return 0
        return int((rms[i] - best) / max(best * TIE, 1e-9)) if rms[i] - best > best * TIE else 0         # bins TIE wide: inside the first bin is a tie
    def defects(i):
        m = per_seed[i]
        return (m.get("folds_gt120", 0) / max(m.get("faces", 1), 1) * 1000 + 25 * len(m.get("caps", [])) + 0.05 * m.get("edges_nm", 0)
                + 0.002 * max(m.get("components", 1) - 1, 0))
    order = sorted(ids, key=lambda i: (tier(i), defects(i), -(per_seed[i].get("fidelity") or 0), rms[i] if rms[i] is not None else 9))
    why = []
    if best is not None:
        spread = (max(known) - best) / best if best else 0
        why.append(f"proportions {'tie' if spread <= TIE else 'differ'} (spread {spread * 100:.1f} % of the best score_rms): " + ("defects decide" if spread <= TIE else "the better proportions win first"))
    return {"ranking": order, "why": "; ".join(why), "scorer_notes": ["piece_ratios biases (helmet crest +39 % DW, waist design flare, boots knee height, gauntlets blind to slotted plates): a ratio never wins alone"]}


def run(root, stage, piece, seeds=None, scores=None, proposals=None, by="agent", out_dir="", **_):
    if stage not in ("measure", "judge", "record"):
        raise AuditError("stage is measure | lineup | judge | record")
    root = Path(root)
    out = root / (out_dir or f"{piece}/seed_audit")
    meas_path = out / "meas.json"
    if stage == "measure":
        if not seeds or len(seeds) < 2:
            raise AuditError("an audit ranks at least two seeds: ingest the variants first (seed_catalog ingest_variants)")
        per, files = {}, {}
        for s in seeds:
            p = Path(s) if Path(s).is_absolute() else root / s
            if p.suffix != ".npz":
                p = p.with_suffix(".npz")
            if not p.exists():
                raise AuditError(f"{p.name} not found: run mesh_to_npz first (the audit reads the seed as npz)")
            sid = p.stem
            per[sid] = measure_mesh(p)
            files[sid] = str(p)
            if scores and sid in scores:
                per[sid]["score_rms"] = float(scores[sid])
        r = rank(per)
        body = {"piece": piece, "per_seed": per, **r, "recommend": {"seed": r["ranking"][0], "why": r["why"]}, "confidence": "low" if "tie" in r["why"] else "medium", "files": files,
                "t": time.time()}
        out.mkdir(parents=True, exist_ok=True)
        meas_path.write_text(json.dumps(body, indent=1))
        return dict(body, audit=str(out / "audit.json"), meas=str(meas_path))
    if not meas_path.exists():
        raise AuditError("run stage measure first")
    meas = json.loads(meas_path.read_text())
    if stage == "judge":
        if len(meas["per_seed"]) > 6:
            raise AuditError("one auditor ranks at most six; split by reroll group")
        return {"piece": piece, "packet": {"meas": str(meas_path), "ranking": meas["ranking"], "per_seed": meas["per_seed"], "lineup": sorted(str(p) for p in out.glob("lineup_*.png"))},
                "how": "read the numbers and the lineup renders against the V3 plate; propose {seed: {verdict: usable|fix|reject, defects: [...], rank}}; the judge proposes, the captain records"}
    if not isinstance(proposals, dict):
        raise AuditError("record needs proposals: {seed: {verdict, defects, rank}}")
    audit = {"piece": piece, "ranking": meas["ranking"], "recommend": meas["recommend"], "per_variant": proposals, "scorer_check": meas["scorer_notes"], "by": by, "confidence": meas["confidence"]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(audit, indent=1))
    written = []
    if by == "captain":
        dec = root / "seeds" / "decisions.jsonl"
        dec.parent.mkdir(parents=True, exist_ok=True)
        with dec.open("a") as fh:
            for sid, p in proposals.items():
                fh.write(json.dumps({"kind": "decision", "t": time.time(), "question": "seed_pick", "options": ["usable", "fix", "reject", "pick", "reroll"], "answer": p.get("verdict"),
                                     "decider": "captain", "descriptor": {"piece": piece, "seed": sid, "measures": meas["per_seed"].get(sid, {})}}) + "\n")
                written.append(sid)
    return {"piece": piece, "audit": str(out / "audit.json"), "verdict_rows_written": written, "verdict_written": bool(written),
            "note": "" if written else "proposals only: a model's or agent's verdict is not a ruling; the captain records it"}
