# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""plate_pick / plate_prep: how faithful is a regenerated reference plate to its approved V3 original, and the deterministic alpha cut of the winner.

Ported from the owner's shelf (tools/texlib/fidelity.py, SPIKE 2026-10-04) with scipy's operations replaced by imgops: per variant the silhouette (luminance above the
background threshold on the generated black) is fitted to V3's alpha by bounding box, the variant resampled into V3's frame, then silhouette IoU, structure = correlation of
the DoG(1..4 px) luminance inside V3's alpha, colour = mean |dRGB| inside it; score = iou x structure x (1 - colour). UNVALIDATED as a ranking (the shelf says so): it
ranks, the user picks. The cut is luminance > threshold, opening, fill holes, 1 px feather."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import imgops

BG_T = 0.06
OPENING = 3                   # the recorded method (alpha.json) says x3; the shelf's fidelity.py scoring mask uses x2 - the 2-vs-3 gap is reported by the tests, not decided here
METHOD = "luminance > {t}, opening x{n}, fill holes, 1 px feather (pipeline/plates.py cut)"
LUM = np.array([0.2126, 0.7152, 0.0722])
VIEWS = ("Front", "Back", "Left", "Right")


class PlateError(ValueError):
    pass


def check_view(view: str, paired: bool = False) -> None:
    if view not in VIEWS:
        raise PlateError(f"view is one of {', '.join(VIEWS)}")
    if paired and view in ("Left", "Right"):
        raise PlateError("paired pieces use Front and Back only")


def _lum(c):
    return c @ LUM


def _dog(x):
    return imgops.gaussian(x, 1.0) - imgops.gaussian(x, 4.0)


def score(v3_plate, variants, bg_threshold: float = BG_T) -> list:
    """Ranked rows [{file, size, iou, structure, colour_mad, score}] best first."""
    V = np.asarray(Image.open(v3_plate).convert("RGBA")).astype(float) / 255
    A = V[..., 3] > 0.5
    if not A.any():
        raise PlateError("the V3 plate has no alpha subject: it must be an RGBA plate on transparent")
    Vc = V[..., :3]
    ys, xs = np.nonzero(A)
    vb = (xs.min(), ys.min(), xs.max(), ys.max())
    dog_v = _dog(_lum(Vc))[A]
    rows = []
    for f in variants:
        G = np.asarray(Image.open(f).convert("RGB")).astype(float) / 255
        m = imgops.fill_holes(imgops.binary_opening(_lum(G) > bg_threshold, 2))
        gy, gx = np.nonzero(m)
        if not len(gy):
            raise PlateError(f"{Path(f).name}: no subject above the background threshold {bg_threshold}: is it on black?")
        gb = (gx.min(), gy.min(), gx.max(), gy.max())
        crop = Image.fromarray((G[gb[1]:gb[3] + 1, gb[0]:gb[2] + 1] * 255).astype(np.uint8)).resize((vb[2] - vb[0] + 1, vb[3] - vb[1] + 1), Image.LANCZOS)
        mcrop = Image.fromarray((m[gb[1]:gb[3] + 1, gb[0]:gb[2] + 1] * 255).astype(np.uint8)).resize(crop.size, Image.BILINEAR)
        R = np.zeros_like(Vc)
        M = np.zeros(A.shape, bool)
        R[vb[1]:vb[3] + 1, vb[0]:vb[2] + 1] = np.asarray(crop).astype(float) / 255
        M[vb[1]:vb[3] + 1, vb[0]:vb[2] + 1] = np.asarray(mcrop) > 127
        iou = (M & A).sum() / (M | A).sum()
        b = _dog(_lum(R))[A]
        struct = float(np.corrcoef(dog_v, b)[0, 1])
        col = float(np.abs(Vc[A] - R[A]).mean())
        rows.append({"file": Path(f).name, "path": str(f), "size": list(G.shape[1::-1]), "iou": round(float(iou), 4), "structure": round(struct, 4),
                     "colour_mad": round(col, 4), "score": round(float(iou * struct * (1 - col)), 4)})
    rows.sort(key=lambda r: -r["score"])
    return rows


def cut(src, out, bg_threshold: float = BG_T, opening_iters: int = OPENING, overwrite: bool = False) -> dict:
    """The winner's alpha cut: an RGBA PNG at the source's size. Refuses a source with no subject (or one that is all subject), and never overwrites."""
    out = Path(out)
    if out.exists() and not overwrite:
        raise PlateError(f"never overwrites: {out} exists (delete it or write to a new directory)")
    G = np.asarray(Image.open(src).convert("RGB"))
    g = G.astype(np.float32) / 255
    mask = imgops.fill_holes(imgops.binary_opening(_lum(g) > bg_threshold, opening_iters))
    cover = float(mask.mean())
    if not 0.05 <= cover <= 0.9:
        raise PlateError(f"the cut found no subject (cover {cover:.3f}): the background is not near-black; raise bg_threshold or regenerate on black")
    alpha = np.clip(imgops.gaussian(mask.astype(np.float64), 0.7), 0, 1)               # the 1 px feather
    rgba = np.dstack([G, (alpha * 255 + 0.5).astype(np.uint8)])
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out)
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    return {"alpha_cover": round(cover, 4), "plate": str(out), "size": [w, h], "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "bg_threshold": bg_threshold, "opening_iters": opening_iters}


def _sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(root, piece: str, view: str, v3_plate, variants, out_dir, pick=None, paired: bool = False, bg_threshold: float = BG_T,
        opening_iters: int = OPENING, min_px: int = 1024) -> dict:
    """score -> pick (the best, or the user's ``pick`` 1-4) -> cut -> check; writes <out_dir>/<View>.png and merges the view into alpha.json."""
    check_view(view, paired)
    variants = [Path(v) for v in variants]
    if len(variants) < 4:
        raise PlateError("never fewer than 4 per generation (the user's rule): re-run the plate generation")
    if not Path(v3_plate).exists():
        raise PlateError(f"V3 plate not found: put it at {v3_plate}")
    small = [v.name for v in variants if min(Image.open(v).size) < min_px]
    if small:
        raise PlateError(f"plates under {min_px} px lose relief detail ({', '.join(small)}); regenerate at 4K")
    rows = score(v3_plate, variants, bg_threshold)
    best = rows[0]
    chosen = variants[int(pick) - 1] if pick else Path(best["path"])
    if pick and not 1 <= int(pick) <= len(variants):
        raise PlateError("pick is 1 to 4")
    out_dir = Path(out_dir)
    target = out_dir / f"{view}.png"
    manifest_path = out_dir / "alpha.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"method": METHOD.format(t=bg_threshold, n=opening_iters), "plates": {}}
    sha = _sha(chosen)
    prior = manifest["plates"].get(view)
    if target.exists() and prior and prior.get("sha256") == sha:
        return {"piece": piece, "view": view, "skipped": True, "picked": chosen.name, "plate": str(target), "ranking": rows, "best": best["file"]}
    res = cut(chosen, target, bg_threshold, opening_iters)
    x0, y0, x1, y1 = res["bbox"]
    w, h = res["size"]
    picked_row = next(r for r in rows if r["file"] == chosen.name)
    checks = {"margins_frac": round(min(x0, y0, w - 1 - x1, h - 1 - y1) / max(w, h), 4), "aspect": round((x1 - x0 + 1) / (y1 - y0 + 1), 4),
              "view_correspondence": picked_row["iou"]}
    manifest["plates"][view] = {"source": chosen.name, "size": res["size"], "alpha_cover": res["alpha_cover"], "sha256": sha}
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1))
    (out_dir / f"fidelity_{view}.json").write_text(json.dumps({"v3": str(v3_plate), "variants": [{k: v for k, v in r.items() if k != "path"} for r in rows], "best": best["file"]}, indent=1))
    return {"piece": piece, "view": view, "ranking": [{k: v for k, v in r.items() if k != "path"} for r in rows], "best": best["file"], "picked": chosen.name,
            "alpha_cover": res["alpha_cover"], "plate": str(target), "manifest": str(manifest_path), "checks": checks}


STAGES = ("prompt", "score", "cut", "run", "status")


def tool(stage, root, piece="", view="Front", paired=False, v3_dir="", variants_dir="", design_words="", palette="", pick=None, bg_threshold=BG_T,
         opening_iters=OPENING, min_px=1024) -> dict:
    """The api tool behind lampway_plate_pick: prompt | score | cut | run (score + cut + check) | status. Paths are relative to the project root (the caller has jailed them)."""
    if stage not in STAGES:
        raise PlateError(f"stage is one of {', '.join(STAGES)}")
    if not piece:
        raise PlateError("name the piece (e.g. Boots1)")
    root = Path(root)
    out_dir = root / piece / "plates_4k_alpha"
    if stage == "status":
        p = out_dir / "alpha.json"
        man = json.loads(p.read_text()) if p.exists() else {"plates": {}}
        return {"piece": piece, "plates": man["plates"], "done": sorted(man["plates"]), "missing": [v for v in (("Front", "Back") if paired else VIEWS) if v not in man["plates"]]}
    check_view(view, paired)
    v3 = root / v3_dir / f"{view}.png" if v3_dir else None
    if stage == "prompt":
        names = {"Front": "front", "Back": "back", "Left": "left side", "Right": "right side"}
        variables = {"view": names[view], **({"design_inventory": design_words} if design_words else {}), **({"palette": palette} if palette else {})}
        return {"piece": piece, "view": view, "template": "plate-4k-crisper", "variables": variables, "reference": str(v3) if v3 else None,
                "how": "render this template (lampway_prompt_render) and pass it with the V3 plate as the reference to the image generator; 4 images per view, never fewer"}
    if v3 is None:
        raise PlateError("v3_dir is needed: the project folder holding <View>.png (RGBA) for the piece")
    if not variants_dir:
        raise PlateError("variants_dir is needed: the folder with 1.jpg .. 4.jpg for this view")
    vs = [p for p in sorted((root / variants_dir).glob("*")) if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.stem.isdigit()]
    if stage == "score":
        if len(vs) < 4:
            raise PlateError("never fewer than 4 per generation (the user's rule): re-run the plate generation")
        if not v3.exists():
            raise PlateError(f"V3 plate not found: put it at {v3}")
        rows = score(v3, vs, bg_threshold)
        return {"piece": piece, "view": view, "ranking": [{k: v for k, v in r.items() if k != "path"} for r in rows], "best": rows[0]["file"]}
    if stage == "cut":
        chosen = vs[int(pick) - 1] if pick else None
        if chosen is None:
            raise PlateError("cut needs pick (1 to 4): run score first, or use stage run")
        return cut(chosen, out_dir / f"{view}.png", bg_threshold, opening_iters)
    return run(root, piece, view, v3, vs, out_dir, pick, paired, bg_threshold, opening_iters, min_px)
