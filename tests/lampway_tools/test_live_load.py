# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Load a rebuild into the live scene beside the previous one (the shelf's meshqa/load_live.py): import the patched UV
mesh, put it in the live frame (turned about Z to the -Y front, lifted to stand on the floor), copy the textured
material from the template with its mask and height images pointed at the rebuild's directory, hide the previous. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, json, os, math
import numpy as np
from mixar.modules.lampway_tools import live_load as LL
work = WORK
os.makedirs(work + "/masks", exist_ok=True)
# a rebuild: a mesh with its x axis along the model's old front, written as FBX, and a masks directory
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2, 0, 0))
bpy.context.object.name = "scratch_cube"
bpy.ops.export_scene.fbx(filepath=work + "/rebuild.fbx", use_selection=True)
bpy.data.objects.remove(bpy.data.objects["scratch_cube"])
for n in ("mask_plate.png", "mask_gold.png", "detail_height_u16.png"):
    im = bpy.data.images.new(n, 4, 4); im.filepath_raw = work + "/masks/" + n; im.file_format = "PNG"; im.save()
    bpy.data.images.remove(im)
# the live scene: a previous version and a template material whose image nodes point at the OLD masks
os.makedirs(work + "/old", exist_ok=True)
prev = bpy.data.objects.new("chest_p9_textured", bpy.data.meshes.new("p9")); bpy.context.scene.collection.objects.link(prev)
tm = bpy.data.materials.new("textured_p9"); tm.use_nodes = True
for n in ("mask_plate.png", "mask_gold.png", "detail_height_u16.png"):
    im = bpy.data.images.new(n, 4, 4); im.filepath_raw = work + "/old/" + n; im.file_format = "PNG"; im.save()
    node = tm.node_tree.nodes.new("ShaderNodeTexImage"); node.image = bpy.data.images.load(work + "/old/" + n)
other = tm.node_tree.nodes.new("ShaderNodeTexImage"); other.image = bpy.data.images.new("colour_tile.png", 4, 4)
'''


def run(tmp_path, body):
    return run_script(PRE.replace("WORK", repr(str(tmp_path))) + body)


def test_the_rebuild_arrives_textured_in_the_live_frame_with_its_own_masks(tmp_path):
    r = run(tmp_path, '''
res = LL.load_rebuild(work + "/rebuild.fbx", work + "/masks", "chest_p10_textured", "textured_p9", hide=["chest_p9_textured"], lift=0.5)
ob = bpy.data.objects["chest_p10_textured"]
xs = [v.co.x for v in ob.data.vertices]; ys = [v.co.y for v in ob.data.vertices]; zs = [v.co.z for v in ob.data.vertices]
m = ob.data.materials[0]
imgs = {os.path.basename(n.image.filepath): os.path.dirname(bpy.path.abspath(n.image.filepath)) for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and n.image.filepath}
print("RESULT", json.dumps({"res": res, "x": [round(min(xs), 2), round(max(xs), 2)], "y": [round(min(ys), 2), round(max(ys), 2)], "z": [round(min(zs), 2), round(max(zs), 2)],
    "mat": m.name, "imgs": {k: v for k, v in imgs.items()}, "colourspace": bpy.data.images[[n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and "mask_plate" in n.image.name][0]].colorspace_settings.name,
    "prev_hidden": [bpy.data.objects["chest_p9_textured"].hide_get(), bpy.data.objects["chest_p9_textured"].hide_render],
    "template_untouched": bpy.data.materials["textured_p9"].name, "n_obj": len(bpy.data.objects)}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["res"]["name"] == "chest_p10_textured" and res["res"]["material"] == "textured_chest_p10_textured"
    # the cube sat at x = 2 (1 m wide): turned -90 about Z it sits at y = -2 (x -> -y), lifted 0.5 in z; origin baked
    assert res["y"] == [-2.5, -1.5] and res["z"] == [0.0, 1.0] and res["x"] == [-0.5, 0.5]
    assert res["mat"] == "textured_chest_p10_textured"
    assert res["imgs"]["mask_plate.png"].endswith("/masks") and res["imgs"]["detail_height_u16.png"].endswith("/masks")
    assert res["colourspace"] == "Non-Color"
    assert res["prev_hidden"] == [True, True]


def test_a_missing_template_is_refused_with_the_materials_that_exist(tmp_path):
    r = run(tmp_path, '''
OBJECTS_BEFORE = set(o.name for o in bpy.data.objects)
try:
    LL.load_rebuild(work + "/rebuild.fbx", work + "/masks", "x", "no_such", lift=0.0); out = "no error"
except LookupError as e:
    out = str(e)
print("RESULT", json.dumps({"msg": out, "new_objects": sorted(set(o.name for o in bpy.data.objects) - OBJECTS_BEFORE)}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "no_such" in r.results[0]["msg"] and "textured_p9" in r.results[0]["msg"]
    assert r.results[0]["new_objects"] == []                    # nothing was imported before the refusal


def test_a_missing_mask_image_is_refused_before_anything_is_imported(tmp_path):
    r = run(tmp_path, '''
os.remove(work + "/masks/mask_gold.png")
OBJECTS_BEFORE = set(o.name for o in bpy.data.objects)
try:
    LL.load_rebuild(work + "/rebuild.fbx", work + "/masks", "x", "textured_p9"); out = "no error"
except FileNotFoundError as e:
    out = str(e)
print("RESULT", json.dumps({"msg": out, "new_objects": sorted(set(o.name for o in bpy.data.objects) - OBJECTS_BEFORE)}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "mask_gold.png" in r.results[0]["msg"] and r.results[0]["new_objects"] == []
