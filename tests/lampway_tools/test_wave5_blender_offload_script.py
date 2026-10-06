# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Blender-offload job's script (server/lampway_server/compute/assets/offload.py): headless Blender bakes, thumbnails and silhouettes, run on a rented box through the compute wrapper. Here it runs in the
real binary (the same bpy API the box gets from `pip install bpy`); the unit under test is the script's contract: what it reads, what it writes, and that it refuses what it cannot do."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parents[2] / "server/lampway_server/compute/assets/offload.py")

PRE = f'''
import bpy, bmesh, json, os, runpy, sys
SCRIPT = {SCRIPT!r}
def make_input(root, params):
    os.makedirs(root + "/in", exist_ok=True); os.makedirs(root + "/out", exist_ok=True)
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.5)
    me = bpy.data.meshes.new("ball"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("ball", me); bpy.context.scene.collection.objects.link(ob)
    bpy.ops.export_scene.gltf(filepath=root + "/in/ball.glb")
    json.dump(params, open(root + "/in/params.json", "w"))
def offload(root):
    sys.argv = ["offload.py", root + "/in", root + "/out"]
    runpy.run_path(SCRIPT, run_name="__main__")
    return json.load(open(root + "/out/result.json"))
'''


def go(tmp_path, body):
    return run(tmp_path, PRE + body)


def test_thumbnail_and_silhouette_write_their_images_and_a_result(tmp_path):
    r = go(tmp_path, f'''
root = {str(tmp_path / "box")!r}
make_input(root, {{"op": "thumbnail", "size": 64}})
res = offload(root)
print("RESULT", json.dumps({{"res": res, "files": sorted(os.listdir(root + "/out"))}}))
make_input(root, {{"op": "silhouette", "size": 64, "yaw_deg": 90}})
res2 = offload(root)
from PIL import Image
im = Image.open(root + "/out/silhouette.png")
print("RESULT", json.dumps({{"res": res2, "mode": im.mode, "size": list(im.size)}}))
''')
    assert r.rc == 0, r.out[-2500:]
    a, b = r.results
    assert a["res"]["op"] == "thumbnail" and a["res"]["faces"] > 100 and "thumbnail.png" in a["files"] and a["res"]["image"] == "thumbnail.png"
    assert b["res"]["op"] == "silhouette" and 0.3 < b["res"]["alpha_coverage"] < 0.9 and b["size"] == [64, 64]
    # a sphere of radius 0.5 framed with margin: its disc covers about pi/4 of a tight square, less with the margin


def test_bake_ao_writes_an_ao_image_and_an_unknown_op_or_a_missing_model_fails_loud(tmp_path):
    r = go(tmp_path, f'''
root = {str(tmp_path / "box")!r}
make_input(root, {{"op": "bake_ao", "size": 64, "samples": 4}})
res = offload(root)
out = {{"res": res, "files": sorted(os.listdir(root + "/out"))}}
make_input(root, {{"op": "mine_bitcoin"}})
try:
    offload(root); out["unknown"] = "no error"
except SystemExit as e:
    out["unknown"] = str(e.code)
os.remove(root + "/in/ball.glb")
json.dump({{"op": "thumbnail"}}, open(root + "/in/params.json", "w"))
try:
    offload(root); out["missing"] = "no error"
except SystemExit as e:
    out["missing"] = str(e.code)
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["res"]["op"] == "bake_ao" and "ao.png" in d["files"] and d["res"]["image"] == "ao.png" and 0.0 <= d["res"]["mean_ao"] <= 1.0
    assert "unknown op" in d["unknown"] and "no model" in d["missing"]
