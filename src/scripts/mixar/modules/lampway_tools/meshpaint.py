# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh-paint texturing: the best texture source so far (the shelf, 2026-10-05).

Instead of projecting V3's own plates (silhouette IoU 0.75-0.89 against our mesh), an image model PAINTS V3's design over a clay
render of OUR mesh, so the painted plate lands on the geometry (projection IoU 0.987 in all four views on the chest). The workflow:

  1. a clay render of our mesh per cardinal view                                  (tool clay_view)
  2. the image backend paints the design over it as flat albedo, 4 variants per view; the references are, in order, the clay
     render, a painted view for consistency, and V3's design plate of that view      (server: imagegen, tripo or codex_cli)
  3. pick 1 of 4 per view (silhouette IoU against the clay render, plus the eye)
  4. the clay-alpha plate set                                                      (tool mesh_paint_set)
  5. projection at 4096 with no warp (RP_COLOR_FULL=1 RP_NO_FLOW=1) into its own directory, then the masks
  6. the projected ``v3_colour_atlas.png`` is also a usable albedo: the live material toggle (albedo.py)

Views are generated in a chain that keeps them consistent: a side first, then the front (matching that side), then the rest
(matching the front).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image

VIEWS = ("Front", "Back", "Left", "Right")
ORDER = ("Left", "Front", "Back", "Right")
PROMPTS = Path(__file__).resolve().parent / "scripts" / "texlib" / "prompts"
_IMG = (".png", ".jpg", ".jpeg", ".webp")


class MeshPaintError(RuntimeError):
    pass


@dataclass
class MeshPaintSpec:
    piece: str
    mesh: str                     # the rebuild's patched UV mesh (fbx) the clay renders are made from
    design_dir: str               # V3's design plates: Front.png, Back.png, Left.png, Right.png
    work_dir: str                 # <project>/<piece>/meshpaint: clay/, runs/<View>/, picks.json, set/, prompts/
    turn: float = -90.0
    clay_res: int = 2048


def consistency_view(view: str, painted) -> Optional[str]:
    """Which already-painted view to hand the model as the SECOND image: the front matches a side, the others the front."""
    painted = list(painted)
    if view == "Front":
        return next((v for v in painted if v in ("Left", "Right")), None)
    if "Front" in painted:
        return "Front"
    return painted[0] if painted else None


def prompt_for(view: str, consistency: Optional[str]) -> str:
    text = (PROMPTS / ("prompt_meshpaint_v2_front.txt" if view == "Front" else "prompt_meshpaint_v2.txt")).read_text(encoding="utf-8").strip()
    if consistency is None:                                        # nothing painted yet: no SECOND image; the design plate moves up
        text = re.sub(r"The SECOND image is the same armor already painted.*?style\. ", "", text, flags=re.S)
        text = text.replace("The THIRD image", "The SECOND image")
    return text


def refs_for(spec: MeshPaintSpec, view: str, consistency: Optional[str], picks: dict) -> list:
    refs = [str(Path(spec.work_dir) / "clay" / f"clay_{view}.png")]
    if consistency is not None:
        refs.append(picks[consistency])
    refs.append(str(Path(spec.design_dir) / f"{view}.png"))
    return refs


def silhouette_iou(clay_png, painted_png) -> float:
    """The shelf's measure: the clay render's silhouette (background difference) against the painted image's, at 512 px."""
    clay = np.asarray(Image.open(clay_png).convert("RGB").resize((512, 512))).astype(float) / 255
    bg = np.median(np.r_[clay[:8, :8].reshape(-1, 3), clay[-8:, -8:].reshape(-1, 3)], 0)
    cm = np.abs(clay - bg).max(-1) > 0.03
    p = np.asarray(Image.open(painted_png).convert("RGB").resize((512, 512))).astype(float) / 255
    pbg = np.median(np.r_[p[:8, :8].reshape(-1, 3), p[-8:, -8:].reshape(-1, 3)], 0)
    pm = np.abs(p - pbg).max(-1) > 0.08
    return float((pm & cm).sum() / max((pm | cm).sum(), 1))


def rank_variants(run_dir, clay_png) -> list:
    files = sorted(str(p) for p in Path(run_dir).glob("*") if p.suffix.lower() in _IMG and p.stem.isdigit())
    return sorted(((f, silhouette_iou(clay_png, f)) for f in files), key=lambda x: -x[1])


def pick_best(run_dir, clay_png) -> str:
    ranked = rank_variants(run_dir, clay_png)
    if not ranked:
        raise FileNotFoundError(f"no variants in {run_dir}")
    return ranked[0][0]


def _picks_path(spec: MeshPaintSpec) -> Path:
    return Path(spec.work_dir) / "picks.json"


def load_picks(spec: MeshPaintSpec) -> dict:
    try:
        return json.loads(_picks_path(spec).read_text(encoding="utf-8")).get("picks", {})
    except (OSError, ValueError):
        return {}


def record_pick(spec: MeshPaintSpec, view: str, file: str, iou: Optional[float] = None) -> None:
    if view not in VIEWS:
        raise ValueError(f"view {view!r}: one of {list(VIEWS)}")
    path = _picks_path(spec)
    data = json.loads(path.read_text()) if path.exists() else {"picks": {}, "iou": {}}
    data["picks"][view] = file
    if iou is not None:
        data["iou"][view] = round(iou, 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def plate_args(spec: MeshPaintSpec, require_all: bool = True) -> list:
    picks = load_picks(spec)
    missing = sorted(set(VIEWS) - set(picks))
    if require_all and missing:
        raise ValueError(f"no pick yet for {', '.join(missing)}")
    return [str(Path(spec.work_dir) / "clay"), str(Path(spec.work_dir) / "set")] + [f"{v}={f}" for v, f in picks.items()]


def output_name(tag: str) -> str:
    return f"{tag}_meshpaint"


def projection_spec(base, spec: MeshPaintSpec):
    """The rebuild's own RebuildSpec with the plate set, 4096, colour at full resolution and no warp."""
    import dataclasses
    return dataclasses.replace(base, plates_dir=str(Path(spec.work_dir) / "set"), res=4096, color_full=True, no_flow=True)


def run_all(spec: MeshPaintSpec, clay: Callable, generate: Callable, plates: Callable, project: Callable) -> dict:
    """The whole workflow with its stages injected (the app's job passes the real ones). Auto-picks the best of each view's
    variants by silhouette IoU against the clay render."""
    clay()
    picks, ious = {}, {}
    painted = []
    for view in ORDER:
        cons = consistency_view(view, painted)
        files = generate(view, prompt_for(view, cons), refs_for(spec, view, cons, picks), str(Path(spec.work_dir) / "runs" / view))
        if not files:
            raise MeshPaintError(f"the image backend returned no images for {view}")
        clay_png = Path(spec.work_dir) / "clay" / f"clay_{view}.png"
        ranked = rank_variants(Path(files[0]).parent, clay_png)
        if not ranked:
            raise MeshPaintError(f"no usable variants for {view}")
        best, iou = ranked[0]
        record_pick(spec, view, best, iou)
        picks[view], ious[view] = best, iou
        painted.append(view)
    plates()
    result = project()
    return {"ok": True, "picks": picks, "iou": ious, "projection": result}
