# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""parts_critique: the auditor's critique of a transferred or segmented part set, as typed proposals a person can read and ``apply_part_fixes`` can consume.

Rules first, the model second. ``flags`` is deterministic (weak-vote and far-transfer islands from the transfer's own ``islands.json``, parts left with too few polygons, a left/right
part that crosses the sagittal plane, left/right area asymmetry); only the unresolved flags go to a model, which proposes fixes with reasons; ``write_fixes`` validates them (unknown
part, empty selector, and the CLASS GUARD: a fix may not move triangles between a metal part and a cloth/leather part, because the material class comes from the user or the
recipe, never from a render); ``check`` is a dry run that reproduces ``apply_part_fixes``'s own ``{triangles, from}`` counts without writing an owner map. Pure numpy.
"""

import json
import re
from pathlib import Path

import numpy as np

WEAK = 0.6                   # [UNVERIFIED] transfer_parts' own default: an island whose vote share is below it is flagged
FAR_MM = 30.0                # [UNVERIFIED] transfer_parts' own default: a mean transfer distance above it is flagged
MIN_FACES = 50               # [UNVERIFIED] a part with fewer polygons than this is flagged as probably fragmentary
ASYMMETRY = (0.8, 1.25)      # [UNVERIFIED] area(_L) / area(_R) outside this is flagged
LIMIT_DEFAULT, LIMIT_MAX = 12, 20


class CritiqueError(ValueError):
    pass


def family(cls):
    """metal | soft | other, from the recipe's motion class text (rigid-metal, cloth-sim, skinned-flex, leather ...)."""
    c = (cls or "").lower()
    if any(k in c for k in ("cloth", "flex", "sim", "leather", "linen", "soft")):
        return "soft"
    if any(k in c for k in ("metal", "rigid", "plate")):
        return "metal"
    return "other"


def _recipe(path):
    parts = json.loads(Path(path).read_text())["parts"]
    return list(parts), {n: parts[n].get("class", "") for n in parts}


def flags(transfer_dir, recipe, piece_uv=None, weak=WEAK, far_mm=FAR_MM, min_faces=MIN_FACES):
    """The deterministic pre-pass. Returns {"islands": [...], "parts": [...], "summary": {...}}."""
    names, classes = _recipe(recipe)
    td = Path(transfer_dir)
    out_islands = []
    for row in json.loads((td / "islands.json").read_text()):
        why = []
        if row["confidence"] < weak:
            why.append(f"weak vote {row['confidence']:.2f} < {weak}")
        if row["mean_dist_mm"] > far_mm:
            why.append(f"far transfer {row['mean_dist_mm']:.0f} mm > {far_mm:g}")
        if why:
            out_islands.append({"island": row["island"], "part": row["part"], "runner_up": row.get("runner_up"), "area_m2": row.get("area_m2"), "why": why})
    owner_poly_path = td / "owner_poly.npy"
    part_rows = []
    if owner_poly_path.exists():
        poly = np.load(owner_poly_path)
        counts = np.bincount(poly, minlength=len(names))
        for k, n in enumerate(names):
            if counts[k] < min_faces:
                part_rows.append({"part": n, "why": [f"{int(counts[k])} polygons < {min_faces}" if counts[k] else "no polygons: the part is absent"]})
    if piece_uv and Path(piece_uv).exists() and (td / "owner_tri.npy").exists():
        d = np.load(piece_uv)
        P = d["V"][d["T"]]
        tri = np.load(td / "owner_tri.npy")
        area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2
        cx = (d["V"][:, 0].min() + d["V"][:, 0].max()) / 2          # the piece's own sagittal plane (x of its bounding-box centre)
        by_name = {n: k for k, n in enumerate(names)}
        for n in names:
            m = re.fullmatch(r"(.+?)_([LR])", n)
            if not m or not (tri == by_name[n]).any():
                continue
            xs = P[tri == by_name[n]][:, :, 0]
            side = m.group(2)
            if (side == "L" and xs.min() < cx - 1e-9 and xs.max() > cx + 1e-9 and (cx - xs.min()) > 0.1 * (xs.max() - xs.min())) or \
                    (side == "R" and xs.min() < cx - 1e-9 and xs.max() > cx + 1e-9 and (xs.max() - cx) > 0.1 * (xs.max() - xs.min())):
                part_rows.append({"part": n, "why": ["crosses the sagittal plane"]})
            other = f"{m.group(1)}_{'R' if side == 'L' else 'L'}"
            if side == "L" and other in by_name and (tri == by_name[other]).any():
                ratio = area[tri == by_name[n]].sum() / max(area[tri == by_name[other]].sum(), 1e-12)
                if not ASYMMETRY[0] <= ratio <= ASYMMETRY[1]:
                    part_rows.append({"part": n, "why": [f"area ratio to {other} is {ratio:.2f} (outside {ASYMMETRY[0]}..{ASYMMETRY[1]})"]})
    return {"islands": out_islands, "parts": part_rows, "summary": {"flagged_islands": len(out_islands), "flagged_parts": len(part_rows), "weak": weak, "far_mm": far_mm}}


def dry_run(transfer_dir, piece_uv, recipe, fixes):
    """apply_part_fixes' own arithmetic without writing: per fix {fix, target, triangles, from} or {fix, error}. Also returns the relabelled triangle array."""
    names, _ = _recipe(recipe)
    td = Path(transfer_dir)
    d = np.load(piece_uv)
    P = d["V"][d["T"]]
    tri = np.load(td / "owner_tri.npy").copy()
    isl = np.load(td / "island_tri.npy")
    cen = P.mean(1)
    log = []
    for k, f in enumerate(fixes):
        t = f.get("target_part")
        if t not in names:
            log.append({"fix": k, "error": f"unknown target_part {t!r}"})
            continue
        m = np.zeros(len(tri), bool)
        if f.get("islands"):
            m |= np.isin(isl, f["islands"])
        if f.get("bbox_fbx"):
            lo, hi = np.array(f["bbox_fbx"][0]), np.array(f["bbox_fbx"][1])
            m |= np.all((cen >= lo) & (cen <= hi), axis=1)
        if f.get("only_from_parts"):
            m &= np.isin(tri, [names.index(n) for n in f["only_from_parts"] if n in names])
        before = np.unique(tri[m], return_counts=True)
        tri[m] = names.index(t)
        log.append({"fix": k, "target": t, "triangles": int(m.sum()), "from": {names[int(a)]: int(b) for a, b in zip(*before)}})
    return log, tri


def validate(proposals, recipe, transfer_dir=None, piece_uv=None):
    """Refuse what must not be written: an unknown part, an empty selector, a move across the metal/soft class line. Returns the clean fixes."""
    names, classes = _recipe(recipe)
    fixes = []
    for k, p in enumerate(proposals or []):
        t = p.get("target_part")
        if t not in names:
            raise CritiqueError(f"unknown target_part {t!r}; the parts are: {names}")
        if not p.get("islands") and not p.get("bbox_fbx"):
            raise CritiqueError(f"fix {k}: a fix needs islands or bbox_fbx")
        fixes.append({key: p[key] for key in ("target_part", "islands", "bbox_fbx", "only_from_parts", "reason", "evidence") if key in p})
    if transfer_dir and piece_uv:
        log, _ = dry_run(transfer_dir, piece_uv, recipe, fixes)
        for entry, f in zip(log, fixes):
            for src in entry.get("from", {}):
                a, b = family(classes.get(src)), family(classes.get(f["target_part"]))
                if src != f["target_part"] and {a, b} == {"metal", "soft"}:
                    raise CritiqueError(f"fix {entry['fix']} moves {entry['from'][src]} triangles of {src} ({classes[src]}) to {f['target_part']} ({classes[f['target_part']]}): "
                                        "material class comes from the user or the recipe, never from a render: ask")
    return fixes


def packet(root, piece, flagged, renders, parts, limit=LIMIT_DEFAULT):
    """What a vision-capable model reads: the flags (at most `limit`, the biggest first), the part list and the render paths."""
    limit = max(1, min(int(limit or LIMIT_DEFAULT), LIMIT_MAX))
    islands = sorted(flagged["islands"], key=lambda r: -(r.get("area_m2") or 0))[:limit]
    return {"piece": piece, "islands": islands, "parts": flagged["parts"], "all_parts": parts, "renders": renders, "limit": limit,
            "ask": "propose fixes as [{target_part, islands | bbox_fbx, only_from_parts?, reason, evidence}]; never change a part between metal and cloth/leather",
            "note": "proposals only: the user rules, and only apply_part_fixes writes an owner map"}


def run(root, stage, piece, recipe="", transfer_dir="", piece_uv="", owner_poly="", mesh="", proposals=None, fixes="", weak=WEAK, far_mm=FAR_MM,
        min_faces=MIN_FACES, limit=LIMIT_DEFAULT, turn=-90.0, render_fn=None, by="agent"):
    base = Path(root) / piece / "parts"
    if stage not in ("flags", "render", "judge", "write_fixes", "check"):
        raise CritiqueError(f"unknown stage {stage!r}; use flags | render | judge | write_fixes | check")
    if not recipe:
        raise CritiqueError("recipe is required (recipe.json with the parts and their classes)")
    names, _ = _recipe(recipe)
    if stage in ("flags", "judge", "write_fixes", "check") and not transfer_dir:
        raise CritiqueError("transfer_dir is required (the directory transfer_parts wrote: islands.json, island_tri.npy, owner_tri.npy)")
    if stage in ("flags", "judge"):
        fl = flags(transfer_dir, recipe, piece_uv or None, weak, far_mm, min_faces)
        if stage == "flags":
            return {"ok": True, "flagged": fl["summary"]["flagged_islands"] + fl["summary"]["flagged_parts"], **fl}
    if stage in ("render", "judge"):
        renders = []
        if render_fn is not None and mesh and owner_poly:
            base.mkdir(parents=True, exist_ok=True)
            renders = render_fn(mesh, owner_poly, recipe, str(base / "owner"), turn)
        if stage == "render":
            return {"ok": True, "renders": renders}
        return {"ok": True, **packet(root, piece, fl, renders, names, limit)}
    if stage == "write_fixes":
        if not piece_uv:
            raise CritiqueError("piece_uv is required to validate the fixes against the part set")
        clean = validate(proposals, recipe, transfer_dir, piece_uv)
        base.mkdir(parents=True, exist_ok=True)
        path = base / "fixes.json"
        path.write_text(json.dumps({"fixes": [{**f, "by": by} for f in clean]}, indent=1))
        return {"ok": True, "fixes": clean, "path": str(path)}
    # check: a recorded fixes file or the proposals, dry-run
    if not piece_uv:
        raise CritiqueError("piece_uv is required for check")
    if fixes:
        data = json.loads(Path(fixes).read_text())
        items = data.get("fixes", data) if isinstance(data, dict) else data
    else:
        items = proposals or []
    log, _ = dry_run(transfer_dir, piece_uv, recipe, items)
    return {"ok": all("error" not in e for e in log), "check": log}
