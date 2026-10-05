# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Texture Gen, AI Render and local texture repair on proven projection code.

* ``project_views``: cardinal-view images are projected into the UV atlas. Every texel of the atlas is located on the mesh (UV
  triangle rasterisation, interpolated position and normal); each view contributes with weight max(0, n . toCamera)^p, optionally
  zeroed where a ray toward the camera hits the mesh first (occlusion); the atlas is the weighted mean, dilated into the gutters.
  Framing convention (render.py): the subject fills the image height and is centred.
* ``texture_gen``: clay render of each view -> the IMAGE SLOT (``generate_image``, the server's image_gen) paints it -> projection.
* ``ai_render``: a clay render handed to the image slot; the result is an image for look development and changes nothing in the scene.
* ``repair_texture``: a patch image and a mask in a view's framing are blended into an existing atlas where the mask says so
  (the surface must face that view); the original file is never overwritten.
"""

import math
import os

import bpy
import numpy as np

from . import common as C
from . import jobs_client
from . import render as R

generate_image = jobs_client.generate_image          # the slot; tests and other engines replace this name


def _texel_samples(ob, size):
    """For every atlas texel under a UV triangle: world position, world normal, validity mask. (size x size)"""
    me = ob.data
    if not me.uv_layers:
        raise C.FeatureError(f"{ob.name!r} has no UV layer: unwrap it first (lampway_uv_unwrap)")
    me.calc_loop_triangles()
    me.calc_normals_split() if hasattr(me, "calc_normals_split") else None
    uv = np.empty(len(me.loops) * 2, dtype=np.float64)
    me.uv_layers.active.uv.foreach_get("vector", uv)
    uv = uv.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mat = np.array(ob.matrix_world)
    wpos = (mat[:3, :3] @ co.T).T + mat[:3, 3]
    nrm = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    wnrm = (np.linalg.inv(mat[:3, :3]).T @ nrm.T).T
    wnrm /= np.maximum(np.linalg.norm(wnrm, axis=1, keepdims=True), 1e-12)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", tris)
    tris = tris.reshape(-1, 3)
    pos = np.zeros((size, size, 3))
    nor = np.zeros((size, size, 3))
    valid = np.zeros((size, size), dtype=bool)
    for t in tris:
        q = uv[t] * size
        x0, x1 = int(max(0, math.floor(q[:, 0].min()))), int(min(size - 1, math.ceil(q[:, 0].max())))
        y0, y1 = int(max(0, math.floor(q[:, 1].min()))), int(min(size - 1, math.ceil(q[:, 1].max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (q[1, 1] - q[2, 1]) * (q[0, 0] - q[2, 0]) + (q[2, 0] - q[1, 0]) * (q[0, 1] - q[2, 1])
        if abs(d) < 1e-12:
            continue
        w0 = ((q[1, 1] - q[2, 1]) * (gx - q[2, 0]) + (q[2, 0] - q[1, 0]) * (gy - q[2, 1])) / d
        w1 = ((q[2, 1] - q[0, 1]) * (gx - q[2, 0]) + (q[0, 0] - q[2, 0]) * (gy - q[2, 1])) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        vi = lv[t]
        p = w0[..., None] * wpos[vi[0]] + w1[..., None] * wpos[vi[1]] + w2[..., None] * wpos[vi[2]]
        n = w0[..., None] * wnrm[vi[0]] + w1[..., None] * wnrm[vi[1]] + w2[..., None] * wnrm[vi[2]]
        sub = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        pos[sub][inside] = p[inside]
        nor[sub][inside] = n[inside]
        valid[sub] |= inside
    nor /= np.maximum(np.linalg.norm(nor, axis=2, keepdims=True), 1e-12)
    # UV space has v up; image rows go down
    return pos[::-1], nor[::-1], valid[::-1]


def _subject(path, crop=True):
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float64)
    alpha = a[..., 3] / 255.0
    if (alpha < 0.98).any():
        mask = alpha > 0.5
    else:
        bg = a[0, 0, :3]
        mask = np.abs(a[..., :3] - bg).sum(axis=2) > 40
    if not mask.any():
        mask = np.ones(mask.shape, dtype=bool)                  # a flat image: the whole frame is the subject
        box = (0, 0, mask.shape[1], mask.shape[0])
    else:
        ys, xs = np.nonzero(mask)
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    if crop:
        x0, y0, x1, y1 = box
        return a[y0:y1, x0:x1, :3] / 255.0, mask[y0:y1, x0:x1]
    return a[..., :3] / 255.0, mask


def _view_coords(pos, view, lo, hi):
    """Image coordinates (column, row) in [0, 1] for world points seen from ``view`` (the subject's height fills 0..1)."""
    height = max(hi[2] - lo[2], 1e-9)
    z = (pos[..., 2] - lo[2]) / height
    centre = {"x": (lo[0] + hi[0]) / 2, "y": (lo[1] + hi[1]) / 2}
    axis, sign = {"Front": ("x", 1.0), "Back": ("x", -1.0), "Right": ("y", 1.0), "Left": ("y", -1.0)}[view]
    h = sign * (pos[..., 0 if axis == "x" else 1] - centre[axis]) / height
    return h, z                                                  # h in subject-height units, z in 0..1


def _sample_image(img, h, z, aspect_w_over_h):
    ih, iw = img.shape[:2]
    col = np.rint((0.5 + h / aspect_w_over_h) * iw - 0.5).astype(int)
    row = np.rint((1.0 - z) * ih - 0.5).astype(int)
    ok = (col >= 0) & (col < iw) & (row >= 0) & (row < ih)
    out = np.zeros(h.shape + (img.shape[2],) if img.ndim == 3 else h.shape)
    out[ok] = img[row[ok], col[ok]]
    return out, ok


def _occluded(ob, pos, nor, valid, to_cam, want):
    """Texels (world ``pos``/``nor``) whose ray toward the camera hits the mesh first. BVHTree.FromObject is in OBJECT space, so the
    rays are moved there."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(ob, dg)
    inv = ob.matrix_world.inverted()
    d_local = (inv.to_3x3() @ Vector(to_cam)).normalized()
    eps = 1e-3 * max(ob.dimensions)
    hidden = np.zeros(valid.shape, dtype=bool)
    for y, x in zip(*np.nonzero(valid & want)):
        origin = inv @ (Vector(pos[y, x]) + Vector(nor[y, x]) * eps)
        if tree.ray_cast(origin, d_local)[0] is not None:
            hidden[y, x] = True
    return hidden


def _dilate(img, filled, rounds):
    out, ok = img.copy(), filled.copy()
    for _ in range(rounds):
        if ok.all():
            break
        pad_i, pad_o = np.pad(out, ((1, 1), (1, 1), (0, 0))), np.pad(ok, 1)
        acc, cnt = np.zeros_like(out), np.zeros(ok.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                sl = (slice(1 + dy, 1 + dy + ok.shape[0]), slice(1 + dx, 1 + dx + ok.shape[1]))
                m = pad_o[sl]
                acc += pad_i[sl] * m[..., None]
                cnt += m
        grow = (~ok) & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow][..., None]
        ok = ok | grow
    return out, ok


def _apply_material(ob, atlas_path, name):
    img = bpy.data.images.load(atlas_path, check_existing=False)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    t = mat.node_tree
    bsdf = next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED")
    tex = t.nodes.new("ShaderNodeTexImage")
    tex.image = img
    t.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return mat


def project_views(object, views, size=1024, out="", occlusion=True, power=4.0, apply=True):
    ob = C.need_object(object)
    bad = [v for v in views if v not in R.TO_CAMERA]
    if bad:
        raise C.FeatureError(f"unknown view(s) {bad}; the views are {', '.join(R.TO_CAMERA)}")
    size = int(size)
    if not 16 <= size <= 4096:
        raise C.FeatureError("size must be between 16 and 4096")
    pos, nor, valid = _texel_samples(ob, size)
    lo, hi = R.bbox_world(ob)
    acc = np.zeros((size, size, 3))
    wsum = np.zeros((size, size))
    view_texels, view_share = {}, {}
    for view, path in views.items():
        img, mask = _subject(path)
        to_cam = np.array(R.TO_CAMERA[view])
        facing = np.clip((nor * to_cam).sum(axis=2), 0, None) ** float(power)
        h, z = _view_coords(pos, view, lo, hi)
        aspect = img.shape[1] / img.shape[0]
        col, ok = _sample_image(img, h, z, aspect)
        inside_subject, _ = _sample_image(mask.astype(np.float64), h, z, aspect)
        w = np.where(valid & ok & (inside_subject > 0.5), facing, 0.0)
        if occlusion:
            w = np.where(_occluded(ob, pos, nor, valid, tuple(to_cam), w > 0), 0.0, w)
        acc += col * w[..., None]
        wsum += w
        view_texels[view] = int((w > 1e-6).sum())
    covered = valid & (wsum > 1e-6)
    atlas = np.where(covered[..., None], acc / np.maximum(wsum, 1e-9)[..., None], 0.5)
    for v in views:
        view_share[v] = round(view_texels[v] / max(1, int(valid.sum())), 4)
    filled, fill_ok = _dilate(atlas, covered, 24)
    filled = np.where(fill_ok[..., None], filled, 0.5)
    from PIL import Image
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    Image.fromarray((np.clip(filled, 0, 1) * 255).round().astype(np.uint8)).save(out)
    mat = _apply_material(ob, out, f"{ob.name}_proj") if apply else None
    return {"object": ob.name, "atlas": out, "material": mat.name if mat else None,
            "report": {"coverage": round(float(covered.sum() / max(1, valid.sum())), 4), "valid_texels": int(valid.sum()),
                       "view_texels": view_texels, "view_share": view_share, "occlusion": bool(occlusion), "size": size,
                       "note": "no occlusion test on a concave mesh seen head-on would paint hidden surfaces: leave occlusion on"}}


def texture_gen(object, prompt, out_dir, views=("Front", "Back"), size=1024, engine="algorithmic", clay_size=768, occlusion=True):
    if engine != "algorithmic":
        return C.studio_slot("texture", engine)
    ob = C.need_object(object)
    os.makedirs(out_dir, exist_ok=True)
    painted = {}
    for view in views:
        clay = os.path.join(out_dir, f"clay_{view}.png")
        R.render_view(ob, view, clay_size, clay)
        full = (f"{prompt}. Paint ONLY the flat albedo colour of this object as seen from its {view.lower()}: no lighting, no shadows, "
                "no background, keep the silhouette and every shape exactly as in the reference image.")
        with open(clay, "rb") as fh:
            images = generate_image(full, fh.read(), 1)
        target = os.path.join(out_dir, f"gen_{view}.png")
        with open(target, "wb") as fh:
            fh.write(images[0])
        painted[view] = target
    res = project_views(ob.name, painted, size, os.path.join(out_dir, "atlas.png"), occlusion)
    res["views"] = painted
    res["slot"] = "image_gen (the server's image model)"
    return res


def ai_render(object, prompt, view="Front", out="", size=768):
    ob = C.need_object(object)
    clay = out.rsplit(".", 1)[0] + "_clay.png"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    R.render_view(ob, view, size, clay)
    with open(clay, "rb") as fh:
        images = generate_image(f"{prompt}. Keep the composition and the silhouette of the reference image.", fh.read(), 1)
    with open(out, "wb") as fh:
        fh.write(images[0])
    img = bpy.data.images.load(out, check_existing=False)
    return {"image": out, "blender_image": img.name, "reference": clay, "view": view,
            "note": "AI Render gives an image for look development; it does not change the scene's materials, lights or camera"}


def repair_texture(object, texture, view, patch, mask, out, feather=2, power=2.0, min_facing=0.25):
    from PIL import Image, ImageFilter
    ob = C.need_object(object)
    base = Image.open(texture).convert("RGB")
    size = base.size[0]
    pos, nor, valid = _texel_samples(ob, size)
    if base.size[1] != size:
        raise C.FeatureError("the texture must be square")
    lo, hi = R.bbox_world(ob)
    patch_img, _m = _subject(patch, crop=False)
    m_img = Image.open(mask).convert("L")
    if feather:
        m_img = m_img.filter(ImageFilter.GaussianBlur(float(feather)))
    m_arr = np.asarray(m_img).astype(np.float64) / 255.0
    to_cam = np.array(R.TO_CAMERA[view])
    facing = (nor * to_cam).sum(axis=2)
    h, z = _view_coords(pos, view, lo, hi)
    aspect = patch_img.shape[1] / patch_img.shape[0]
    col, ok = _sample_image(patch_img, h, z, aspect)
    m_s, ok2 = _sample_image(m_arr, h, z, m_arr.shape[1] / m_arr.shape[0])
    weight = np.where(valid & ok & ok2 & (facing > min_facing), m_s * np.clip(facing, 0, 1) ** float(power), 0.0)
    weight = np.clip(weight, 0, 1)
    b = np.asarray(base).astype(np.float64) / 255.0
    outp = b * (1 - weight[..., None]) + col * weight[..., None]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    Image.fromarray((np.clip(outp, 0, 1) * 255).round().astype(np.uint8)).save(out)
    return {"texture": out, "source": texture, "report": {"changed_fraction": round(float((weight > 0.5).mean()), 4),
            "valid_texels": int(valid.sum()), "view": view}}
