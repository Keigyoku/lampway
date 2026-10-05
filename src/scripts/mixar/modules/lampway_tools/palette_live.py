# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live palette: a Hue/Saturation/Value node per class on a COPY of the material, mixed in by the class's mask, so the person can nudge three numbers per class in the viewport.

Nodes carry the label prefix ``PAL:`` (the pattern of ``albedo.py``'s ``AB:`` and ``detail_normals.py``'s ``DN:``): a re-apply removes the old set and rebuilds it, so there is one set
per class. ``read`` reads the sliders back (the person's nudge is law); the HSV node works on linear colour, which is why ``palette_fit`` measures in linear.
"""

import os

import bpy

PREFIX = "PAL:"


def _nodes(nt):
    return [n for n in nt.nodes if n.label.startswith(PREFIX)]


def _strip(nt, base):
    """Remove the PAL: nodes and put the base colour's original source back."""
    pal = _nodes(nt)
    mix = next((n for n in pal if n.label == f"{PREFIX} out"), None)
    if mix is not None:
        src = next((n for n in pal if n.label == f"{PREFIX} source"), None)
        orig = mix.inputs[6]
        if orig.links:
            nt.links.new(orig.links[0].from_socket, base)
        else:
            for l in list(base.links):
                nt.links.remove(l)
            base.default_value = tuple(orig.default_value)
    for n in pal:
        nt.nodes.remove(n)


def apply(material, masks_dir, palette, order, name=""):
    src = bpy.data.materials.get(material)
    if src is None:
        raise LookupError(f"no material named {material!r}; the scene has: {sorted(m.name for m in bpy.data.materials)}")
    target = name or (material if material.endswith("_pal") else material + "_pal")
    mat = bpy.data.materials.get(target)
    if mat is None:
        mat = src.copy()
        mat.name = target
    nt = mat.node_tree
    bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base = bs.inputs["Base Color"]
    _strip(nt, base)
    for c in order:
        if not os.path.exists(os.path.join(masks_dir, f"mask_{c}.png")):
            raise FileNotFoundError(f"no mask_{c}.png in {masks_dir}: run material_masks")
    uv = nt.nodes.new("ShaderNodeTexCoord")
    uv.label = f"{PREFIX} uv"
    current = base.links[0].from_socket if base.links else None
    start_value = tuple(base.default_value)
    holder = nt.nodes.new("ShaderNodeValue")        # a source marker so the chain's first mix has a stable origin
    holder.label = f"{PREFIX} source"
    first = True
    last_out = None
    for c in order:
        row = palette[c]
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.label = f"{PREFIX} {c} hsv"
        hsv.inputs["Hue"].default_value = 0.5 + float(row["hue_shift"])
        hsv.inputs["Saturation"].default_value = float(row["sat_mul"])
        hsv.inputs["Value"].default_value = float(row["val_mul"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.label = f"{PREFIX} {c} mask"
        tex.image = bpy.data.images.load(os.path.join(masks_dir, f"mask_{c}.png"), check_existing=False)
        tex.image.colorspace_settings.name = "Non-Color"
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type, mix.blend_type = "RGBA", "MIX"
        mix.label = f"{PREFIX} {c} mix"
        nt.links.new(tex.outputs["Color"], mix.inputs[0])
        if first:
            if current is not None:
                nt.links.new(current, mix.inputs[6])
                nt.links.new(current, hsv.inputs["Color"])
            else:
                mix.inputs[6].default_value = start_value
                hsv.inputs["Color"].default_value = start_value
            first_mix = mix
            first = False
        else:
            nt.links.new(last_out, mix.inputs[6])
            nt.links.new(last_out, hsv.inputs["Color"])
        nt.links.new(hsv.outputs["Color"], mix.inputs[7])
        last_out = mix.outputs[2]
    out = nt.nodes.new("ShaderNodeMix")
    out.data_type, out.blend_type = "RGBA", "MIX"
    out.label = f"{PREFIX} out"
    out.inputs[0].default_value = 1.0
    if current is not None:
        nt.links.new(current, out.inputs[6])
    else:
        out.inputs[6].default_value = start_value
    if last_out is not None:
        nt.links.new(last_out, out.inputs[7])
    nt.links.new(out.outputs[2], base)
    return {"material": mat.name, "classes": list(order)}


def read(material, order=None):
    mat = bpy.data.materials.get(material)
    if mat is None:
        raise LookupError(f"no material named {material!r}")
    nodes = {n.label: n for n in _nodes(mat.node_tree)}
    classes = order or sorted({l.split()[1] for l in nodes if l.endswith(" hsv")})
    palette = {}
    for c in classes:
        n = nodes.get(f"{PREFIX} {c} hsv")
        if n is None:
            raise LookupError(f"{material} has no PAL: node for {c}: run apply_live first")
        palette[c] = {"hue_shift": round(n.inputs["Hue"].default_value - 0.5, 4), "sat_mul": round(n.inputs["Saturation"].default_value, 4),
                      "val_mul": round(n.inputs["Value"].default_value, 4)}
    return palette


def set_slider(material, cls, hue=None, sat=None, val=None):
    n = next(n for n in _nodes(bpy.data.materials[material].node_tree) if n.label == f"{PREFIX} {cls} hsv")
    if hue is not None:
        n.inputs["Hue"].default_value = hue
    if sat is not None:
        n.inputs["Saturation"].default_value = sat
    if val is not None:
        n.inputs["Value"].default_value = val
