# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The PIECE_PIPELINE known gap 'QA candidate renders need a thicker highlight and cameras past occluders' (STATUS O32): a hole behind a plate must still be
seen in its review crop (the camera's near clip passes the occluder), and the highlight is several pixels wide. REAL binary: mesh_qa.py run as the batch tool."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from blender_run import run_script

ROOT = Path(__file__).resolve().parents[2]
MESH_QA = ROOT / "src/scripts/mixar/modules/lampway_tools/scripts/meshqa/mesh_qa.py"

BUILD = '''
import bpy, bmesh, json, numpy as np, os, sys
from mathutils import Matrix
out = sys.argv[sys.argv.index("--") + 1]
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 0.5)))
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=4, use_grid_fill=True)
bm.faces.ensure_lookup_table()
hole = [f for f in bm.faces if abs(f.calc_center_median().y + 0.5) < 1e-6 and abs(f.calc_center_median().x) < 0.05 and abs(f.calc_center_median().z - 0.5) < 0.05]
bmesh.ops.delete(bm, geom=hole, context="FACES_ONLY")
n_box = len(bm.faces)
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.6, matrix=Matrix.Translation((0, -0.8, 0.5)) @ Matrix.Rotation(1.5707963, 4, "X"))
me = bpy.data.meshes.new("piece"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("piece", me); bpy.context.scene.collection.objects.link(ob)
own = np.array([0] * n_box + [1] * (len(me.polygons) - n_box), dtype=np.int64)
np.save(os.path.join(out, "owner.npy"), own)
json.dump({"parts": {"body": {"class": "metal"}, "plate": {"class": "metal"}}}, open(os.path.join(out, "recipe.json"), "w"))
bpy.ops.export_scene.fbx(filepath=os.path.join(out, "piece.fbx"), use_selection=False)
print("RESULT", json.dumps({"faces": len(me.polygons), "box": n_box, "hole": len(hole)}))
'''

RUN_QA = f'''
import runpy, sys
runpy.run_path({str(MESH_QA)!r}, run_name="__main__")
'''


def test_a_hole_behind_a_plate_is_seen_in_its_crop_with_a_thick_highlight(tmp_path):
    b = run_script(BUILD, args=[str(tmp_path)])
    assert b.rc == 0 and b.results and b.results[0]["hole"] == 1, b.out[-2000:]
    out = tmp_path / "qa"
    r = run_script(RUN_QA, args=[str(tmp_path / "piece.fbx"), str(tmp_path / "owner.npy"), str(tmp_path / "recipe.json"), str(out), "--max-shell-tris", "1"], timeout=600)
    assert r.rc == 0, r.out[-3000:]
    cands = json.loads((out / "candidates.json").read_text())["candidates"]
    hole = next(c for c in cands if c["kind"] == "open_loop" and abs(c["centroid_m"][1] + 0.5) < 0.02 and abs(c["centroid_m"][2] - 0.5) < 0.05)
    assert hole["review_camera"]["clip_start_m"] > 0.4, hole["review_camera"]                 # past the plate 0.3 m in front of the hole
    a = np.asarray(Image.open(out / "img" / f"{hole['id']}.png").convert("RGB")).astype(int)
    yellow = (a[..., 0] > 200) & (a[..., 1] > 170) & (a[..., 2] < 90)
    assert yellow.sum() > 400, f"the highlight is hidden or thin: {yellow.sum()} yellow pixels"
    rows = yellow.any(axis=1).sum()
    cols_per_row = yellow.sum(axis=1)[yellow.any(axis=1)]
    assert np.median(cols_per_row) >= 3 or rows < 10, "a highlight several pixels wide"
