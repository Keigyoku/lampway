# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place's shading kinds: a material appended onto a slot (a Mixar Paint material is never replaced silently), a PBR / texture set built into a Principled BSDF by role
(base colour sRGB, everything else Non-Color, ORM split G=roughness B=metallic, a DX normal map's green flipped before the Normal Map node), a node group dropped into a
material's tree, an HDRI as the world's environment."""

import bpy

from .asset_place import PlaceError, entry, file_of, load_blend, stamp, where

SRGB_ROLES = ("basecolor", "emission")


def _slot_target(target):
    """(object, slot index) of a ``slot:<object>:<index>`` or ``object:<name>`` target (the object's active slot); (None, None) for no target."""
    w = where(target)
    if w.startswith("slot:"):
        body = w[len("slot:"):]
        name, _, idx = body.rpartition(":")
        if not name or not idx.isdigit():
            raise PlaceError(f"target {w!r}: write slot:<object>:<index>")
        index = int(idx)
    elif w.startswith("object:"):
        name, index = w.split(":", 1)[1], None
    else:
        return None, None
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != "MESH":
        raise PlaceError(f"{name!r} is not a mesh object: pick a mesh object with a material slot")
    return ob, (ob.active_material_index if index is None else index)


def is_mixar_paint(mat) -> bool:
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return False
    return any(n.type == "GROUP" and n.node_tree is not None and getattr(getattr(n.node_tree, "mp", None), "is_mpaint_node", False) for n in mat.node_tree.nodes)


def _assign(mat, target, opts) -> dict:
    ob, index = _slot_target(target)
    if ob is None:
        return {}
    while len(ob.material_slots) <= index:
        ob.data.materials.append(None)
    current = ob.material_slots[index].material
    if is_mixar_paint(current) and not opts.get("replace"):
        raise PlaceError(f"object already has a Mixar Paint material: pass replace:true (slot {index} holds {current.name!r})")
    ob.material_slots[index].material = mat
    return {"object": ob.name, "slot": index}


def assign_material(asset, opts, target) -> list:
    _slot_target(target)                     # refuse a bad target before anything is read
    path, sha, _ = file_of(asset, ("blend",))
    mat = load_blend(path, "materials", str(asset.get("name")), "material")
    stamp(mat, asset, sha)
    return [entry("material", mat, **_assign(mat, target, opts))]


# ---- PBR sets

def _members(asset) -> list:
    if asset.get("kind") == "map":
        return [asset]
    members = [m for m in asset.get("members") or [] if m.get("kind") == "map"]
    if not members:
        raise PlaceError(f"{asset.get('name')!r} carries no map members: fetch it with include members (lampway_asset_get) or place its maps one by one")
    return members


def _role(m) -> str:
    sub = str(m.get("subtype") or "")
    if sub in ("normal_gl", "normal_dx"):
        return sub
    return sub or str((m.get("stats") or {}).get("channel") or "")


def _is_dx(m) -> bool:
    st = m.get("stats") or {}
    return _role(m) == "normal_dx" or str(st.get("convention") or st.get("normal_convention") or "").lower() == "dx"


def _image(m, nt, x, y):
    path, sha, _ = file_of(m, ("main",))
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "sRGB" if _role(m) in SRGB_ROLES else "Non-Color"
    stamp(img, m, sha)
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image, node.location, node.label = img, (x, y), _role(m)
    return node


def _flip_green(nt, color_out, x, y):
    sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (x, y)
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0; inv.location = (x + 160, y); inv.label = "DX green flip"
    comb = nt.nodes.new("ShaderNodeCombineColor"); comb.location = (x + 320, y)
    nt.links.new(color_out, sep.inputs["Color"])
    nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
    nt.links.new(sep.outputs["Green"], inv.inputs[1])
    nt.links.new(inv.outputs[0], comb.inputs["Green"])
    nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
    return comb.outputs["Color"]


def build_pbr(asset, opts):
    mat = bpy.data.materials.new(str(asset.get("name")))
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    unused = []
    for i, m in enumerate(_members(asset)):
        role, y = _role(m), 300 - i * 300
        if role in ("ao", "mask", "material_id", "curvature") or (role == "height" and not opts.get("height")):
            unused.append(role)
            continue
        if role not in ("basecolor", "orm", "roughness", "metallic", "normal_gl", "normal_dx", "height", "emission"):
            unused.append(role)
            continue
        tex = _image(m, nt, -900, y)
        col = tex.outputs["Color"]
        if role == "basecolor":
            nt.links.new(col, bsdf.inputs["Base Color"])
        elif role == "emission":
            nt.links.new(col, bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = 1.0
        elif role == "roughness":
            nt.links.new(col, bsdf.inputs["Roughness"])
        elif role == "metallic":
            nt.links.new(col, bsdf.inputs["Metallic"])
        elif role == "orm":                    # R = occlusion (Principled has no input for it), G = roughness, B = metallic
            sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-600, y)
            nt.links.new(col, sep.inputs["Color"])
            nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
            nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        elif role in ("normal_gl", "normal_dx"):
            nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-200, y)
            nt.links.new(_flip_green(nt, col, -700, y) if _is_dx(m) else col, nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        elif role == "height":
            disp = nt.nodes.new("ShaderNodeDisplacement"); disp.location = (-200, y)
            nt.links.new(col, disp.inputs["Height"])
            nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    stamp(mat, asset, (asset.get("files") or [{}])[0].get("sha256") or "")      # a set has no file of its own: its maps carry theirs
    return mat, unused


def assign_maps(asset, opts, target) -> list:
    _slot_target(target)
    mat, unused = build_pbr(asset, opts)
    return [entry("material", mat, unused_maps=unused, **_assign(mat, target, opts))]


# ---- node groups and the world

def add_node_group(asset, opts, target) -> list:
    w = where(target)
    if not w.startswith("node_tree:"):
        raise PlaceError("add_node_group needs target node_tree:<material>")
    mname = w.split(":", 1)[1]
    mat = bpy.data.materials.get(mname)
    if mat is None:
        raise PlaceError(f"no material named {mname!r}: the target is node_tree:<material> of a material in this file")
    path, sha, _ = file_of(asset, ("blend",))
    group = next((g for g in bpy.data.node_groups if g.get("lw_asset_id") == str(asset.get("id")) and g.get("lw_asset_sha256") == str(sha)), None)
    if group is None:
        group = load_blend(path, "node_groups", str(asset.get("name")), "node group")
        stamp(group, asset, sha)
    mat.use_nodes = True
    nt = mat.node_tree
    empty = all(n.type == "OUTPUT_MATERIAL" for n in nt.nodes)
    node = nt.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.location = tuple(float(v) for v in (opts.get("location") or (0.0, 0.0)))
    shader = next((o for o in node.outputs if o.type == "SHADER"), None)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    wired = bool(empty and shader is not None and out is not None)
    if wired:
        nt.links.new(shader, out.inputs["Surface"])
    return [entry("node_group", group, material=mat.name, node=node.name, wired=wired)]


def set_world(asset, opts, target) -> list:
    from .asset_place import scene
    sc = scene()
    path, sha, _ = file_of(asset, ("main",))
    img = bpy.data.images.load(path, check_existing=True)
    stamp(img, asset, sha)
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None) or nt.nodes.new("ShaderNodeBackground")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
    if not bg.outputs["Background"].is_linked:
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image, env.location = img, (bg.location[0] - 300, bg.location[1])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    stamp(world, asset, sha)
    return [entry("world", world, image=img.name)]
