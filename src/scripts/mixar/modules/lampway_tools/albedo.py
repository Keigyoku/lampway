# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live material toggle that uses the projected albedo as base colour.

The mesh-paint projection writes ``v3_colour_atlas.png``, which (painted flat, no lighting, over our own mesh's render) is a usable
albedo. The shelf's captain built this toggle by hand in his live material ``textured_chest_p17_albedo``; nodes carry the label
prefix ``AB:``. This is the same thing as a function: a COPY of the textured material gets an image node on the UV map and a Mix
between the material's own base colour and the albedo, driven by one Value node (1 = albedo, 0 = the textured look). The original
material is never touched.
"""

import os

import bpy

from . import canon_io

PREFIX = "AB:"


def _nodes(nt):
    return {n.label: n for n in nt.nodes if n.label.startswith(PREFIX)}


def apply(material: str, albedo_path: str, name: str = "", on: bool = True) -> dict:
    src = bpy.data.materials.get(material)
    if src is None:
        raise LookupError(f"no material named {material!r}; the scene has: {sorted(m.name for m in bpy.data.materials)}")
    if not os.path.exists(albedo_path):
        raise FileNotFoundError(f"{albedo_path} not found (the projected albedo, v3_colour_atlas.png)")
    target_name = name or (material if material.endswith("_albedo") else material + "_albedo")
    mat = bpy.data.materials.get(target_name)
    if mat is None:
        mat = src.copy()
        mat.name = target_name
    nt = mat.node_tree
    bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base = bs.inputs["Base Color"]
    old_mix = _nodes(nt).get("AB: mix")
    if old_mix is not None:                                        # a re-apply: put the original base colour back first
        orig = old_mix.inputs[6]
        if orig.links:
            nt.links.new(orig.links[0].from_socket, base)
        else:
            for l in list(base.links):
                nt.links.remove(l)
            base.default_value = tuple(orig.default_value)
    for n in list(_nodes(nt).values()):
        nt.nodes.remove(n)

    def node(kind, label, **kw):
        n = nt.nodes.new(kind)
        n.label = f"{PREFIX} {label}"
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    uv = node("ShaderNodeTexCoord", "uv")
    tex = node("ShaderNodeTexImage", "albedo")
    tex.image = canon_io.load_image(albedo_path, role="basecolor", check_existing=False)
    tex.image.colorspace_settings.name = "sRGB"
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    use = node("ShaderNodeValue", "use albedo")
    use.outputs[0].default_value = 1.0 if on else 0.0
    mix = node("ShaderNodeMix", "mix", data_type="RGBA", blend_type="MIX")
    nt.links.new(use.outputs[0], mix.inputs[0])
    if base.links:
        nt.links.new(base.links[0].from_socket, mix.inputs[6])
    else:
        mix.inputs[6].default_value = tuple(base.default_value)
    nt.links.new(tex.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], base)
    return {"material": mat.name, "on": bool(on), "albedo": albedo_path}


def set_albedo(material: str, on: bool) -> None:
    n = _nodes(bpy.data.materials[material].node_tree).get("AB: use albedo")
    if n is None:
        raise LookupError(f"{material} has no albedo toggle; call apply first")
    n.outputs[0].default_value = 1.0 if on else 0.0


def state(material: str) -> bool:
    n = _nodes(bpy.data.materials[material].node_tree).get("AB: use albedo")
    return bool(n and n.outputs[0].default_value >= 0.5)
