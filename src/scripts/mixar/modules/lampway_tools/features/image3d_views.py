# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_to_3d's views (specs/mixar_docs/image_to_3d.md, wiki/image_to_3d.md): a turnaround sheet cut into labelled panels before anything is built, paired
pieces held to front + back, the multi-view Studio slots answered as plans with their arguments, and a plate check before any of them.

detect_views  the sheet's subjects as connected components (alpha, else the border colour: segment_image's own labelling), the pieces over min_pixels kept,
              read LEFT TO RIGHT and named by ``views`` (the panel order is the user's or the sheet's: never guessed), each cropped with a margin to
              <out_dir>/<View>.png. (Mixar's own detect-views is a hosted endpoint; this is the deterministic path for transparent plates.)
plate_check   the subject keeps a margin from every border (>= 1 % of the side), the plate is at least 1024 px, it has a subject at all: a failing plate is
              named before a Studio plan, because a bad plate still costs the credits.
studio slots  studio:tripo -> tripo.mesh {front, left, right, back, paired} (100 credits, 4 variants at maximum polycount), studio:meshy ->
              meshy.multi_image_to_3d {images}, studio:hi3d -> hi3d.image_to_3d {images}: the plan_args for studio_plan; nothing is clicked."""

import os

import numpy as np
from PIL import Image

from . import common as C
from ..pipeline.segment_image import _foreground, label

ORDER = ("Front", "Left", "Right", "Back")
MIN_PX = 1024
MARGIN = 0.01


def detect_views(sheet, out_dir, views, min_pixels=2000):
    if not views:
        raise C.FeatureError("pass views (the panel order left to right, e.g. [Front, Left, Back, Right]): the side a panel shows is not guessed")
    bad = [v for v in views if v not in ORDER]
    if bad:
        raise C.FeatureError(f"unknown view {bad[0]!r}: the views are {', '.join(ORDER)}")
    im = Image.open(sheet)
    method = "alpha_components" if (im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info) else "color_regions"
    fg, _bg = _foreground(im, method)
    lab, n = label(fg)
    sizes = np.bincount(lab.ravel())
    keep = [k for k in range(1, n + 1) if sizes[k] >= int(min_pixels)]
    if len(keep) != len(views):
        raise C.FeatureError(f"the sheet holds {len(keep)} panels of at least {min_pixels} px, but views names {len(views)}: give one view per panel, left to right")
    boxes = []
    for k in keep:
        ys, xs = np.nonzero(lab == k)
        boxes.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    boxes.sort(key=lambda b: b[0])
    rgba = im.convert("RGBA")
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for v, (x0, y0, x1, y1) in zip(views, boxes):
        m = max(4, int(0.05 * max(x1 - x0, y1 - y0)))
        crop = rgba.crop((max(0, x0 - m), max(0, y0 - m), min(rgba.size[0], x1 + m), min(rgba.size[1], y1 + m)))
        p = os.path.join(out_dir, f"{v}.png")
        crop.save(p)
        out[v] = p
    return {"panels": len(keep), "views": out, "boxes": {v: list(b) for v, b in zip(views, boxes)}, "method": method}


def looks_like_sheet(path) -> bool:
    w, h = Image.open(path).size
    return w > 2 * h or h > 2 * w


def plate_check(path) -> list:
    im = Image.open(path)
    w, h = im.size
    problems = []
    if min(w, h) < MIN_PX:
        problems.append(f"{os.path.basename(path)} is {w} x {h}: a plate under {MIN_PX} px loses detail")
    method = "alpha_components" if (im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info) else "color_regions"
    fg, _bg = _foreground(im, method)
    if not fg.any():
        return problems + [f"{os.path.basename(path)} has no subject"]
    ys, xs = np.nonzero(fg)
    margin = min(int(xs.min()), int(ys.min()), w - 1 - int(xs.max()), h - 1 - int(ys.max())) / max(w, h)
    if margin < MARGIN:
        problems.append(f"{os.path.basename(path)}: the subject touches the border (margin {margin:.3f} < {MARGIN}): it will be cut off")
    return problems


def studio_plan(images, engine, paired):
    problems = [p for path in images.values() for p in plate_check(path)]
    if problems:
        raise C.FeatureError("fix the plate first (plate_pick / plate_prep); a bad plate still costs the credits: " + "; ".join(problems))
    slot = C.studio_slot("image_to_3d", engine)
    studio = engine.split(":", 1)[1]
    if studio == "tripo":
        slot["plan_args"] = {**{v.lower(): p for v, p in images.items()}, "paired": bool(paired)}
    else:
        order = [v for v in ORDER if v in images]
        slot["plan_args"] = {"images": [images[v] for v in order]}
    slot["views"] = sorted(images)
    return slot
