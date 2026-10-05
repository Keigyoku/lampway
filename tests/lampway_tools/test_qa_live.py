# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA in the live scene: compute candidates on an object, draw them, read the captain's tags back into
decisions and rulings. The scene is a sphere with a hole and a floating cube, lifted 0.5 m like his live chest
(candidates are stored in the mesh's own frame; the live frame is that plus ``offset``). REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

SCENE = '''
import bpy, bmesh, json, math, os
import numpy as np
from mathutils import Vector, Matrix
from mixar.modules.lampway_tools.meshqa import live as L, decisions as D

work = ARGS_DIR
me = bpy.data.meshes.new("piece")
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.3)
bm.faces.ensure_lookup_table()
cut = [f for f in bm.faces if math.degrees(f.calc_center_median().angle(Vector((1, 0, 0)))) < 25]
bmesh.ops.delete(bm, geom=cut, context="FACES_ONLY")
bmesh.ops.create_cube(bm, size=0.05, matrix=Matrix.Translation((0, 0, 0.345)))
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("piece", me); ob.location = (0, 0, 0.5)
bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.update()                  # a script-made object has no world matrix until the depsgraph runs
n = len(me.polygons)
cube_polys = [p.index for p in me.polygons if p.center.z > 0.31]
os.makedirs(work, exist_ok=True)
json.dump({"parts": {"top": {"class": "rigid-metal"}, "bottom": {"class": "cloth-sim"}}}, open(work + "/recipe.json", "w"))
np.save(work + "/owner.npy", np.array([0 if p.center.z >= 0 else 1 for p in me.polygons]))
cfg = L.QAConfig(object="piece", recipe=work + "/recipe.json", owner=work + "/owner.npy", rulings_dir=work + "/rulings",
                 piece="demo", session="s1", offset=(0, 0, 0.5))
'''


def run(tmp_path, body, **kw):
    return run_script(SCENE.replace("ARGS_DIR", repr(str(tmp_path))) + body, **kw)


def test_compute_writes_candidates_in_the_mesh_frame(tmp_path):
    run_ = run(tmp_path, '''
rep = L.compute_candidates(cfg)
d = json.load(open(rep["path"]))
print("RESULT", json.dumps({"rep": rep, "ids": [c["id"] for c in d["candidates"]], "loop_z": [c["centroid_m"][2] for c in d["candidates"] if c["kind"] == "open_loop"],
                             "keys": sorted(k for k in d if k != "candidates")}))
''')
    assert run_.rc == 0, run_.out[-2500:]
    res = run_.results[0]
    assert res["ids"] == ["L000", "S000"] and res["rep"]["open_loops"] == 1 and res["rep"]["loose_shells"] == 1
    assert abs(res["loop_z"][0]) < 0.02                         # the hole is on the equator: z ~ 0 in the mesh's frame, not 0.5
    assert {"mesh", "owner", "recipe", "turn", "frame", "offset"} <= set(res["keys"])


def test_draw_replaces_its_own_collection_each_time(tmp_path):
    run_ = run(tmp_path, '''
L.compute_candidates(cfg)
a = L.draw_candidates(cfg)
b = L.draw_candidates(cfg)
col = bpy.data.collections["QA_candidates"]
labels = sorted(o.name for o in col.objects if o.name.endswith("_label"))
z = [round(o.location.z, 2) for o in col.objects if o.name == "L000_label"]
print("RESULT", json.dumps({"a": a, "b": b, "n": len(col.objects), "labels": labels, "label_z_lifted": z[0] > 0.45}))
''')
    assert run_.rc == 0, run_.out[-2500:]
    res = run_.results[0]
    assert res["a"]["drawn"] == res["b"]["drawn"] == 2 and res["n"] == 4 and res["labels"] == ["L000_label", "S000_label"]
    assert res["label_z_lifted"] is True                        # drawn at the live position: mesh frame + offset


def test_tags_become_decisions_and_rulings(tmp_path):
    run_ = run(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import marks as M
rep0 = L.compute_candidates(cfg)
d = json.load(open(rep0["path"]))
loop = next(c for c in d["candidates"] if c["kind"] == "open_loop")
ann = M.create_tag_layers()
def stroke(layer, pts):
    lay = ann.layers[layer]; fr = lay.frames[0] if len(lay.frames) else lay.frames.new(0)
    s = fr.strokes.new(); s.points.add(len(pts))
    for p, c in zip(s.points, pts): p.co = c
along = [tuple(np.array(seg[0]) + np.array((0, 0, 0.5))) for seg in loop["segments_m"]]
stroke("Hole", along)
stroke("Delete", [(0.0, 0.0, 0.845), (0.01, 0.0, 0.845), (0.0, 0.01, 0.845)])
rep = L.read_tags(cfg, apply=True)
rows = D.read_rows(os.path.join(work, "rulings", "decisions.jsonl"))
dele = json.load(open(os.path.join(work, "rulings", "demo_deletions.json")))
print("RESULT", json.dumps({"rep": rep, "answers": D.latest_answers(rows), "shells": D.latest_answers(rows, kind="loose_shell"),
                             "deleted": dele["polys"], "cube_polys": cube_polys}))
''')
    assert run_.rc == 0, run_.out[-2500:]
    res = run_.results[0]
    assert res["answers"] == {"L000": "hole"}
    assert res["shells"] == {"S000": "delete"}
    assert res["deleted"] == sorted(res["cube_polys"])
    rep = res["rep"]
    assert rep["strokes"] == {"delete": 1, "mislabel": 0, "hole": 1}
    assert rep["hole_loops"] == ["L000"] and rep["orphans"] == [] and rep["deleted"] == 6 and rep["shells"] == ["S000"]


def test_reading_the_tags_twice_does_not_duplicate_rulings(tmp_path):
    run_ = run(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import marks as M
L.compute_candidates(cfg)
ann = M.create_tag_layers()
lay = ann.layers["Delete"]; fr = lay.frames.new(0); s = fr.strokes.new(); s.points.add(2)
s.points[0].co = (0, 0, 0.845); s.points[1].co = (0.01, 0, 0.845)
L.read_tags(cfg, apply=True); L.read_tags(cfg, apply=True)
dele = json.load(open(os.path.join(work, "rulings", "demo_deletions.json")))
print("RESULT", json.dumps({"decisions": len(dele["decisions"]), "polys": len(dele["polys"])}))
''')
    assert run_.rc == 0, run_.out[-2500:]
    assert run_.results == [{"decisions": 1, "polys": 6}]


def test_skip_strokes_leaves_earlier_marks_alone(tmp_path):
    run_ = run(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import marks as M
L.compute_candidates(cfg)
ann = M.create_tag_layers()
lay = ann.layers["Delete"]; fr = lay.frames.new(0)
for x in (0.0, 0.2):
    s = fr.strokes.new(); s.points.add(2); s.points[0].co = (x, 0, 0.845); s.points[1].co = (x + 0.01, 0, 0.845)
cfg.skip_strokes = {"delete": 1, "mislabel": 0, "hole": 0}
rep = L.read_tags(cfg, apply=False)
print("RESULT", json.dumps({"strokes": rep["strokes"]}))
''')
    assert run_.rc == 0, run_.out[-2500:]
    assert run_.results == [{"strokes": {"delete": 1, "mislabel": 0, "hole": 0}}]
