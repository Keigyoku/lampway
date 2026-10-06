# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Zones of a mesh, and the zone sheet (specs/wiki/zone_sheet.md).

A zone is a set of faces named one way: ``material_slot`` (each slot in use, by its material's name), ``part`` (the int face attribute ``part``; with a recipe the
part names), ``segment`` (the int face attribute ``segment``) or ``vertex_group`` (the faces whose vertices all belong to a group). Zones are numbered from 1 in
that order; the numbers are what a user answers with and what mesh_region_extract and mesh_local_edit take (``zone`` + ``by``).

zone_sheet renders a throw-away copy with one flat palette colour per zone from the clay camera (render.render_view, anti-aliasing off), every pixel snapped to
its zone colour, the zone's number written at its visible centroid, the views side by side on one PNG, and the legend beside it as JSON."""

import json
import os
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import render as R
from .condition_passes import palette
from .material_id import _lin, _snap

BYS = ("material_slot", "part", "segment", "vertex_group")
UNZONED = (110, 110, 110)


def _face_attr(ob, name):
    attr = ob.data.attributes.get(name)
    if attr is None or attr.domain != "FACE" or attr.data_type != "INT":
        return None
    v = np.empty(len(ob.data.polygons), dtype=np.int64)
    attr.data.foreach_get("value", v)
    return v


def zones(ob, by="material_slot", recipe="") -> list:
    """[(name, [face indices])] in zone order (zone number = position + 1)."""
    if by not in BYS:
        raise C.FeatureError("by is " + " | ".join(BYS))
    polys = ob.data.polygons
    out = []
    if by == "material_slot":
        idx = np.empty(len(polys), dtype=np.int64)
        polys.foreach_get("material_index", idx)
        for i, slot in enumerate(ob.material_slots):
            fs = np.nonzero(idx == i)[0].tolist()
            if fs:
                out.append((slot.material.name if slot.material else f"slot {i}", fs))
    elif by in ("part", "segment"):
        v = _face_attr(ob, by)
        if v is None:
            raise C.FeatureError(f"{ob.name} has no int face attribute '{by}': " + ("run segment_mesh first" if by == "segment" else "give the parts (transfer_parts / segment_mesh labels)"))
        names = list((json.loads(Path(recipe).read_text(encoding="utf-8")).get("parts") or {})) if recipe else []
        for k in sorted(set(v.tolist())):
            out.append((names[k] if 0 <= k < len(names) else f"{by} {k}", np.nonzero(v == k)[0].tolist()))
    else:
        member = {g.index: set() for g in ob.vertex_groups}
        for vtx in ob.data.vertices:
            for e in vtx.groups:
                if e.weight > 0 and e.group in member:
                    member[e.group].add(vtx.index)
        for g in ob.vertex_groups:
            fs = [p.index for p in polys if p.vertices and all(x in member[g.index] for x in p.vertices)]
            if fs:
                out.append((g.name, fs))
    return out


def zone_faces(ob, by, number, recipe="") -> tuple:
    zs = zones(ob, by, recipe)
    n = int(number)
    if not 1 <= n <= len(zs):
        raise C.FeatureError(f"no zone {number} by {by}: the zones are 1..{len(zs)} (zone_sheet shows them)")
    return zs[n - 1]


def _label(img, xy, text):
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=max(12, img.size[1] // 18))
    except TypeError:                                   # an old Pillow without sized default fonts
        font = ImageFont.load_default()
    x, y = xy
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            d.text((x + dx, y + dy), text, fill=(0, 0, 0, 255), font=font, anchor="mm")
    d.text((x, y), text, fill=(255, 255, 255, 255), font=font, anchor="mm")


def zone_sheet(object, by="material_slot", views=None, size=768, out="zones/sheet.png", recipe=""):
    from PIL import Image
    ob = C.need_object(object)
    views = list(views or ["Front", "Back", "Left", "Right"])
    bad = [v for v in views if v not in R.TO_CAMERA]
    if bad:
        raise C.FeatureError(f"unknown view {bad[0]!r}: the views are {', '.join(R.TO_CAMERA)}")
    size = int(size)
    if not 256 <= size <= 2048:
        raise C.FeatureError("size is 256..2048")
    zs = zones(ob, by, recipe)
    if len(zs) < 2:
        raise C.FeatureError(f"{ob.name} has {len(zs)} zone(s) by {by}: a sheet needs at least two zones (try another `by`)")
    pal = palette(len(zs))
    face_zone = np.full(len(ob.data.polygons), len(zs), dtype=np.int32)          # the last slot: faces in no zone
    for k, (_n, fs) in enumerate(zs):
        face_zone[fs] = k
    me = ob.data.copy()
    tmp = bpy.data.objects.new(ob.name + "_zones_tmp", me)
    tmp.matrix_world = ob.matrix_world.copy()
    mats = []
    images = []
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    try:
        me.materials.clear()
        for rgb in pal + [UNZONED]:
            m = bpy.data.materials.new("lw_zone")
            m.diffuse_color = (*(_lin(c) for c in rgb), 1.0)
            me.materials.append(m)
            mats.append(m)
        me.polygons.foreach_set("material_index", face_zone)
        me.update()
        for v in views:
            path = out.rsplit(".", 1)[0] + f"_{v}.png"
            R.render_view(tmp, v, size, path, shading={"light": "FLAT", "color_type": "MATERIAL", "show_object_outline": False, "show_cavity": False,
                                                       "show_shadows": False, "show_specular_highlight": False})
            a = _snap(np.asarray(Image.open(path).convert("RGBA")), {str(i): c for i, c in enumerate(pal + [UNZONED])})
            im = Image.fromarray(a, "RGBA")
            for k, rgb in enumerate(pal):
                m = (np.abs(a[..., :3].astype(int) - np.array(rgb)).sum(axis=2) == 0) & (a[..., 3] > 0)
                if m.sum() > 20:
                    ys, xs = np.nonzero(m)
                    j = int(np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2))          # a pixel OF the zone nearest its centroid
                    _label(im, (int(xs[j]), int(ys[j])), str(k + 1))
            im.save(path)
            images.append((v, path, im))
    finally:
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        for m in mats:
            bpy.data.materials.remove(m)
    gap = 16
    W = sum(im.size[0] for _v, _p, im in images) + gap * (len(images) - 1)
    H = max(im.size[1] for _v, _p, im in images)
    sheet = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = 0
    for _v, _p, im in images:
        sheet.paste(im, (x, H - im.size[1]))
        x += im.size[0] + gap
    sheet.save(out)
    legend = [{"number": k + 1, "name": n, "faces": len(fs), "rgb": list(pal[k])} for k, (n, fs) in enumerate(zs)]
    legend_json = out.rsplit(".", 1)[0] + "_legend.json"
    with open(legend_json, "w", encoding="utf-8") as fh:
        json.dump({"object": ob.name, "by": by, "views": views, "legend": legend, "unzoned_faces": int((face_zone == len(zs)).sum())}, fh, indent=1)
    return {"object": ob.name, "by": by, "views": views, "sheet_png": out, "view_pngs": {v: p for v, p, _ in images}, "legend": legend, "legend_json": legend_json,
            "unzoned_faces": int((face_zone == len(zs)).sum()), "how": "answer with a zone number; mesh_region_extract / mesh_local_edit take zone + by"}
