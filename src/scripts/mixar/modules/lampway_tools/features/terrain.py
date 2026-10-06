# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""terrain: a modest landscape backdrop in Blender (specs/mixar_docs/terrain.md): a geometry-nodes heightfield on a grid, carved channels and basins, a water
plane and instanced vegetation. There is no erosion simulation, no sky and no real-world (DEM/GIS) import.

heightfield: a grid of ``resolution`` x ``resolution`` quads over ``size_m``, with a copy of the node group LW_TerrainField (``LW_TerrainField_<name>``) as the modifier ``LW_Terrain``:
4D noise (W = the seed) over position, its own minimum and maximum (Attribute Statistic) mapped to 0..height_m, so the height range is the height asked
for and height, detail, scale, warp and seed stay adjustable. carve COMMITS the procedural result to real vertices (stage two) and lowers a channel
(within width/2 of the polyline, a smooth bank to width/2 + bank) or a basin by its depth; nothing beyond the bank moves. water: a plane at
water_level_m. vegetation: points sampled on the terrain (deterministic seed) above the water and below MAX_SLOPE_DEG, at the biome's density
[UNVERIFIED densities] and never more than max_instances, instancing the given objects. from_image: the grid displaced by a heightmap's luminance,
blurred first so 8-bit steps do not terrace; an image that looks like a ground-level photo (a bright, blue upper band) is refused."""

import json
import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C

PRESETS = {"mountains": {"height_m": 40.0, "scale": 0.02, "detail": 8.0, "warp": 0.5}, "hills": {"height_m": 10.0, "scale": 0.03, "detail": 4.0, "warp": 0.2},
           "canyon": {"height_m": 25.0, "scale": 0.025, "detail": 6.0, "warp": 1.0}, "desert": {"height_m": 5.0, "scale": 0.05, "detail": 2.0, "warp": 0.1},
           "flat": {"height_m": 0.5, "scale": 0.05, "detail": 1.0, "warp": 0.0}}
BIOMES = {"riparian": 0.2, "grassland": 0.5, "meadow": 0.3, "forest": 0.1}       # instances per square metre [UNVERIFIED]
ACTIONS = ("heightfield", "carve", "water", "vegetation", "from_image")
MAX_SLOPE_DEG = 35.0
GROUP = "LW_TerrainField"


def _field_group():
    g = bpy.data.node_groups.get(GROUP)
    if g is not None:
        return g
    g = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for n in ("Height", "Scale", "Detail", "Warp", "Seed"):
        g.interface.new_socket(n, in_out="INPUT", socket_type="NodeSocketFloat")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = g.nodes, g.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    pos = N.new("GeometryNodeInputPosition")
    noise = N.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    stat = N.new("GeometryNodeAttributeStatistic")
    stat.data_type, stat.domain = "FLOAT", "POINT"
    mr = N.new("ShaderNodeMapRange")
    comb = N.new("ShaderNodeCombineXYZ")
    setp = N.new("GeometryNodeSetPosition")
    L.new(pos.outputs["Position"], noise.inputs["Vector"])
    L.new(gi.outputs["Seed"], noise.inputs["W"])
    L.new(gi.outputs["Scale"], noise.inputs["Scale"])
    L.new(gi.outputs["Detail"], noise.inputs["Detail"])
    L.new(gi.outputs["Warp"], noise.inputs["Distortion"])
    L.new(gi.outputs["Geometry"], stat.inputs["Geometry"])
    L.new(noise.outputs["Fac"], stat.inputs["Attribute"])
    L.new(noise.outputs["Fac"], mr.inputs["Value"])
    L.new(stat.outputs["Min"], mr.inputs["From Min"])
    L.new(stat.outputs["Max"], mr.inputs["From Max"])
    mr.inputs["To Min"].default_value = 0.0
    L.new(gi.outputs["Height"], mr.inputs["To Max"])
    L.new(mr.outputs["Result"], comb.inputs["Z"])
    L.new(gi.outputs["Geometry"], setp.inputs["Geometry"])
    L.new(comb.outputs["Vector"], setp.inputs["Offset"])
    L.new(setp.outputs["Geometry"], go.inputs["Geometry"])
    return g


def _grid(name, size, res):
    k = np.linspace(-size / 2, size / 2, res + 1)
    xx, yy = np.meshgrid(k, k)
    verts = np.stack([xx.ravel(), yy.ravel(), np.zeros(xx.size)], axis=1)
    faces = [(j * (res + 1) + i, j * (res + 1) + i + 1, (j + 1) * (res + 1) + i + 1, (j + 1) * (res + 1) + i) for j in range(res) for i in range(res)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll = bpy.data.collections.get("LW_Terrain") or bpy.data.collections.new("LW_Terrain")
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    coll.objects.link(ob)
    return ob


def _terrain(name):
    ob = C.need_object(name)
    if "lw_terrain" not in ob:
        raise C.FeatureError(f"{name} is not a terrain this tool made (action=heightfield first)")
    return ob, json.loads(ob["lw_terrain"])


def _check_res(resolution, size_m):
    if int(resolution) > 1024:
        raise C.FeatureError("resolution is capped at 1024 (a million vertices)")
    if int(resolution) < 32:
        raise C.FeatureError("resolution is 32..1024")
    if not 20 <= float(size_m) <= 500:
        raise C.FeatureError("size_m is 20..500")


def heightfield(name, preset="hills", size_m=100.0, resolution=256, height_m=None, detail=None, detail_scale=None, warp=None, seed=0):
    if preset not in PRESETS:
        raise C.FeatureError(f"preset is {' | '.join(PRESETS)}")
    _check_res(resolution, size_m)
    if bpy.data.objects.get(name) is not None:
        raise C.FeatureError(f"an object named {name!r} exists: pick another name")
    p = dict(PRESETS[preset])
    for k, v in (("height_m", height_m), ("detail", detail), ("scale", detail_scale), ("warp", warp)):
        if v is not None:
            p[k] = float(v)
    ob = _grid(name, float(size_m), int(resolution))
    # One group per terrain, its input defaults set BEFORE the modifier takes it: the modifier copies the defaults at assignment (measured: defaults
    # changed afterwards left 0 m of relief), and this build refuses ID properties on the modifier for its inputs.
    g = _field_group().copy()
    g.name = f"{GROUP}_{name}"
    values = {"Height": p["height_m"], "Scale": p["scale"], "Detail": p["detail"], "Warp": p["warp"], "Seed": float(seed)}
    for item in g.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name in values:
            item.default_value = values[item.name]
    mod = ob.modifiers.new("LW_Terrain", "NODES")
    mod.node_group = g
    ob["lw_terrain"] = json.dumps({"preset": preset, "size_m": float(size_m), "resolution": int(resolution), "seed": int(seed), **p})
    ob.data.update()
    bpy.context.view_layer.update()
    return {"objects": [ob.name], "modifier": "LW_Terrain", "params": {"preset": preset, "seed": int(seed), **p},
            "stats": {"vertices": len(ob.data.vertices), "instances": 0}, "note": "the height stays live until a carve commits it"}


def _commit(ob):
    if not any(m.name == "LW_Terrain" for m in ob.modifiers):
        return False
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    old = ob.data
    ob.modifiers.remove(ob.modifiers["LW_Terrain"])
    ob.data = me
    me.name = ob.name
    bpy.data.meshes.remove(old)
    return True


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, float(np.dot(p - a, ab) / max(float(np.dot(ab, ab)), 1e-12))))
    return float(np.linalg.norm(p - (a + ab * t)))


def carve(name, channel=None, basin=None):
    ob, _meta = _terrain(name)
    if not channel and not basin:
        raise C.FeatureError("carve needs a channel {polyline: [[x, y], ...], width_m, depth_m, bank_m} or a basin {centre: [x, y], radius_m, depth_m}")
    committed = _commit(ob)
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if channel:
        line = [np.array(p, float) for p in channel["polyline"]]
        if len(line) < 2:
            raise C.FeatureError("a channel's polyline has at least two points")
        half, bank, depth = float(channel["width_m"]) / 2, float(channel.get("bank_m", 0.0)), float(channel["depth_m"])
        for i, v in enumerate(co):
            d = min(_seg_dist(v[:2], a, b) for a, b in zip(line, line[1:]))
            co[i, 2] -= depth * _falloff(d, half, bank)
    if basin:
        c, r, depth = np.array(basin["centre"], float), float(basin["radius_m"]), float(basin["depth_m"])
        bank = float(basin.get("bank_m", r * 0.3))
        for i, v in enumerate(co):
            co[i, 2] -= depth * _falloff(float(np.linalg.norm(v[:2] - c)), r, bank)
    ob.data.vertices.foreach_set("co", co.ravel())
    ob.data.update()
    return {"objects": [ob.name], "committed": True, "warning": "stage two commits the procedural result to vertices: tune the height first" if committed else "",
            "stats": {"vertices": len(ob.data.vertices)}}


def _falloff(d, inner, bank):
    if d <= inner:
        return 1.0
    if bank <= 0 or d >= inner + bank:
        return 0.0
    t = (d - inner) / bank
    return 1.0 - t * t * (3 - 2 * t)


def water(name, water_level_m=0.0):
    ob, meta = _terrain(name)
    s = meta["size_m"]
    wname = f"{name}_water"
    for o in [o for o in bpy.data.objects if o.name == wname]:
        bpy.data.objects.remove(o)
    me = bpy.data.meshes.new(wname)
    me.from_pydata([(-s / 2, -s / 2, 0), (s / 2, -s / 2, 0), (s / 2, s / 2, 0), (-s / 2, s / 2, 0)], [], [(0, 1, 2, 3)])
    w = bpy.data.objects.new(wname, me)
    w.location = (ob.location.x, ob.location.y, float(water_level_m))
    mat = bpy.data.materials.get("LW_Water") or bpy.data.materials.new("LW_Water")
    mat.diffuse_color = (0.1, 0.25, 0.4, 0.8)
    me.materials.append(mat)
    for c in ob.users_collection:
        c.objects.link(w)
    return {"objects": [w.name], "object": w.name, "water_level_m": float(water_level_m)}


def vegetation(name, biome="meadow", asset_objects=None, water_level_m=None, max_instances=2000, seed=0, size_m=None):
    ob, meta = _terrain(name)
    span = float(size_m) if size_m is not None else meta["size_m"]
    if span > 200:
        raise C.FeatureError(f"an instance budget spread over {span:g} m reads sparse: 60-120 m reads lush; vegetate a smaller terrain")
    if biome not in BIOMES:
        raise C.FeatureError(f"biome is {' | '.join(BIOMES)}")
    protos = [C.need_object(n, "") for n in (asset_objects or [])]
    if not protos:
        raise C.FeatureError("give the vegetation assets: asset_objects (objects in the scene, e.g. placed from lampway_asset_search)")
    if not 1 <= int(max_instances) <= 50000:
        raise C.FeatureError("max_instances is 1..50000 (the viewport freezes past a few tens of thousands)")
    dg = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(ob, dg)
    s = meta["size_m"]
    want = min(int(max_instances), int(BIOMES[biome] * s * s))
    rng = np.random.default_rng(int(seed))
    level = float(water_level_m) if water_level_m is not None else -math.inf
    pts, tries = [], 0
    inv = ob.matrix_world.inverted()
    while len(pts) < want and tries < want * 6:
        tries += 1
        x, y = rng.uniform(-s / 2, s / 2, size=2)
        hit = tree.ray_cast(inv @ Vector((x, y, 1e4)), Vector((0, 0, -1)))
        if hit[0] is None:
            continue
        p = ob.matrix_world @ hit[0]
        slope = math.degrees(math.acos(max(-1.0, min(1.0, hit[1].z))))
        if p.z <= level or slope > MAX_SLOPE_DEG:
            continue
        pts.append(p)
    pname = f"{name}_veg"
    for o in [o for o in bpy.data.objects if o.name == pname]:
        bpy.data.objects.remove(o)
    me = bpy.data.meshes.new(pname)
    me.from_pydata([tuple(p) for p in pts], [], [])
    po = bpy.data.objects.new(pname, me)
    for c in ob.users_collection:
        c.objects.link(po)
    cname = f"{name}_veg_assets"
    coll = bpy.data.collections.get(cname) or bpy.data.collections.new(cname)
    for p in protos:
        if p.name not in coll.objects:
            coll.objects.link(p)
    g = bpy.data.node_groups.new(f"LW_Veg_{name}", "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go, info, inst, real = (g.nodes.new(t) for t in ("NodeGroupInput", "NodeGroupOutput", "GeometryNodeCollectionInfo", "GeometryNodeInstanceOnPoints", "GeometryNodeRealizeInstances"))
    info.inputs["Collection"].default_value = coll
    info.inputs["Separate Children"].default_value = True
    inst.inputs["Pick Instance"].default_value = True
    g.links.new(gi.outputs["Geometry"], inst.inputs["Points"])
    g.links.new(info.outputs["Instances"], inst.inputs["Instance"])
    g.links.new(inst.outputs["Instances"], go.inputs["Geometry"])
    g.nodes.remove(real)
    mod = po.modifiers.new("LW_Vegetation", "NODES")
    mod.node_group = g
    return {"objects": [po.name], "points_object": po.name, "biome": biome, "stats": {"instances": len(pts), "budget": int(max_instances), "tries": tries}}


def _blur(a, n=3):
    for _ in range(n):
        p = np.pad(a, 1, mode="edge")
        a = sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
    return a


def from_image(name, heightmap, size_m=100.0, resolution=256, height_m=10.0):
    _check_res(resolution, size_m)
    if not os.path.isfile(heightmap):
        raise C.FeatureError(f"{heightmap} is not a file")
    img = bpy.data.images.load(heightmap, check_existing=False)   # LEGACY(normalize): a heightmap read as luminance only; route through canon_io once it lands
    try:
        w, h = img.size
        px = np.array(img.pixels[:], dtype=np.float64).reshape(h, w, -1)[..., :3]
    finally:
        bpy.data.images.remove(img)
    top, bottom = px[int(h * 0.6):], px[:int(h * 0.4)]                       # Blender's rows run bottom-up
    if top[..., 2].mean() > top[..., 0].mean() + 0.1 and top.mean() > bottom.mean() + 0.15:
        raise C.FeatureError("this looks like a ground-level photo (a bright blue upper band): give a top-down height reference [UNVERIFIED heuristic]")
    if bpy.data.objects.get(name) is not None:
        raise C.FeatureError(f"an object named {name!r} exists: pick another name")
    lum = _blur(px.mean(axis=2))
    lum = (lum - lum.min()) / max(float(lum.max() - lum.min()), 1e-12)
    ob = _grid(name, float(size_m), int(resolution))
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    u = np.clip(((co[:, 0] / float(size_m)) + 0.5) * (w - 1), 0, w - 1).round().astype(int)
    v = np.clip(((co[:, 1] / float(size_m)) + 0.5) * (h - 1), 0, h - 1).round().astype(int)
    co[:, 2] = lum[v, u] * float(height_m)
    ob.data.vertices.foreach_set("co", co.ravel())
    ob.data.update()
    ob["lw_terrain"] = json.dumps({"preset": "from_image", "size_m": float(size_m), "resolution": int(resolution), "seed": 0, "height_m": float(height_m)})
    return {"objects": [ob.name], "stats": {"vertices": len(ob.data.vertices)}, "note": "blurred before displacement so 8-bit steps do not terrace"}


def terrain(root, action, resolve, **kw):
    if action not in ACTIONS:
        raise C.FeatureError(f"action is {' | '.join(ACTIONS)}; there is no erosion simulation, no sky and no real-world data import")
    name = kw.pop("name", None) or "LW_Terrain_1"
    if action == "heightfield":
        return heightfield(name, kw.get("preset") or "hills", kw.get("size_m") or 100.0, kw.get("resolution") or 256, kw.get("height_m"), kw.get("detail"),
                           kw.get("detail_scale"), kw.get("warp"), kw.get("seed") or 0)
    if action == "carve":
        return carve(name, kw.get("channel"), kw.get("basin"))
    if action == "water":
        return water(name, kw.get("water_level_m") or 0.0)
    if action == "vegetation":
        return vegetation(name, kw.get("biome") or "meadow", kw.get("asset_objects"), kw.get("water_level_m"), kw.get("max_instances") or 2000, kw.get("seed") or 0,
                          kw.get("size_m"))
    return from_image(name, resolve(kw.get("heightmap") or ""), kw.get("size_m") or 100.0, kw.get("resolution") or 256, kw.get("height_m") or 10.0)
