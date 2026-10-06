# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Micro depth for a textured_atlas material without the relief map.

Ported from the shelf's texlib/detail_normals.py (SPIKE 2026-10-04), which was an exec-in-the-live-scene script; now a
function. Per-material tiling DETAIL NORMALS, box-projected in object space at each material's own box scale (no UV seams,
crisp at any distance - the 2048 relief bump was "a pixelation effect on everything", the user, 2026-10-04): the metals
take their ambientCG NormalGL maps through Normal Map nodes; cloth and leather (colour tiles only) take a small bump from
their colour's brightness; the per-texel masks blend them. Idempotent: nodes it made are labelled 'DN:' and replaced on a
re-run; the relief bump stays in the chain (strength 0 = off). Strengths: plate 0.6, gold 0.45, cloth 0.25, leather 0.3.
"""

import os

import bpy

from . import canon_io

DEFAULT_STRENGTHS = {"plate": 0.6, "gold": 0.45, "cloth": 0.25, "leather": 0.3}
_METALS = (("plate", "Metal009", "Metal009_2K-PNG_NormalGL.png"), ("gold", "Metal048C", "Metal048C_2K-PNG_NormalGL.png"))


def apply(material, strengths=None, acg_dir=None) -> dict:
    """Add the detail-normal layers to ``material`` (a name). ``acg_dir`` is the ambientCG library
    (LAMPWAY_AMBIENTCG_DIR when not given)."""
    acg = acg_dir or os.environ.get("LAMPWAY_AMBIENTCG_DIR")
    if not acg:
        raise LookupError("no ambientCG folder: pass acg_dir or set LAMPWAY_AMBIENTCG_DIR")
    paths = {k: os.path.join(acg, d, f) for k, d, f in _METALS}
    for p in paths.values():
        if not os.path.exists(p):
            raise FileNotFoundError(f"{p} not found (ambientCG normal map)")
    S = {**DEFAULT_STRENGTHS, **(strengths or {})}
    mat = bpy.data.materials[material]
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    for n in [n for n in N if n.label.startswith("DN:")]:
        N.remove(n)
    bs = next(n for n in N if n.type == "BSDF_PRINCIPLED")
    bump = next(n for n in N if n.type == "BUMP")
    tc = next(n for n in N if n.type == "TEX_COORD")
    masks = {}
    for n in N:                                                           # the mask images by name
        if n.type == "TEX_IMAGE" and n.image and (n.image.name.startswith("mask_") or "mask_" in os.path.basename(n.image.filepath)):
            masks[os.path.basename(n.image.filepath)[5:-4]] = n.outputs["Color"]
    colour_tex = {}                                                       # each material's existing colour tile node (box projected)
    for n in N:
        if n.type == "TEX_IMAGE" and n.image and n.projection == "BOX":
            fn = os.path.basename(n.image.filepath)
            for k, key in (("red", "Crimson_Cape"), ("linen", "Black_Linen"), ("leather", "Oxblood_Belt")):
                if key in fn and "Roughness" not in fn:
                    colour_tex[k] = n

    def node(t, label, **kw):
        x = N.new(t)
        x.label = "DN:" + label
        for k, v in kw.items():
            setattr(x, k, v)
        return x

    def box_img(path, scale, label):
        mp = node("ShaderNodeMapping", label + " map")
        mp.inputs["Scale"].default_value = (scale, scale, scale)
        L.new(tc.outputs["Object"], mp.inputs["Vector"])
        t = node("ShaderNodeTexImage", label)
        t.image = canon_io.load_image(path, role="normal", check_existing=True)
        t.image.colorspace_settings.name = "Non-Color"
        t.projection = "BOX"
        t.projection_blend = 0.5
        L.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    def nmap(path, scale, strength, label):
        t = box_img(path, scale, label)
        nm = node("ShaderNodeNormalMap", label + " nm")
        nm.inputs["Strength"].default_value = strength
        L.new(t.outputs["Color"], nm.inputs["Color"])
        return nm.outputs["Normal"]

    def cbump(src, strength, label):
        bw = node("ShaderNodeRGBToBW", label + " bw")
        L.new(src.outputs["Color"], bw.inputs["Color"])
        b = node("ShaderNodeBump", label + " bump")
        b.inputs["Strength"].default_value = strength
        b.inputs["Distance"].default_value = 0.002
        L.new(bw.outputs["Val"], b.inputs["Height"])
        return b.outputs["Normal"]

    layers = [("plate", nmap(paths["plate"], 5.0, S["plate"], "plate normal")),
              ("gold", nmap(paths["gold"], 5.0, S["gold"], "gold normal"))]
    if "red" in colour_tex:
        layers.append(("red", cbump(colour_tex["red"], S["cloth"], "red weave")))
    if "linen" in colour_tex:
        layers.append(("linen", cbump(colour_tex["linen"], S["cloth"], "linen weave")))
    if "leather" in colour_tex:
        layers.append(("leather", cbump(colour_tex["leather"], S["leather"], "leather grain")))
    geo = node("ShaderNodeNewGeometry", "geo")
    cur = geo.outputs["Normal"]                                           # the base: the surface normal
    for k, nrm in layers:
        if k not in masks:
            continue
        mx = node("ShaderNodeMix", k + " mix")
        mx.data_type = "VECTOR"
        L.new(masks[k], mx.inputs["Factor"])
        L.new(cur, mx.inputs[4])
        L.new(nrm, mx.inputs[5])
        cur = mx.outputs[1]
    L.new(cur, bump.inputs["Normal"])                                     # the relief bump (strength 0 = off) perturbs the detail normal
    L.new(bump.outputs["Normal"], bs.inputs["Normal"])
    return {"material": material, "layers": [k for k, _ in layers if k in masks], "masks_found": sorted(masks), "strengths": S}
