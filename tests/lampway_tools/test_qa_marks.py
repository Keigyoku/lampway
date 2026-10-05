# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The user's annotation tags, read into faces, islands and loops.

He tags with three annotation layers drawn with placement Surface (points on the mesh):
  Red = Delete, Green = Mislabel, Yellow = Hole.
A stroke's faces are the faces nearest its points; the islands are the Smart UV islands those faces sit in
(UV-connected corners); a Hole stroke names the open-loop candidates it circles or runs along. Synthetic cases run
in the REAL binary; the recorded-run check replays his own marks against the shelf's live scene."""

import os
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

GRID = '''
import bpy, bmesh, json, math
import numpy as np
from mathutils import Matrix
from mixar.modules.lampway_tools.meshqa import marks as M

# a 10x10 grid in the XY plane (cell 0.1 m, spanning -0.5..0.5), UVs in two islands split at x = 0
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=0.5)
uv = bm.loops.layers.uv.new("UVMap")
for f in bm.faces:
    left = f.calc_center_median().x < 0
    for l in f.loops:
        x, y = l.vert.co.x, l.vert.co.y
        l[uv].uv = ((x + 0.5) * 0.4, y + 0.5) if left else (0.6 + x * 0.4, y + 0.5)
me = bpy.data.meshes.new("grid"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("grid", me); bpy.context.scene.collection.objects.link(ob)

def cell(x, y):
    """polygon index of the cell containing (x, y)"""
    for p in me.polygons:
        c = p.center
        if abs(c.x - x) < 0.05 and abs(c.y - y) < 0.05:
            return p.index

def add_stroke(layer, pts):
    ann = bpy.data.annotations.get("Annotations") or bpy.data.annotations.new("Annotations")
    bpy.context.scene.annotation = ann
    lay = ann.layers.get(layer) or ann.layers.new(layer)
    fr = lay.frames[0] if len(lay.frames) else lay.frames.new(0)
    s = fr.strokes.new(); s.points.add(len(pts))
    for p, c in zip(s.points, pts):
        p.co = c
    return s
'''


def test_tag_layers_are_read_by_name_and_by_colour():
    run = run_script(GRID + '''
add_stroke("Delete", [(0, 0, 0), (0.1, 0, 0)])
add_stroke("Hole", [(0.2, 0, 0), (0.3, 0, 0)])
ann = bpy.data.annotations["Annotations"]
ann.layers.new("lime").color = (0.0, 0.78, 0.004)           # unnamed, but green
ann.layers.new("Note").color = (0.4, 0.6, 0.8)              # the stock note layer: not a tag
lime = ann.layers["lime"]; fr = lime.frames.new(0); s = fr.strokes.new(); s.points.add(2)
s.points[0].co = (0.3, 0.3, 0); s.points[1].co = (0.4, 0.3, 0)
tags = M.read_tags(ann)
print("RESULT", json.dumps({k: [len(s.points) for s in v] for k, v in tags.items()}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"delete": [2], "mislabel": [2], "hole": [2]}]


def test_a_strokes_faces_are_the_faces_nearest_its_points_in_order_without_repeats():
    run = run_script(GRID + '''
s = add_stroke("Delete", [(-0.35, 0.05, 0.0), (-0.32, 0.05, 0.0), (-0.15, 0.05, 0.0), (-0.15, 0.15, 0.001)])
surf = M.Surface(ob)
faces = surf.faces_for(np.array([p.co[:] for p in s.points]))
print("RESULT", json.dumps({"faces": faces, "want": [cell(-0.35, 0.05), cell(-0.15, 0.05), cell(-0.15, 0.15)]}))
''')
    assert run.rc == 0, run.out[-2500:]
    res = run.results[0]
    assert res["faces"] == res["want"]


def test_a_point_far_from_the_mesh_is_not_a_face():
    run = run_script(GRID + '''
surf = M.Surface(ob)
faces = surf.faces_for(np.array([(0, 0, 0.5), (0.25, 0.25, 0.0)]), max_dist_m=0.02)
print("RESULT", json.dumps({"faces": faces, "want": [cell(0.25, 0.25)]}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results[0]["faces"] == run.results[0]["want"]


def test_uv_islands_follow_the_uv_seam_not_the_3d_connectivity():
    run = run_script(GRID + '''
isl = M.uv_islands(me)
print("RESULT", json.dumps({"n": int(isl.max()) + 1, "left": sorted({int(isl[cell(-0.25, y)]) for y in np.arange(-0.45, 0.5, 0.1)}),
                             "right": sorted({int(isl[cell(0.25, y)]) for y in np.arange(-0.45, 0.5, 0.1)}),
                             "seam_pair_differs": bool(isl[cell(-0.05, 0.05)] != isl[cell(0.05, 0.05)])}))
''')
    assert run.rc == 0, run.out[-2500:]
    res = run.results[0]
    assert res["n"] == 2 and len(res["left"]) == 1 and len(res["right"]) == 1 and res["left"] != res["right"]
    assert res["seam_pair_differs"] is True


def test_interpret_gives_faces_islands_and_the_share_of_each_island_touched():
    run = run_script(GRID + '''
add_stroke("Mislabel", [(-0.25, y, 0.0) for y in np.arange(-0.45, 0.46, 0.1)])      # a stripe down the left island
tagged = M.interpret(M.read_tags(), ob)
ml = tagged["mislabel"]
print("RESULT", json.dumps({"strokes": len(ml), "faces": len(ml[0]["faces"]), "islands": ml[0]["islands"],
                             "touch": ml[0]["island_touch"]}))
''')
    assert run.rc == 0, run.out[-2500:]
    res = run.results[0]
    assert res["strokes"] == 1 and res["faces"] == 10 and len(res["islands"]) == 1
    assert list(res["touch"].values()) == [pytest.approx(10 / 50)]                  # 10 of the island's 50 faces


def test_a_hole_stroke_names_the_loops_it_runs_along_and_the_ones_it_circles():
    run = run_script(GRID + '''
# candidate loops, as mesh_qa writes them: L000 sits under the stroke, L001 is circled by it, L002 is elsewhere
def loop(cid, pts):
    segs = [[list(a), list(b)] for a, b in zip(pts, pts[1:] + pts[:1])]
    return {"id": cid, "kind": "open_loop", "segments_m": segs, "centroid_m": list(np.mean(pts, axis=0))}
L0 = loop("L000", [(0.30, -0.30, 0), (0.35, -0.30, 0), (0.35, -0.35, 0), (0.30, -0.35, 0)])
L1 = loop("L001", [(-0.30, 0.30, 0), (-0.25, 0.30, 0), (-0.25, 0.35, 0), (-0.30, 0.35, 0)])
L2 = loop("L002", [(0.40, 0.40, 0), (0.45, 0.40, 0), (0.45, 0.45, 0), (0.40, 0.45, 0)])
circle = [(-0.275 + 0.08 * math.cos(t), 0.325 + 0.08 * math.sin(t), 0.0) for t in np.linspace(0, 2 * math.pi, 40)]
add_stroke("Hole", [(0.30, -0.30, 0), (0.32, -0.30, 0), (0.34, -0.30, 0)])
add_stroke("Hole", circle)
tagged = M.interpret(M.read_tags(), ob, candidates=[L0, L1, L2])
hs = tagged["hole"]
print("RESULT", json.dumps([{"loops": h["loops"]} for h in hs]))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [[{"loops": {"L000": "along"}}, {"loops": {"L001": "circled"}}]]


def test_a_hole_stroke_that_meets_no_candidate_is_an_orphan_finding():
    run = run_script(GRID + '''
add_stroke("Hole", [(0.0, 0.0, 0), (0.05, 0.0, 0), (0.1, 0.0, 0)])
tagged = M.interpret(M.read_tags(), ob, candidates=[])
h = tagged["hole"][0]
print("RESULT", json.dumps({"loops": h["loops"], "orphan": h["orphan"], "centre": [round(x, 3) for x in h["centre_m"]]}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"loops": {}, "orphan": True, "centre": [0.05, 0.0, 0.0]}]


def test_the_marks_json_shape_matches_the_shelfs_exports():
    run = run_script(GRID + '''
add_stroke("Hole", [(0, 0, 0), (0.1, 0, 0)])
d = M.export_marks(bpy.data.annotations["Annotations"])
print("RESULT", json.dumps({"keys": sorted(d), "view": len(d["view"]["view_matrix"]), "layer_keys": sorted(d["layers"][0]), "layer": d["layers"][0]["layer"], "n": d["layers"][0]["n"], "pts": len(d["layers"][0]["strokes"][0])}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"keys": ["layers", "view"], "view": 4, "layer_keys": ["color", "gp", "layer", "n", "strokes"], "layer": "Hole", "n": 1, "pts": 2}]


def test_create_tag_layers_makes_the_three_with_the_captains_colours():
    run = run_script(GRID + '''
ann = M.create_tag_layers()
print("RESULT", json.dumps({l.info: [round(c, 3) for c in l.color] for l in ann.layers}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"Delete": [0.78, 0.074, 0.106], "Mislabel": [0.0, 0.78, 0.004], "Hole": [0.78, 0.738, 0.041]}]


SHELF = Path(os.environ.get("LAMPWAY_SHELF") or "/nonexistent") / "tex_r7/v8"   # the owner's recorded runs; unset = skipped
MARKS = SHELF / "captain_marks" / "marks_2026-10-04_tagged.json"
FACES = SHELF / "captain_marks" / "tagged_faces.json"
SCENE = SHELF / "textured_scene.blend"


@pytest.mark.skipif(not (MARKS.exists() and SCENE.exists()), reason="the shelf's live scene and marks are not on this machine")
def test_his_own_marks_give_the_face_counts_he_recorded(tmp_path):
    import shutil
    scene = tmp_path / "scene_copy.blend"                       # never the user's file: a copy
    shutil.copy(SCENE, scene)
    run = run_script(f'''
import bpy, json
import numpy as np
from mixar.modules.lampway_tools.meshqa import marks as M
d = json.load(open({str(MARKS)!r}))
ann = M.create_tag_layers()
for L in d["layers"]:
    lay = ann.layers[L["layer"]]
    fr = lay.frames[0] if len(lay.frames) else lay.frames.new(0)
    for pts in L["strokes"]:
        s = fr.strokes.new(); s.points.add(len(pts))
        for p, c in zip(s.points, pts):
            p.co = c
tagged = M.interpret(M.read_tags(ann), bpy.data.objects["chest_patched_p6"])
print("RESULT", json.dumps({{t: [len(r["faces"]) for r in rows] for t, rows in tagged.items()}}))
''', scene=scene)
    assert run.rc == 0, run.out[-2500:]
    got = run.results[0]
    want = {}
    for r in json.load(open(FACES)):
        want.setdefault(r["tag"].lower(), []).append(len(r["faces"]))
    assert set(got) == set(want)
    for tag, counts in want.items():
        assert len(got[tag]) == len(counts), tag
        for g, w in zip(got[tag], counts):
            assert abs(g - w) <= 1, (tag, got[tag], counts)
