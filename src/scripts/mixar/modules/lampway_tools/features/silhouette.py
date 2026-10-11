# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""silhouette_compare: render two meshes (or a mesh and a plate) from the SAME cameras and report silhouette IoU, area ratio, centroid shift and contact-landmark drift per view,
gating "reject drift that changes identity or side" (specs/wiki/silhouette_compare.md). The camera is fixed by the approved source ``a`` (orthographic, Workbench, transparent
film, subject-height framing like render.py), so a candidate that moved or scaled shows it; a mirrored candidate fails the view that sees the mirror, not the one that does not.
A plate image is compared after putting both masks at one subject height with their aspect kept (canon 10: never cropped and stretched), because a plate carries no camera."""

from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from .. import canon_geom as G
from . import render as R

VIEWS = ("Front", "Back", "Left", "Right")


def _render_mask(ob, camera_from, view, size, tmp, shaded=False):
    """The alpha mask (size x size bool) of ``ob`` seen by the camera framed on ``camera_from``; with ``shaded`` also its studio-lit luminance (0..1) for the interior difference."""
    lo, hi = R.bbox_world(camera_from)
    center = (lo + hi) / 2
    dim = hi - lo
    ext = max(dim.x, dim.y, dim.z) * 1.15
    sc = bpy.data.scenes.new("lw_cmp")
    cam_data = bpy.data.cameras.new("lw_cmp_cam")
    cam_data.type, cam_data.ortho_scale = "ORTHO", ext
    cam = bpy.data.objects.new("lw_cmp_cam", cam_data)
    target = bpy.data.objects.new("lw_cmp_target", None)
    target.location = center
    try:
        for o in (ob, cam, target):
            sc.collection.objects.link(o)
        cam.location = center + Vector(R.TO_CAMERA[view]) * (ext * 2 + dim.length)
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
        sc.camera = cam
        r = sc.render
        r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.film_transparent = "BLENDER_WORKBENCH", size, size, 100, True
        r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
        sc.display.shading.light, sc.display.shading.color_type = ("STUDIO" if shaded else "FLAT"), "SINGLE"
        sc.display.render_aa = "OFF"
        r.filepath = str(tmp)
        bpy.ops.render.render(write_still=True, scene=sc.name)
    finally:
        sc.collection.objects.unlink(ob) if ob.name in sc.collection.objects else None
        for o in (cam, target):
            bpy.data.objects.remove(o)
        bpy.data.scenes.remove(sc)
        bpy.data.cameras.remove(cam_data)
    from PIL import Image
    px = np.asarray(Image.open(tmp).convert("RGBA"))
    if shaded:
        return px[..., 3] > 8, px[..., :3].astype(float).mean(axis=2) / 255.0
    return px[..., 3] > 8


def _image_mask(path, size=None):
    """Plate mask; native dimensions when size is None, border-ring key per canon 10 B.6."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)
    if a[..., 3].min() < 255:
        m = a[..., 3] > 127
    else:
        rgb = a[..., :3].astype(float)
        ring = np.zeros(a.shape[:2], bool)
        ring[:8] = ring[-8:] = True
        ring[:, :8] = ring[:, -8:] = True
        if rgb[ring].std(axis=0).max() > 12:
            raise C.FeatureError("the plate needs an alpha or a flat background (see plate_pick)")
        bg = np.median(rgb[ring], axis=0)
        delta = np.abs(rgb - bg).max(-1)
        tolerance = float(np.quantile(delta[ring], .99))
        m = delta > tolerance
    if size is None:
        return m
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((size, size))) > 127


def _fit_pair(ma, mb, size):
    """Both masks on one canvas at one subject height, aspect kept (canon 10, canon_geom.fit_masks_true_aspect): a plate carries no
    camera, but cropping each mask to its own box and stretching it square makes a 2:1 and a 1:1 silhouette read IoU 1.0 (golden C11)."""
    return G.fit_masks_true_aspect(ma, mb, size)


def _iou(a, b):
    return float((a & b).sum() / max((a | b).sum(), 1))


def _centroid(m):
    ys, xs = np.nonzero(m)
    return np.array([xs.mean(), ys.mean()]) if len(ys) else np.zeros(2)


def _drift(a, b, landmarks):
    """3D distance from each landmark (a point on ``a``, world space) to the nearest surface point of ``b``."""
    tree = BVHTree.FromObject(b, bpy.context.evaluated_depsgraph_get())
    out = []
    for lm in landmarks:
        p = Vector(lm["point"])
        loc = tree.find_nearest(p)[0]
        out.append({"name": lm["name"], "d": round(float((loc - p).length), 6)})
    return out


def run(a, b, root, piece="", views=None, size=512, min_iou=0.9, landmarks=None, interior=False):
    views = list(views or VIEWS)
    if any(v not in VIEWS for v in views):
        raise C.FeatureError(f"views are {', '.join(VIEWS)}")
    if not 128 <= int(size) <= 2048:
        raise C.FeatureError("size is 128..2048")
    size = int(size)
    oa = C.need_object(a)
    image = isinstance(b, str) and (Path(b).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    ob = None if image else C.need_object(b)
    if ob is oa:
        raise C.FeatureError("a and b are the same object: compare the approved source with the candidate")
    for o in [x for x in (oa, ob) if x is not None]:
        if max(abs(s - 1.0) for s in o.scale) > 1e-4:
            raise C.FeatureError(f"scale not applied on {o.name}: apply it first")
    outdir = Path(root) / (piece or oa.name) / "compare"
    outdir.mkdir(parents=True, exist_ok=True)
    rows, images = [], []
    from PIL import Image
    tmp = outdir / ".tmp.png"
    for v in views:
        want_interior = bool(interior) and not image
        if want_interior:
            ma, la = _render_mask(oa, oa, v, size, tmp, shaded=True)
            mb, lb = _render_mask(ob, oa, v, size, tmp, shaded=True)
        else:
            ma = _render_mask(oa, oa, v, size, tmp)
        if image:
            mb = _image_mask(b, size)
            ma, mb = _fit_pair(ma, mb, size)
        elif not want_interior:
            mb = _render_mask(ob, oa, v, size, tmp)
        row = {"view": v, "iou": round(_iou(ma, mb), 4), "area_ratio": round(float(mb.sum() / max(ma.sum(), 1)), 4),
               "centroid_shift_frac": round(float(np.linalg.norm(_centroid(ma) - _centroid(mb)) / size), 4)}
        if want_interior:
            from ..pipeline import interior_diff as ID
            row.update(ID.interior_diff(la, ma, lb, mb))
        if landmarks and ob is not None:
            row["landmark_drift_m"] = _drift(oa, ob, landmarks)
        rows.append(row)
        sbs = np.zeros((size, size * 2, 3), np.uint8)
        sbs[:, :size, 0], sbs[:, size:, 1] = ma * 255, mb * 255
        p = outdir / f"{v}_{oa.name}_vs_{ob.name if ob else Path(b).stem}.png"
        Image.fromarray(sbs).save(p)
        images.append(str(p))
    tmp.unlink(missing_ok=True)
    worst = min(r["iou"] for r in rows)
    return {"views": rows, "worst_iou": worst, "min_iou": float(min_iou), "pass": worst >= float(min_iou), "images": images}
