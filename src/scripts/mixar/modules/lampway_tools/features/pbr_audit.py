# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""pbr_pack, the material half: audit what a material actually has connected, and swap only its base colour.

audit walks the Principled BSDF's inputs: an image feeding Base Color must be sRGB, one feeding Roughness, Metallic or (through a Normal Map node) Normal must be Non-Color, and a Normal
input needs a Normal Map node. "Automatic import does not wire every PBR channel", so each channel is reported linked or not. swap_base_color works on a COPY of the material (the original
stays), replaces only the base-colour image and keeps the roughness, metallic and normal nodes; the new colour map must share the mesh's UV layout (its producer's UV hash must equal the
mesh's)."""

import bpy

from .. import canon_io

from . import common as C

CHANNELS = ("Base Color", "Roughness", "Metallic", "Normal")
EXPECT = {"Base Color": "sRGB", "Roughness": "Non-Color", "Metallic": "Non-Color", "Normal": "Non-Color"}


def _source_image(socket):
    """The image node feeding a socket, looking through one Normal Map node."""
    if not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == "NORMAL_MAP":
        c = node.inputs["Color"]
        return _source_image(c) if c.is_linked else "NO-COLOR"
    return node if node.type == "TEX_IMAGE" else None


def _bsdf(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def audit(object_name):
    ob = C.need_object(object_name)
    mats = [s.material for s in ob.material_slots if s.material and s.material.use_nodes]
    if not mats:
        raise C.FeatureError(f"{ob.name} has no node material to audit")
    checks, connected, issues = [], [], []
    for mat in mats:
        b = _bsdf(mat)
        if b is None:
            issues.append(f"{mat.name}: no Principled BSDF")
            continue
        for ch in CHANNELS:
            sock = b.inputs[ch]
            src = _source_image(sock)
            linked = bool(sock.is_linked)
            connected.append({"material": mat.name, "channel": ch, "linked": linked})
            if not linked:
                if ch in ("Metallic", "Roughness", "Normal"):
                    issues.append(f"{mat.name}: {ch} is not connected (automatic import does not wire every channel)")
                continue
            if ch == "Normal" and sock.links[0].from_node.type != "NORMAL_MAP":
                issues.append(f"{mat.name}: Normal is not routed through a Normal Map node")
            if src == "NO-COLOR" or src is None:
                continue
            cs = src.image.colorspace_settings.name if src.image else None
            ok = cs == EXPECT[ch]
            checks.append({"material": mat.name, "map": ch, "image": src.image.name if src.image else None, "colorspace": cs, "expected": EXPECT[ch], "pass": ok})
            if not ok:
                issues.append(f"{mat.name}: {ch.lower()} map {src.image.name if src.image else '?'} is {cs}, expected {EXPECT[ch]} ({'colour' if ch == 'Base Color' else 'data'} map)")
    return {"ok": not issues, "checks": checks, "connected": connected, "issues": issues}


def swap_base_color(object_name, new_base, uv_hash=None):
    from . import workflows as W
    ob = C.need_object(object_name)
    if uv_hash is not None and uv_hash != W.uv_hash(ob):
        raise C.FeatureError("the colour map must share this mesh's UV layout: its producer's UV hash differs from this mesh's (direct reuse must not be assumed for a retextured export)")
    slot = next((s for s in ob.material_slots if s.material and s.material.use_nodes and _bsdf(s.material)), None)
    if slot is None:
        raise C.FeatureError(f"{ob.name} has no Principled material to swap the base colour of")
    src = _source_image(_bsdf(slot.material).inputs["Base Color"])
    if src is None or src == "NO-COLOR":
        raise C.FeatureError(f"{slot.material.name} has no image on Base Color to replace")
    mat = slot.material.copy()
    mat.name = slot.material.name + "_swap"
    node = next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.outputs["Color"].links and n.outputs["Color"].links[0].to_socket.name == "Base Color")
    img = canon_io.load_image(new_base, role="basecolor", check_existing=False)
    img.colorspace_settings.name = "sRGB"
    node.image = img
    slot.material = mat
    return {"ok": True, "object": ob.name, "material": mat.name, "replaced": "base", "kept": [c for c in ("Roughness", "Metallic", "Normal") if _bsdf(mat).inputs[c].is_linked]}
