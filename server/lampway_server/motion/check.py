# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The self-check of a sampled frame and the labelled contact sheet (specs/motion_graphics/scene.md, Self-check contract), ported from the spike's driver.

Per sampled frame: ``empty`` (fail) when under 0.01 % of pixels carry a local luminance step (a background-only frame measures 0.000 %),
``sparse`` (warn) under 0.1 %; authored text outside the 5 % title-safe area (fail); text under 22 px (fail); measured contrast of fully
visible text against a ring of pixels around its box under 4.5 (3.0 at 24 px and up) (fail); text overlapping a figure or card box (fail);
a mark cut by the frame edge (fail). The agent's own look at the contact sheet stays a step: the spike's round-cap dots were seen by eye only."""
import io
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

EMPTY, SPARSE = 0.0001, 0.001
MIN_TEXT_PX = 22


def validate_audit(audit, require_arrays=True):
    """Refuse malformed authored geometry rather than silently bypassing checks."""
    def number(value):
        try:
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        except OverflowError:
            return False

    if not isinstance(audit, dict):
        raise ValueError("audit: return an object with text and marks arrays")
    for key in ("text", "marks"):
        rows = audit.get(key, [] if not require_arrays else None)
        if not isinstance(rows, list):
            raise ValueError(f"audit {key}: return an array")
        for item in rows:
            if not isinstance(item, dict) or not isinstance(item.get("sel"), str) or not item["sel"]:
                raise ValueError(f"audit {key}: each item needs a string sel")
            box = item.get("box")
            if not isinstance(box, list) or len(box) != 4 or not all(number(x) for x in box) or box[2] < box[0] or box[3] < box[1]:
                raise ValueError(f"audit {key}: box must contain four finite ordered pixel coordinates")
            if key == "text" and (not isinstance(item.get("text"), str) or not number(item.get("font_px")) or item["font_px"] <= 0
                                  or not number(item.get("opacity")) or not 0 <= item["opacity"] <= 1):
                raise ValueError("audit text: use string text, positive finite font_px and opacity in 0..1")
    return audit


def frame_stats(png: bytes):
    """Pixel facts for the self-check: luminance spread and the share of pixels carrying a local luminance step."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    a = np.asarray(im.resize((im.width // 2, im.height // 2), Image.BILINEAR), dtype=np.float32)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    # detail: share of pixels with a local luminance step > 10/255. A smooth glow or a flat fill has none; text and marks do.
    g = np.abs(np.diff(lum, axis=0))[:, :-1] + np.abs(np.diff(lum, axis=1))[:-1, :]
    # Threshold decisions need the measured fraction; round only its presentation in finding details.
    return im, {"lum_mean": round(float(lum.mean()), 2), "lum_std": round(float(lum.std()), 2), "detail_share": float((g > 10).mean())}


def srgb_lum(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rel_lum(rgb):
    r, g, b = rgb
    return 0.2126 * srgb_lum(r) + 0.7152 * srgb_lum(g) + 0.0722 * srgb_lum(b)


def text_contrast(im, box, pad=10):
    """Measured contrast of a text box in the captured frame: background = median of a ring just outside the text box, text = the 2nd or
    98th luminance percentile inside it, whichever is further from the background."""
    W, H = im.size
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    # NumPy's RGB view works across the supported Pillow >=10 range; get_flattened_data is a newer Pillow API.
    inner = [rel_lum(p) for p in np.asarray(im.crop((x0, y0, x1, y1))).reshape(-1, 3)]
    ring = []
    for bx in ((x0 - pad, y0 - pad, x1 + pad, y0), (x0 - pad, y1, x1 + pad, y1 + pad), (x0 - pad, y0, x0, y1), (x1, y0, x1 + pad, y1)):
        bx = (max(0, bx[0]), max(0, bx[1]), min(W, bx[2]), min(H, bx[3]))
        if bx[2] > bx[0] and bx[3] > bx[1]:
            ring += [rel_lum(p) for p in np.asarray(im.crop(bx)).reshape(-1, 3)]
    if not ring:
        return None
    ring.sort()
    inner.sort()
    bg = ring[len(ring) // 2]
    lo, hi = inner[int(0.02 * (len(inner) - 1))], inner[int(0.98 * (len(inner) - 1))]
    fg = hi if abs(hi - bg) >= abs(lo - bg) else lo
    a, b = max(fg, bg), min(fg, bg)
    return float((a + 0.05) / (b + 0.05))


def findings(im, stats: dict, audit: dict, W: int, H: int) -> list:
    """The findings for one sampled frame (each {check, severity, detail}); ``audit`` is the scene's __audit() at this t, or empty."""
    validate_audit(audit, require_arrays=False)
    f = []
    if stats["detail_share"] < EMPTY:
        f.append({"check": "empty", "severity": "fail", "detail": f"detail share {stats['detail_share'] * 100:.4f}% (< 0.01%): nothing is visible"})
    elif stats["detail_share"] < SPARSE:
        f.append({"check": "sparse", "severity": "warn", "detail": f"detail share {stats['detail_share'] * 100:.3f}% (< 0.1%): almost nothing is visible (a weak poster frame)"})
    sx0, sy0, sx1, sy1 = 0.05 * W, 0.05 * H, 0.95 * W, 0.95 * H
    text, marks = audit.get("text") or [], audit.get("marks") or []
    for t in text:
        x0, y0, x1, y1 = t["box"]
        if x0 < sx0 or y0 < sy0 or x1 > sx1 or y1 > sy1:
            f.append({"check": "crop", "severity": "fail", "detail": f"text outside title-safe: {t['text']!r} box {t['box']}"})
        if t["font_px"] < MIN_TEXT_PX:
            f.append({"check": "legibility", "severity": "fail", "detail": f"text under {MIN_TEXT_PX} px: {t['text']!r} ({t['font_px']} px)"})
        if t["opacity"] >= 0.95:
            c = text_contrast(im, t["box"])
            t["contrast_measured"] = round(c, 2) if c is not None else None
            need = 3.0 if t["font_px"] >= 24 else 4.5
            if c is not None and c < need:
                f.append({"check": "legibility", "severity": "fail", "detail": f"contrast {c:.6f} < {need}: {t['text']!r}"})
    for m in marks:
        x0, y0, x1, y1 = m["box"]
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            f.append({"check": "crop", "severity": "fail", "detail": f"{m['sel']} cut by the frame edge: box {m['box']}"})
    # overlap: visible text over a visible card or the figure (the spike's rule, its tag-on-card exemption included)
    for t in text:
        for m in marks:
            if m["sel"] in ("figure",) or m["sel"].startswith("card"):
                a, b = t["box"], m["box"]
                ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
                iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
                if ix * iy > 0 and not (t["sel"] == ".card .tag"):
                    f.append({"check": "overlap", "severity": "fail", "detail": f"{t['text']!r} overlaps {m['sel']} by {int(ix)}x{int(iy)} px"})
    return f


TILE_LONG_EDGE = 640


def tile_size(width: int, height: int, long_edge: int = TILE_LONG_EDGE) -> tuple:
    """A contact-sheet tile with the frame's own aspect, its long edge ``long_edge`` (16:9 stays 640x360; 9:16 is 360x640)."""
    if width >= height:
        return long_edge, max(1, int(round(long_edge * height / width)))
    return max(1, int(round(long_edge * width / height))), long_edge


def contact_sheet(samples_dir: Path, out_png: Path, tile=None, cols=3, hashes=None) -> int:
    """The sampled frames on one labelled sheet (frame, t, finding count per tile). Returns the tile count. The tile keeps the frames'
    aspect unless ``tile`` is given (a vertical render squashed into 16:9 tiles cannot be judged by eye)."""
    files = sorted(Path(samples_dir).glob("f*.png"))
    if tile is None:
        with Image.open(files[0]) if files else Image.new("RGB", (16, 9)) as first:
            tile = tile_size(*first.size)
    tw, th = tile
    rows = max(1, (len(files) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 28)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for k, f in enumerate(files):
        meta = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
        x, y = (k % cols) * tw, (k // cols) * (th + 28)
        sheet.paste(Image.open(f).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y + 28))
        d.text((x + 6, y + 6), f"{f.name}  t={meta['t']:.3f}s  findings={len(meta['findings'])}", fill=(255, 220, 120))
    data = io.BytesIO()
    sheet.save(data, format="PNG")
    png = data.getvalue()
    if hashes is not None:
        hashes["contact"] = hashlib.sha256(png).hexdigest()
    Path(out_png).write_bytes(png)
    return len(files)
