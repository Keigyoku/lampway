"""The pure image previews (specs/asset_library/asset_render.md section 6): image and video thumbnails, the UV overlay, the map sheet and the contact sheet.

Pillow and numpy only (ffmpeg for a video frame). Nothing here opens a window or a Blender; every product is a pure function of its inputs."""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .store import LibraryError

LABEL_H = 16
SHEET_COLS, SHEET_ROWS = 4, 3
NORMAL_CHANNELS = {"normal": None, "normal_gl": "GL", "normal_dx": "DX"}
BACKGROUND = (128, 128, 128)


def _jpeg(im, quality=90) -> bytes:
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=quality, optimize=False, subsampling=0)
    return b.getvalue()


def _png(im) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def _fit(im, size):
    """``im`` scaled to fit ``size`` x ``size`` (aspect kept), alpha flattened onto the neutral grey."""
    from PIL import Image
    im = im.copy()
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, BACKGROUND + (255,))
        im = Image.alpha_composite(bg, im)
    return im.convert("RGB")


def image_thumb(path, size: int) -> bytes:
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        return _jpeg(_fit(im, size))


def video_thumb(path, size: int, nice: int = 15) -> bytes:
    """A representative frame (ffmpeg's ``thumbnail`` filter over the first 50 frames), fitted to ``size``."""
    if not shutil.which("ffmpeg"):
        raise LibraryError("ffmpeg not found on PATH: install it (the server needs ffmpeg + ffprobe)")
    p = subprocess.run(["nice", "-n", str(nice), "ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vf", "thumbnail=50", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=120)
    if p.returncode != 0 or not p.stdout:
        raise LibraryError(f"cannot decode {path}: {p.stderr.decode(errors='replace')[-300:]}")
    from PIL import Image
    with Image.open(io.BytesIO(p.stdout)) as im:
        im.load()
        return _jpeg(_fit(im, size))


# ---- UV overlay ----------------------------------------------------------------------------------------------------------------
def _uv_parts(mesh):
    return [p for p in mesh["parts"] if p.get("uv") is not None and len(p["idx"])]


def uv_loops(mesh) -> list:
    """The boundary loops of every UV island, as (k, 2) arrays of UV points. A boundary edge is used by exactly one triangle; a GLB splits vertices at UV seams, so vertex
    indices are UV-space vertices."""
    loops = []
    for part in _uv_parts(mesh):
        tri = part["idx"]
        e = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
        uniq, count = np.unique(e, axis=0, return_counts=True)
        nxt: dict = {}
        for a, b in uniq[count == 1].tolist():
            nxt.setdefault(a, []).append(b)
            nxt.setdefault(b, []).append(a)
        used = set()
        for start in sorted(nxt):
            for first in nxt[start]:
                if (min(start, first), max(start, first)) in used:
                    continue
                loop, prev, cur = [start], start, first
                used.add((min(start, first), max(start, first)))
                for _ in range(len(nxt) + 1):                       # bounded: a loop cannot be longer than the boundary
                    if cur == start:
                        break
                    loop.append(cur)
                    step = next((n for n in nxt[cur] if (min(cur, n), max(cur, n)) not in used), None)
                    if step is None:
                        break
                    used.add((min(cur, step), max(cur, step)))
                    prev, cur = cur, step
                loops.append(part["uv"][loop])
    return loops


def uv_overlay(mesh, size: int = 1024, base=None) -> bytes:
    """PNG: every UV edge as a thin wire and every island boundary as a heavier line, over the base-colour map (``base``, a path) or a checker."""
    from PIL import Image, ImageDraw
    parts = _uv_parts(mesh)
    if not parts:
        raise LibraryError("no UV set on this mesh: unwrap it first (uv_unwrap), then ask for the overlay again")
    if base:
        with Image.open(base) as im:
            canvas = im.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    else:
        cells = (np.add.outer(np.arange(size) * 8 // size, np.arange(size) * 8 // size) % 2).astype(np.uint8)
        canvas = Image.fromarray(np.repeat((96 + 64 * cells)[:, :, None], 3, 2))
    draw = ImageDraw.Draw(canvas)

    def xy(uv):
        return [(float(u) * size, float(v) * size) for u, v in uv]            # glTF UV: v grows downward, like image rows

    for part in parts:
        for t in part["uv"][part["idx"]]:
            draw.line(xy(list(t) + [t[0]]), fill=(230, 230, 230), width=1)
    for loop in uv_loops(mesh):
        draw.line(xy(list(loop) + [loop[0]]), fill=(255, 170, 0), width=2)
    return _png(canvas)


# ---- sheets ----------------------------------------------------------------------------------------------------------------------
def _font():
    from PIL import ImageFont
    return ImageFont.load_default(size=11)


def map_sheet(maps: list, cell: int = 256) -> dict:
    """One labelled cell per channel, four per row. A normal map is stamped with its convention (GL / DX): a wrong-handed normal is visible, not guessed."""
    from PIL import Image, ImageDraw
    if not maps:
        raise LibraryError("no maps to show: a map sheet needs at least one channel")
    cells = []
    for m in maps:
        ch = m["channel"]
        stamp = None
        if ch in NORMAL_CHANNELS:
            stamp = (m.get("convention") or NORMAL_CHANNELS[ch] or "").upper() or None
            if stamp not in ("GL", "DX"):
                raise LibraryError(f"normal map convention unknown for {Path(m['path']).name}: say GL or DX (OpenGL Y+ or DirectX Y-)")
        cells.append({"channel": ch, "stamp": stamp, "path": str(m["path"])})
    cols = min(SHEET_COLS, len(cells))
    rows = -(-len(cells) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + LABEL_H)), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for i, c in enumerate(cells):
        x, y = (i % cols) * cell, (i // cols) * (cell + LABEL_H)
        with Image.open(c["path"]) as im:
            sheet.paste(im.convert("RGB").resize((cell, cell), Image.Resampling.LANCZOS), (x, y + LABEL_H))
        draw.text((x + 3, y + 2), c["channel"] + (f"  [{c['stamp']}]" if c["stamp"] else ""), fill=(235, 235, 235), font=_font())
    return {"bytes": _jpeg(sheet), "cells": cells}


def contact_sheet(frames: list, cell: int = 256) -> bytes:
    """A 4 x 3 JPEG of twelve frames evenly picked from ``frames`` (paths), row-major."""
    from PIL import Image
    if not frames:
        raise LibraryError("no frames for a contact sheet: render a turntable or a strip first")
    n = SHEET_COLS * SHEET_ROWS
    pick = [frames[int(i * len(frames) / n)] for i in range(n)] if len(frames) >= n else list(frames)
    sheet = Image.new("RGB", (SHEET_COLS * cell, SHEET_ROWS * cell), BACKGROUND)
    for i, f in enumerate(pick):
        with Image.open(f) as im:
            sheet.paste(_fit(im, cell), ((i % SHEET_COLS) * cell, (i // SHEET_COLS) * cell))
    return _jpeg(sheet)
