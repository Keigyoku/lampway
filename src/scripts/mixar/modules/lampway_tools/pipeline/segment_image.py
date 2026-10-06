# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""segment_image (specs/mixar_docs/segment_image.md): one image to per-part masks. Deterministic first: connected components (8-connected, union-find over row runs) on the alpha channel of a transparent plate, or on
the foreground of an opaque sheet (pixels that differ from the border's commonest colour). Pure NumPy and Pillow: no model, no network. Parts that touch or overlap are ONE component: that is the documented
limit, and the note says so. A model split (a studio or a vision model's boxes) is a slot and is refused until a provider is configured."""

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

MAX_PIXELS = 16_000_000
MAX_COMPONENTS = 64


class SegmentError(ValueError):
    pass


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def label(mask: np.ndarray):
    """(labels int32 with 0 = background, count). 8-connected components by union-find over each row's runs."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    parent, runs_prev, nxt = [0], [], 1
    for y in range(h):
        row = mask[y].astype(np.int8)
        d = np.diff(np.concatenate(([0], row, [0])))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        cur = []
        for s, e in zip(starts, ends):
            lab = 0
            for (ps, pe, pl) in runs_prev:
                if ps <= e and s <= pe:                                       # overlaps or touches diagonally in the row above
                    if lab == 0:
                        lab = _find(parent, pl)
                    else:
                        a, b = _find(parent, lab), _find(parent, pl)
                        if a != b:
                            parent[max(a, b)] = min(a, b)
                            lab = min(a, b)
            if lab == 0:
                lab = nxt
                parent.append(lab)
                nxt += 1
            cur.append((s, e, lab))
            labels[y, s:e] = lab
        runs_prev = cur
    roots = np.array([_find(parent, i) for i in range(len(parent))], dtype=np.int32)
    labels = roots[labels]
    uniq = np.unique(labels[labels > 0])
    remap = np.zeros(int(labels.max()) + 1, dtype=np.int32)
    remap[uniq] = np.arange(1, len(uniq) + 1)
    return remap[labels], len(uniq)


def _foreground(im: Image.Image, method: str):
    if method == "alpha_components":
        if im.mode not in ("RGBA", "LA", "PA") and "transparency" not in im.info:
            raise SegmentError("this image has no transparency: use color_regions or a model engine")
        a = np.asarray(im.convert("RGBA"))[:, :, 3]
        return a > 127, None
    rgb = np.asarray(im.convert("RGB")).astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    vals, counts = np.unique(border, axis=0, return_counts=True)
    bg = vals[int(counts.argmax())]
    diff = np.abs(rgb - bg).max(axis=2)
    return diff > 24, [int(x) for x in bg]


def _png(arr_or_im) -> bytes:
    b = io.BytesIO()
    (arr_or_im if isinstance(arr_or_im, Image.Image) else Image.fromarray(arr_or_im)).save(b, "PNG")
    return b.getvalue()


def segment(image, out_dir, method="alpha_components", min_pixels=6000, expected_parts=None) -> dict:
    if method == "model":
        raise SegmentError("model engines need a configured provider: none is configured, and no studio driver exists for segment yet: use method alpha_components or color_regions")
    if method not in ("alpha_components", "color_regions"):
        raise SegmentError("method is alpha_components | color_regions | model")
    im = Image.open(image)
    if im.width * im.height > MAX_PIXELS:
        raise SegmentError(f"the image is {im.width}x{im.height}: over 16 megapixels; scale it down first")
    mask, bg = _foreground(im, method)
    labels, n = label(mask)
    parts = []
    dropped = 0
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        if len(ys) < int(min_pixels):
            dropped += 1
            continue
        parts.append({"pixels": int(len(ys)), "bbox": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], "id": i})
    if len(parts) > MAX_COMPONENTS:
        raise SegmentError(f"too many components: raise min_pixels ({len(parts)} found, the limit is {MAX_COMPONENTS})")
    parts.sort(key=lambda p: (p["bbox"][0], p["bbox"][1]))                         # reading order: left to right, then top to bottom
    note = []
    names = [None] * len(parts)
    if expected_parts:
        if len(expected_parts) == len(parts):
            names = list(expected_parts)
        else:
            note.append(f"expected {len(expected_parts)} parts, found {len(parts)}: no labels were assigned")
    if len(parts) == 1:
        note.append("one component: parts that are touching or overlapping cannot be separated by alpha or colour alone (a model split is needed)")
    out = Path(out_dir)
    files, masks = {}, []
    rgb = np.asarray(im.convert("RGBA")).astype(np.float32)
    flat = rgb[:, :, :3] * (rgb[:, :, 3:4] / 255.0) + 255.0 * (1 - rgb[:, :, 3:4] / 255.0) if method == "alpha_components" else rgb[:, :, :3]
    over = flat.copy()
    palette = [(230, 60, 60), (60, 160, 230), (60, 200, 90), (240, 190, 40), (180, 90, 220), (240, 130, 40)]
    for k, p in enumerate(parts):
        m = labels == p["id"]
        files[f"mask_{k:02d}.png"] = _png((m * 255).astype(np.uint8))
        c = np.array(palette[k % len(palette)], dtype=np.float32)
        over[m] = over[m] * 0.5 + c * 0.5
        masks.append({"index": k, "path": str(out / f"mask_{k:02d}.png"), "bbox": p["bbox"], "pixels": p["pixels"], "label": names[k]})
    ov = Image.fromarray(over.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(ov)
    for k, p in enumerate(parts):
        d.text(((p["bbox"][0] + p["bbox"][2]) // 2 - 3, (p["bbox"][1] + p["bbox"][3]) // 2 - 5), str(k), fill=(0, 0, 0))
    files["overlay.png"] = _png(ov)
    for name, data in files.items():                                              # never overwrite a record: refuse before writing anything
        f = out / name
        if f.exists() and f.read_bytes() != data:
            raise SegmentError(f"{name} exists in {out} and differs: never overwrites a record: choose another out_dir or delete it")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    res = {"ok": True, "masks": masks, "overlay": str(out / "overlay.png"), "dropped_below_min_pixels": dropped, "method": method}
    if bg is not None:
        res["background"] = bg
    if note:
        res["note"] = "; ".join(note)
    return res
