# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The recorded orthographic cameras of anim_reference_render and the projection that reuses them: later steps (anim_check, the silhouette refinement) project
with the SAME camera the reference was rendered with. World axes are Blender's (X right, Y forward-into-the-front-view, Z up): the character faces -Y, so the
front camera sits at -Y and the side camera at +X, where the character faces LEFT. Numpy only."""

import numpy as np

MARGIN = 0.06                    # of the figure height, each side
VIEWS = {"front": {"right": (1.0, 0.0, 0.0), "up": (0.0, 0.0, 1.0), "toward": (0.0, -1.0, 0.0)},
         "side": {"right": (0.0, 1.0, 0.0), "up": (0.0, 0.0, 1.0), "toward": (1.0, 0.0, 0.0)}}


class RefError(ValueError):
    pass


def parse_size(size) -> tuple:
    if isinstance(size, str):
        try:
            w, h = (int(x) for x in size.lower().split("x"))
        except ValueError:
            raise RefError(f"size is WIDTHxHEIGHT, not {size!r}")
    else:
        w, h = (int(x) for x in size)
    if not (16 <= w <= 4096 and 16 <= h <= 4096):
        raise RefError("size must be between 16 and 4096 px per side")
    return w, h


def camera_record(view, center, height_m, size, ortho_scale=None, distance=10.0) -> dict:
    if view not in VIEWS:
        raise RefError("view is front or side")
    if height_m <= 0:
        raise RefError("the figure has no height")
    w, h = parse_size(size)
    scale = float(ortho_scale) if ortho_scale else height_m * (1.0 + 2 * MARGIN)         # fit-to-height with a 6 % margin each side
    if scale <= 0:
        raise RefError("ortho_scale must be positive")
    v = VIEWS[view]
    center = np.asarray(center, float)
    loc = center + np.asarray(v["toward"]) * distance
    return {"type": "ORTHO", "view": view, "size": [w, h], "ortho_scale": round(scale, 9), "px_per_m": round(max(w, h) / scale, 9),
            "center": [round(float(c), 9) for c in center], "right": list(v["right"]), "up": list(v["up"]), "location": [round(float(c), 9) for c in loc], "height_m": round(float(height_m), 9)}


def project(points, cam) -> np.ndarray:
    """World points (n, 3) to pixel (u, v), v down, through the recorded orthographic camera."""
    p = np.asarray(points, float) - np.asarray(cam["center"], float)
    w, h = cam["size"]
    u = w / 2 + (p @ np.asarray(cam["right"])) * cam["px_per_m"]
    v = h / 2 - (p @ np.asarray(cam["up"])) * cam["px_per_m"]
    return np.stack([u, v], -1)


def frame_check(bbox_min, bbox_max, cam) -> dict:
    """Is the whole figure inside the frame? Every bounding-box corner is projected."""
    lo, hi = np.asarray(bbox_min, float), np.asarray(bbox_max, float)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    uv = project(corners, cam)
    w, h = cam["size"]
    inside = bool((uv[:, 0] >= 0).all() and (uv[:, 0] <= w).all() and (uv[:, 1] >= 0).all() and (uv[:, 1] <= h).all())
    top, bottom = float(uv[:, 1].min()), float(uv[:, 1].max())
    return {"inside": inside, "top_px": top, "bottom_px": bottom, "margin_px": min(top, h - bottom, float(uv[:, 0].min()), w - float(uv[:, 0].max()))}


def raster_mask(verts, tris, cam) -> np.ndarray:
    """The silhouette of a triangle mesh through the recorded camera: a pixel is set when its CENTRE lies inside a triangle (the rule a renderer uses; no anti-aliasing)."""
    w, h = cam["size"]
    uv = project(verts, cam)
    mask = np.zeros((h, w), bool)
    for t in tris:
        a, b, c = uv[t[0]], uv[t[1]], uv[t[2]]
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0]) - 0.5))), int(min(w - 1, np.ceil(max(a[0], b[0], c[0]) - 0.5)))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1]) - 0.5))), int(min(h - 1, np.ceil(max(a[1], b[1], c[1]) - 0.5)))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        inside = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return mask


def iou(a, b) -> float:
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    u = (a | b).sum()
    return 1.0 if u == 0 else float((a & b).sum() / u)


def perturbed(cam, ortho_scale_factor=1.0) -> dict:
    out = dict(cam)
    out["ortho_scale"] = cam["ortho_scale"] * ortho_scale_factor
    out["px_per_m"] = cam["px_per_m"] / ortho_scale_factor
    return out
