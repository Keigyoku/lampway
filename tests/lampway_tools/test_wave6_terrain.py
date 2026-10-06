# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""terrain (specs/mixar_docs/terrain.md) in the real binary: a geometry-nodes heightfield on a grid (height, detail, warp and seed stay live), carving that commits
it to real vertices (a channel lowered to its depth, nothing outside its bank touched), a water plane, and instanced vegetation held to a budget."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

HASH = '''
import hashlib
def vhash(name):
    ev = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh(); co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get("co", co); ev.to_mesh_clear()
    return hashlib.sha256(co.tobytes()).hexdigest(), float(co[2::3].max() - co[2::3].min())
'''


def test_the_same_seed_gives_the_same_terrain_another_seed_another_and_the_height_scale_holds(tmp_path):
    d = one(go(tmp_path, HASH + '''
a = call("terrain", action="heightfield", name="t1", preset="hills", size_m=60, resolution=64, height_m=10, seed=1)
b = call("terrain", action="heightfield", name="t2", preset="hills", size_m=60, resolution=64, height_m=10, seed=1)
c = call("terrain", action="heightfield", name="t3", preset="hills", size_m=60, resolution=64, height_m=10, seed=2)
ha, za = vhash("t1"); hb, _ = vhash("t2"); hc, _ = vhash("t3")
mods = [m.type for m in bpy.data.objects["t1"].modifiers]
print("RESULT", json.dumps({"a": a, "same": ha == hb, "diff": ha != hc, "zrange": za, "mods": mods, "verts": len(bpy.data.objects["t1"].data.vertices)}))
'''))
    assert d["a"]["ok"] and d["a"]["modifier"] == "LW_Terrain" and d["mods"] == ["NODES"]
    assert d["same"] and d["diff"] and abs(d["zrange"] - 10) <= 1.0 and d["verts"] == 65 * 65


def test_carve_lowers_the_channel_to_its_depth_commits_and_leaves_the_rest_untouched(tmp_path):
    d = one(go(tmp_path, HASH + '''
call("terrain", action="heightfield", name="vale", preset="hills", size_m=60, resolution=64, height_m=6, seed=3)
ev = bpy.data.objects["vale"].evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
before = [tuple(v.co) for v in me.vertices]; ev.to_mesh_clear()
res = call("terrain", action="carve", name="vale", channel={"polyline": [[-30, 0], [30, 0]], "width_m": 6, "depth_m": 2, "bank_m": 3})
ob = bpy.data.objects["vale"]
after = [tuple(v.co) for v in ob.data.vertices]
inner = [(b[2] - a[2]) for a, b in zip(after, before) if abs(b[1]) <= 2.9]
outside = [abs(b[2] - a[2]) for a, b in zip(after, before) if abs(b[1]) >= 6.1]
print("RESULT", json.dumps({"res": res, "inner": inner, "outside": max(outside), "mods": [m.type for m in ob.modifiers]}))
'''))
    assert d["res"]["ok"] and d["res"]["committed"] is True and "commits" in d["res"]["warning"] and d["mods"] == []
    assert d["inner"] and all(abs(x - 2.0) <= 0.1 for x in d["inner"])                  # lowered by the depth, within 5 %
    assert d["outside"] == 0.0


def test_water_and_vegetation_within_the_instance_budget(tmp_path):
    d = one(go(tmp_path, '''
call("terrain", action="heightfield", name="isle", preset="hills", size_m=80, resolution=48, height_m=8, seed=5)
w = call("terrain", action="water", name="isle", water_level_m=2.0)
tree = sphere("tree", 0.5, subdiv=1)
veg = call("terrain", action="vegetation", name="isle", biome="forest", asset_objects=["tree"], water_level_m=2.0, max_instances=300, seed=7)
pts = bpy.data.objects[veg["points_object"]]
zs = [(pts.matrix_world @ v.co).z for v in pts.data.vertices]
wide = call("terrain", action="vegetation", name="isle", biome="forest", asset_objects=["tree"], size_m=400)
print("RESULT", json.dumps({"w": w, "veg": veg, "zmin": min(zs) if zs else None, "n": len(zs), "wide": wide,
                            "water_z": bpy.data.objects[w["object"]].location.z}))
'''))
    assert d["w"]["ok"] and abs(d["water_z"] - 2.0) < 1e-6
    veg = d["veg"]
    assert veg["ok"] and 0 < veg["stats"]["instances"] <= 300 and d["n"] == veg["stats"]["instances"]
    assert d["zmin"] > 2.0                                                              # nothing planted under the water
    assert d["wide"]["ok"] is False and "60-120 m reads lush" in d["wide"]["error"]


def test_the_resolution_cap_and_what_terrain_does_not_do_are_refused(tmp_path):
    d = one(go(tmp_path, '''
big = call("terrain", action="heightfield", name="big", resolution=2048)
erosion = call("terrain", action="erosion", name="e")
print("RESULT", json.dumps({"big": big, "erosion": erosion, "objects": [o.name for o in bpy.data.objects]}))
'''))
    assert d["big"]["ok"] is False and "capped at 1024 (a million vertices)" in d["big"]["error"]
    assert d["erosion"]["ok"] is False and "no erosion" in d["erosion"]["error"] and d["objects"] == []


def test_from_image_displaces_by_the_heightmap_and_refuses_a_ground_level_photo(tmp_path):
    d = one(go(tmp_path, '''
def png(name, px):
    h, w = px.shape[:2]
    img = bpy.data.images.new(name, w, h); img.pixels = px.astype(np.float32).ravel()
    img.filepath_raw = os.path.join(root, name + ".png"); img.file_format = "PNG"; img.save()
ramp = np.zeros((64, 64, 4)); ramp[..., 0] = ramp[..., 1] = ramp[..., 2] = np.linspace(0, 1, 64)[None, :]; ramp[..., 3] = 1
png("ramp", ramp)
photo = np.zeros((64, 64, 4)); photo[..., 3] = 1
photo[32:, :, :3] = 0.6                                         # the upper half of the image (Blender's rows run bottom-up): a bright blue sky
photo[32:, :, 2] = 0.95; photo[:32, :, :3] = [0.25, 0.3, 0.15]   # a dark green ground below
png("photo", photo)
res = call("terrain", action="from_image", name="hm", heightmap="ramp.png", size_m=50, resolution=64, height_m=8)
ob = bpy.data.objects["hm"]
zs = [v.co.z for v in ob.data.vertices]
sky = call("terrain", action="from_image", name="ph", heightmap="photo.png", size_m=50, resolution=64, height_m=8)
print("RESULT", json.dumps({"res": res, "zr": max(zs) - min(zs), "sky": sky}))
'''))
    assert d["res"]["ok"] and abs(d["zr"] - 8) < 0.5
    assert d["sky"]["ok"] is False and "top-down" in d["sky"]["error"]
