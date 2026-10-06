# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_material_id (specs/generation/image_material_id.md): a flat material-ID map that says which region of a piece is metal, cloth, leather, gold ...

source parts  (the FACT, free, exact) every polygon takes its part's material (the recipe's ``class``, or ``part_materials`` {part: material}), the part per polygon
              from ``owner`` (.npy) or the int face attribute ``part``; a throw-away copy is rendered from the SAME camera as the clay render (render.render_view)
              in flat Workbench colour with anti-aliasing off, and every opaque pixel is snapped to its palette colour
source model  (a DRAFT) the design plate goes to the image slot with purpose ``mask`` and the palette in the prompt; the reply's black line art is filled from its
              neighbours, the rest quantised to the palette in CIE Lab, and the draft is gated: ``conformance`` (the share of subject pixels within dE 25 of a
              palette colour after the line art is gone) must reach 0.99 or the draft is rejected; it is named ``*_draft`` and never auto-accepted. live=false
              (the default) is a dry run: nothing is sent or spent.
Palette entries closer than dE 60 (CIE76) are refused as indistinguishable."""

import json
import os
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import jobs_client
from . import render as R

generate_image = jobs_client.generate_image          # the slot; tests replace this name
VIEWS = tuple(R.TO_CAMERA)
MIN_DE = 60.0
DRAFT_DE = 25.0
GATE = 0.99
COST_NOTE = "about $0.10 per image at 2K (google/gemini-3.1-flash-image, purpose mask: the bake-off's measured price)"


def _hex(h):
    h = str(h).lstrip("#")
    if len(h) != 6:
        raise C.FeatureError(f"palette colours are #rrggbb, got {h!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lab(rgb):
    """sRGB 0..255 (..., 3) -> CIE Lab (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def check_palette(palette) -> dict:
    pal = {str(k): _hex(v) for k, v in (palette or {}).items()}
    if not 2 <= len(pal) <= 16:
        raise C.FeatureError("palette has 2..16 entries {material: '#rrggbb'} (the materials and colours are the user's)")
    names = list(pal)
    L = lab(np.array([pal[n] for n in names]))
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = float(np.linalg.norm(L[i] - L[j]))
            if d < MIN_DE:
                raise C.FeatureError(f"indistinguishable materials: {names[i]},{names[j]} (dE {d:.1f} < {MIN_DE:.0f}); pick colours further apart")
    return pal


def _lin(c8):
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _regions(a, pal):
    total = a.shape[0] * a.shape[1]
    out = []
    for name, rgb in pal.items():
        n = int(((a[..., 3] > 0) & (np.abs(a[..., :3].astype(int) - np.array(rgb)).sum(axis=2) == 0)).sum())
        out.append({"material": name, "pixels": n, "fraction": n / total})
    return out


def _snap(a, pal):
    names = list(pal)
    P = np.array([pal[n] for n in names])
    op = a[..., 3] > 127
    d = np.abs(a[..., None, :3].astype(int) - P[None, None]).sum(axis=3)
    idx = d.argmin(axis=2)
    out = np.zeros(a.shape, np.uint8)
    out[op, :3] = P[idx[op]]
    out[op, 3] = 255
    return out


def _parts_map(ob, view, pal, materials_of_poly, out_path, size):
    from PIL import Image
    me = ob.data.copy()
    tmp = bpy.data.objects.new(ob.name + "_matid_tmp", me)
    tmp.matrix_world = ob.matrix_world.copy()
    mats = []
    try:
        me.materials.clear()
        names = list(pal)
        for n in names:
            m = bpy.data.materials.new("lw_matid_" + n)
            m.diffuse_color = (*(_lin(c) for c in pal[n]), 1.0)
            me.materials.append(m)
            mats.append(m)
        idx = np.array([names.index(m) for m in materials_of_poly], dtype=np.int32)
        me.polygons.foreach_set("material_index", idx)
        me.update()
        R.render_view(tmp, view, size, out_path, shading={"light": "FLAT", "color_type": "MATERIAL", "show_object_outline": False, "show_cavity": False,
                                                          "show_shadows": False, "show_specular_highlight": False})
    finally:
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        for m in mats:
            bpy.data.materials.remove(m)
    a = _snap(np.asarray(Image.open(out_path).convert("RGBA")), pal)
    Image.fromarray(a, "RGBA").save(out_path)
    return a


def _poly_materials(ob, recipe_path, owner_path, part_materials, pal):
    n = len(ob.data.polygons)
    if owner_path:
        own = np.load(owner_path).reshape(-1)
    else:
        attr = ob.data.attributes.get("part")
        if attr is None or attr.domain != "FACE":
            raise C.FeatureError("material-ID by parts needs a segmented piece: an owner map or the int face attribute 'part' (run lampway_segment_mesh), or use source=model")
        own = np.empty(n, dtype=np.int64)
        attr.data.foreach_get("value", own)
    if len(own) != n:
        raise C.FeatureError(f"the owner map has {len(own)} entries for {n} polygons")
    if len(np.unique(own)) < 2:
        raise C.FeatureError("material-ID by parts needs a segmented piece (this one has a single part): run lampway_segment_mesh or use source=model")
    rec = json.loads(Path(recipe_path).read_text(encoding="utf-8")) if recipe_path else {}
    parts = list((rec.get("parts") or {}))
    mapping = dict(part_materials or {})
    for p in parts:
        mapping.setdefault(p, (rec["parts"][p] or {}).get("class") if isinstance(rec["parts"][p], dict) else None)
    out = []
    for k in own:
        part = parts[int(k)] if 0 <= int(k) < len(parts) else None
        mat = mapping.get(part)
        if mat not in pal:
            raise C.FeatureError(f"part {part!r} has material {mat!r}, which is not in the palette ({', '.join(pal)}): give part_materials or extend the palette")
        out.append(mat)
    return out


def _clean_draft(img, pal):
    """(snapped RGBA, raw conformance, conformance): background from the corners becomes transparent, black line art is filled from its neighbours, the
    rest quantised to the palette in Lab."""
    a = np.asarray(img.convert("RGB")).astype(np.float64)
    h, w = a.shape[:2]
    corners = np.r_[a[:4, :4].reshape(-1, 3), a[-4:, -4:].reshape(-1, 3), a[:4, -4:].reshape(-1, 3), a[-4:, :4].reshape(-1, 3)]
    bg = np.median(corners, axis=0)
    L = lab(a)
    P = np.array(list(pal.values()), dtype=np.float64)
    PL = lab(P)
    subject = np.linalg.norm(L - lab(bg), axis=2) > 10
    dmin = np.linalg.norm(L[..., None, :] - PL[None, None], axis=3).min(axis=2)
    raw = float((dmin[subject] <= DRAFT_DE).mean()) if subject.any() else 0.0
    line = subject & (L[..., 0] < 25) & (dmin > DRAFT_DE)
    ok = subject & ~line
    filled = a.copy()
    known = ok.copy()
    for _ in range(64):
        if not (line & ~known).any():
            break
        pad = np.pad(filled, ((1, 1), (1, 1), (0, 0)))
        pk = np.pad(known, 1)
        acc, cnt = np.zeros_like(filled), np.zeros((h, w))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                sl = (slice(1 + dy, 1 + dy + h), slice(1 + dx, 1 + dx + w))
                acc += pad[sl] * pk[sl][..., None]
                cnt += pk[sl]
        grow = line & ~known & (cnt > 0)
        filled[grow] = acc[grow] / cnt[grow][..., None]
        known |= grow
    L2 = lab(filled)
    d2 = np.linalg.norm(L2[..., None, :] - PL[None, None], axis=3)
    conf = float((d2.min(axis=2)[subject] <= DRAFT_DE).mean()) if subject.any() else 0.0
    idx = d2.argmin(axis=2)
    out = np.zeros((h, w, 4), np.uint8)
    out[subject, :3] = P[idx[subject]].astype(np.uint8)
    out[subject, 3] = 255
    return out, raw, conf


def run(piece, root, object="", view="Front", palette=None, source="parts", recipe="", owner="", part_materials=None, design_plate="", live=False, size=768,
        out_dir="material_id"):
    from PIL import Image
    pal = check_palette(palette)
    if source not in ("parts", "model"):
        raise C.FeatureError("source is parts (the fact, from a segmented piece) | model (a draft from the design plate)")
    views = list(VIEWS) if view == "all" else [view]
    if any(v not in VIEWS for v in views):
        raise C.FeatureError(f"view is one of {', '.join(VIEWS)} | all")
    if not str(piece or "").strip():
        raise C.FeatureError("piece names the output folder")
    d = Path(out_dir) / piece
    if source == "parts":
        ob = C.need_object(object)
        mats = _poly_materials(ob, recipe, owner, part_materials, pal)
        d.mkdir(parents=True, exist_ok=True)
        maps, regions = {}, {}
        for v in views:
            path = str(d / f"{v}_matid.png")
            a = _parts_map(ob, v, pal, mats, path, size)
            maps[v], regions[v] = path, _regions(a, pal)
        return {"piece": piece, "source": "parts", "maps": maps, "regions": regions, "conformance": 1.0, "draft": False, "cost_usd": 0.0,
                "palette": {k: "#%02x%02x%02x" % v for k, v in pal.items()}}
    if not design_plate:
        raise C.FeatureError("source=model needs design_plate (the approved plate the draft is read from)")
    if not os.path.exists(design_plate):
        raise FileNotFoundError(f"design_plate {design_plate} not found")
    legend = ", ".join(f"{k} = #%02x%02x%02x" % v for k, v in pal.items())
    prompt = ("Repaint this armour plate as a flat MATERIAL-ID map: every region filled with exactly one of these colours and no other colour, no shading, no "
              f"lines, no outlines, no text, plain white background: {legend}. Keep the silhouette and every region boundary exactly.")
    if not live:
        return {"piece": piece, "source": "model", "dry_run": True, "prompt": prompt, "views": views, "requests": len(views), "cost_note": COST_NOTE,
                "how": "live=true sends the plate to the image slot (purpose mask); only when the user asked for it"}
    with open(design_plate, "rb") as fh:
        plate = fh.read()
    d.mkdir(parents=True, exist_ok=True)
    maps, regions, raws, confs = {}, {}, {}, {}
    for v in views:
        data = generate_image(prompt, plate, 1, params_extra={"purpose": "mask"})[0]
        raw_path = d / f"{v}_matid_raw.png"
        raw_path.write_bytes(data)
        import io
        snapped, raw, conf = _clean_draft(Image.open(io.BytesIO(data)), pal)
        raws[v], confs[v] = round(raw, 4), round(conf, 4)
        if conf < GATE:
            raise C.FeatureError(f"Draft rejected: conformance {conf:.2f} < {GATE} in {v}: the model drew colours outside the palette (raw reply kept at {raw_path.name})")
        path = str(d / f"{v}_matid_draft.png")
        Image.fromarray(snapped, "RGBA").save(path)
        maps[v], regions[v] = path, _regions(snapped, pal)
    return {"piece": piece, "source": "model", "draft": True, "maps": maps, "regions": regions, "raw_conformance": raws, "conformance": min(confs.values()),
            "cost_note": COST_NOTE, "note": "a DRAFT: a part-ID render or the user's confirmation replaces it; it is never auto-accepted"}
