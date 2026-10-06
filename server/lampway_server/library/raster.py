"""The software preview renderer (specs/asset_library/asset_render.md section 6, engine 1): a numpy z-buffer rasteriser, no GPU, no Blender.

One fixed framing recipe for every mesh so previews compare across assets: a front three-quarter view, a 35 mm lens, framed to the bounding box of the projected surface with a margin,
a neutral grey background and one camera-space light rig (the same light whatever the turntable angle, like a matcap). Flat shading; the base colour is the material's
factor, its embedded base-colour texture (nearest texel) or COLOR_0. Deterministic: the same bytes for the same mesh and recipe."""
from __future__ import annotations

import io
import math

import numpy as np

from . import spaces as SP
from .store import LibraryError

RECIPE = {"version": 1, "azimuth_deg": 35.0, "elevation_deg": 20.0, "focal_mm": 35.0, "sensor_mm": 36.0, "margin": 0.08, "background": [128, 128, 128],
          "clay": [0.8, 0.8, 0.8], "key_light": [-0.45, 0.6, 0.66], "ambient": 0.22, "hemi": 0.18, "key": 0.62, "jpeg_quality": 90}
CHUNK_PIXELS = 2_000_000          # candidate pixels per rasterisation chunk (bounds memory on a dense mesh)
FRAME_POINTS = 30_000             # vertices sampled (a fixed stride) to frame the view


def glb_mesh(src) -> dict:
    """The parts of a GLB plus the flattened triangle soup the rasteriser reads. Zero triangles is a valid answer (an empty mesh is reported, not raised)."""
    parts = SP.glb_parts(src)
    tris = [p["pos"][p["idx"]].astype("float64") for p in parts]
    return {"parts": parts, "tris": np.concatenate(tris) if tris else np.zeros((0, 3, 3)), "tri_part": np.concatenate([np.full(len(t), i) for i, t in enumerate(tris)]) if tris else np.zeros(0, int),
            "tri_local": np.concatenate([np.arange(len(t)) for t in tris]) if tris else np.zeros(0, int), "uv": parts[0]["uv"] if len(parts) == 1 else None}


def _camera(recipe):
    az, el = math.radians(recipe["azimuth_deg"]), math.radians(recipe["elevation_deg"])
    d = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])     # glTF is +Y up, +Z front: the camera sits front-right-above
    f = -d
    right = np.cross(f, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    return d, f, right, up


def _yaw(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _project(p, eye, f, right, up):
    q = p - eye
    z = q @ f
    return np.stack([(q @ right) / z, (q @ up) / z], -1), z


def frame_views(tris: np.ndarray, yaws, recipe=None):
    """The camera and the 2D framing shared by every view in ``yaws`` (radians): the projected bounding-box corners of every view fit the frame minus the margin."""
    recipe = recipe or RECIPE
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    centre, radius = (lo + hi) / 2, max(float(np.linalg.norm(hi - lo)) / 2, 1e-6)
    d, f, right, up = _camera(recipe)
    half = math.atan(recipe["sensor_mm"] / 2 / recipe["focal_mm"])
    eye = centre + d * radius / math.sin(half)
    pts = tris.reshape(-1, 3)
    pts = pts[:: max(1, len(pts) // FRAME_POINTS)] - centre        # the bounding box of the PROJECTED surface: a sphere fills its frame like a cube does
    uv = np.concatenate([_project(pts @ _yaw(a).T + centre, eye, f, right, up)[0] for a in yaws])
    mn, mx = uv.min(0), uv.max(0)
    return {"centre": centre, "eye": eye, "f": f, "right": right, "up": up, "mid": (mn + mx) / 2, "span": max(float((mx - mn).max()), 1e-9)}


def render_mesh(mesh: dict, size: int = 256, yaw: float = 0.0, framing=None, recipe=None):
    """(RGB uint8 image, bool silhouette mask) of the mesh turned by ``yaw`` radians about +Y. ``framing`` (from ``frame_views``) keeps a turntable's frames on one camera."""
    recipe = recipe or RECIPE
    tris = mesh["tris"]
    if not len(tris):
        raise LibraryError("empty mesh: nothing to render")
    fr = framing or frame_views(tris, [yaw], recipe)
    world = (tris - fr["centre"]) @ _yaw(yaw).T + fr["centre"]
    uv, z = _project(world.reshape(-1, 3), fr["eye"], fr["f"], fr["right"], fr["up"])
    s = size * (1 - 2 * recipe["margin"]) / fr["span"]
    px = np.stack([(uv[:, 0] - fr["mid"][0]) * s + size / 2, size / 2 - (uv[:, 1] - fr["mid"][1]) * s], -1).reshape(-1, 3, 2)
    inv_z = (1.0 / np.maximum(z, 1e-9)).reshape(-1, 3)
    best_t, bary = _rasterise(px, inv_z, size)
    mask = best_t >= 0
    img = np.empty((size * size, 3), "float64")
    img[:] = np.asarray(recipe["background"], "float64") / 255.0
    hit = np.nonzero(mask.reshape(-1))[0]
    if hit.size:
        t = best_t.reshape(-1)[hit]
        img[hit] = _base_colour(mesh, t, bary.reshape(-1, 3)[hit], recipe) * _shade(world, fr, recipe)[t][:, None]
    out = np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8).reshape(size, size, 3)
    out[~mask] = recipe["background"]
    return out, mask


def _rasterise(px, inv_z, size):
    """Per pixel: the nearest triangle id (-1 = background) and its barycentric weights. Candidate pixels of each triangle's bounding box are generated in chunks, kept
    where inside the triangle, and resolved by depth with a sort (no Python loop over triangles)."""
    n = size * size
    zbuf, tbuf, bbuf = np.full(n, -np.inf), np.full(n, -1, np.int64), np.zeros((n, 3))
    x0 = np.clip(np.ceil(px[:, :, 0].min(1) - 0.5), 0, size).astype(np.int64)
    x1 = np.clip(np.floor(px[:, :, 0].max(1) - 0.5), -1, size - 1).astype(np.int64)
    y0 = np.clip(np.ceil(px[:, :, 1].min(1) - 0.5), 0, size).astype(np.int64)
    y1 = np.clip(np.floor(px[:, :, 1].max(1) - 0.5), -1, size - 1).astype(np.int64)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    area = (px[:, 1, 0] - px[:, 0, 0]) * (px[:, 2, 1] - px[:, 0, 1]) - (px[:, 2, 0] - px[:, 0, 0]) * (px[:, 1, 1] - px[:, 0, 1])
    live = np.nonzero((w > 0) & (h > 0) & (np.abs(area) > 1e-12))[0]
    cum = np.cumsum((w * h)[live])
    start = 0
    while start < len(live):                                   # every pass advances by at least one triangle
        base = int(cum[start - 1]) if start else 0
        stop = max(start + 1, int(np.searchsorted(cum, base + CHUNK_PIXELS, side="right")))
        ids = live[start:stop]
        start = stop
        cnt = (w * h)[ids]
        t = np.repeat(ids, cnt)
        k = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        x = x0[t] + k % w[t]
        y = y0[t] + k // w[t]
        cx, cy = x + 0.5, y + 0.5
        p = px[t]
        e0 = (p[:, 2, 0] - p[:, 1, 0]) * (cy - p[:, 1, 1]) - (p[:, 2, 1] - p[:, 1, 1]) * (cx - p[:, 1, 0])
        e1 = (p[:, 0, 0] - p[:, 2, 0]) * (cy - p[:, 2, 1]) - (p[:, 0, 1] - p[:, 2, 1]) * (cx - p[:, 2, 0])
        e2 = (p[:, 1, 0] - p[:, 0, 0]) * (cy - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (cx - p[:, 0, 0])
        b = np.stack([e0, e1, e2], -1) / area[t][:, None]
        inside = (b >= 0).all(1)
        if not inside.any():
            continue
        t, b, pix = t[inside], b[inside], (y * size + x)[inside]
        iz = (b * inv_z[t]).sum(1)
        order = np.lexsort((t, -iz, pix))                      # per pixel: nearest first, then the lower triangle id (deterministic ties)
        pix, t, b, iz = pix[order], t[order], b[order], iz[order]
        first = np.concatenate([[True], pix[1:] != pix[:-1]])
        pix, t, b, iz = pix[first], t[first], b[first], iz[first]
        better = iz > zbuf[pix]
        pix, t, b, iz = pix[better], t[better], b[better], iz[better]
        zbuf[pix], tbuf[pix] = iz, t
        # perspective-correct weights: barycentrics in screen space scaled by 1/z and renormalised
        pc = b * inv_z[t]
        bbuf[pix] = pc / pc.sum(1, keepdims=True)
    return tbuf.reshape(size, size), bbuf.reshape(size, size, 3)


def _shade(world, fr, recipe):
    n = np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    to_eye = fr["eye"] - world.mean(1)
    n[(n * to_eye).sum(1) < 0] *= -1                          # two-sided: a normal always faces the camera
    nc = np.stack([n @ fr["right"], n @ fr["up"], -(n @ fr["f"])], -1)
    key = np.asarray(recipe["key_light"], "float64")
    key /= np.linalg.norm(key)
    return recipe["ambient"] + recipe["hemi"] * (0.5 + 0.5 * nc[:, 1]) + recipe["key"] * np.maximum(nc @ key, 0)


def _base_colour(mesh, t, bary, recipe):
    out = np.tile(np.asarray(recipe["clay"], "float64"), (len(t), 1))
    part_of, local = mesh["tri_part"][t], mesh["tri_local"][t]
    for pi, part in enumerate(mesh["parts"]):
        sel = np.nonzero(part_of == pi)[0]
        if not sel.size:
            continue
        corners = part["idx"][local[sel]]
        col = np.tile(part["color"] if part["color"] is not None else np.asarray(recipe["clay"]), (sel.size, 1)).astype("float64")
        if part["texture"] is not None and part["uv"] is not None:
            uv = (part["uv"][corners] * bary[sel][:, :, None]).sum(1)
            tex = np.asarray(part["texture"], "float64") / 255.0
            th, tw = tex.shape[:2]
            col = tex[(np.floor(np.mod(uv[:, 1], 1.0) * th).astype(int)).clip(0, th - 1), (np.floor(np.mod(uv[:, 0], 1.0) * tw).astype(int)).clip(0, tw - 1)] * (col if part["color"] is not None else 1.0)
        elif part["vcolor"] is not None:
            col = col * (part["vcolor"][corners] * bary[sel][:, :, None]).sum(1)
        out[sel] = col
    return out


def encode_jpeg(img: np.ndarray, quality=None) -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(img).save(b, "JPEG", quality=int(quality or RECIPE["jpeg_quality"]), optimize=False, subsampling=0)
    return b.getvalue()
