# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_defect_scan (specs/wiki/mesh_defect_scan.md): a read-only clay inspection that lists typed defect candidates (open loops, floating shells, self-intersections, thin features,
flipped shells, degenerate faces, isolated triangles) for the user's typed decisions. It never edits. Each kind has a falsifier: the same mesh with the defect removed reports none. REAL binary."""

import json
import os
from pathlib import Path

import pytest

from features_support import run

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
BOOT = SCR / "tripo_uv/Boots1/attempt_2.fbx"

HELP = '''
def tube(name, flip=False, closed=False, loc=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=closed, cap_tris=False, segments=24, radius1=0.5, radius2=0.5, depth=1.0)
    if flip: bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    return link(ob)

def counts(res): return res["counts"] if res["ok"] else res
'''


def scan(tmp_path, body):
    return run(tmp_path, HELP + body)


def test_two_overlapping_cubes_report_one_intersection_and_separate_cubes_none(tmp_path):
    r = scan(tmp_path, '''
a = boxes("hit", [((0, 0, 0), (1, 1, 1)), ((0.5, 0.5, 0.5), (1, 1, 1))])
b = boxes("apart", [((0, 0, 0), (1, 1, 1)), ((3, 0, 0), (1, 1, 1))])
print("RESULT", json.dumps({"hit": call("mesh_defect_scan", full=True, object="hit", kinds=["intersection"]), "apart": call("mesh_defect_scan", full=True, object="apart", kinds=["intersection"])}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["hit"]["counts"]["intersection"] == 1 and o["apart"]["counts"].get("intersection", 0) == 0
    c = o["hit"]["candidates"][0]
    assert c["kind"] == "intersection" and c["descriptor"]["faces"] >= 2 and len(c["descriptor"]["centroid"]) == 3 and c["rule_verdict"] == "ambiguous"


def test_a_reversed_open_cylinder_is_a_flipped_shell_and_the_right_way_out_one_is_not(tmp_path):
    r = scan(tmp_path, '''
tube("flipped", flip=True); tube("good", loc=(5, 0, 0))
print("RESULT", json.dumps({"f": call("mesh_defect_scan", full=True, object="flipped", kinds=["flipped_shell", "open_loop"]), "g": call("mesh_defect_scan", full=True, object="good", kinds=["flipped_shell", "open_loop"])}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["f"]["counts"]["flipped_shell"] == 1 and o["g"]["counts"].get("flipped_shell", 0) == 0
    assert o["f"]["counts"]["open_loop"] == 2 and all(c["descriptor"]["rim_length_m"] == pytest.approx(3.14, abs=0.1) for c in o["f"]["candidates"] if c["kind"] == "open_loop"), "both rims of a tube"


def test_a_strap_thinner_than_the_threshold_is_thin_and_a_thick_one_is_not(tmp_path):
    r = scan(tmp_path, '''
boxes("thin", [((0, 0, 0), (0.3, 0.3, 0.001))]); boxes("thick", [((0, 0, 0), (0.3, 0.3, 0.1))])
print("RESULT", json.dumps({"t": call("mesh_defect_scan", full=True, object="thin", kinds=["thin"]), "k": call("mesh_defect_scan", full=True, object="thick", kinds=["thin"]),
                            "loose": call("mesh_defect_scan", full=True, object="thin", kinds=["thin"], thin_threshold_m=0.0005)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["t"]["counts"]["thin"] >= 1 and o["k"]["counts"].get("thin", 0) == 0 and o["loose"]["counts"].get("thin", 0) == 0, "the threshold decides"


def test_floating_shells_degenerate_faces_and_isolated_triangles(tmp_path):
    r = scan(tmp_path, '''
body = boxes("m", [((0, 0, 0), (1, 1, 1)), ((2.0, 0, 0), (0.05, 0.05, 0.05))])                  # a tiny cube floating 1.5 m from the body
bm = bmesh.new(); bm.from_mesh(body.data)
v = [bm.verts.new(p) for p in ((5, 5, 5), (5.1, 5, 5), (5, 5.1, 5))]; bm.faces.new(v)                  # one isolated triangle
d1, d2, d3 = [bm.verts.new(p) for p in ((8, 0, 0), (9, 0, 0), (10, 0, 0))]; bm.faces.new((d1, d2, d3))        # a zero-area (collinear) triangle
bm.to_mesh(body.data); bm.free()
res = call("mesh_defect_scan", full=True, object="m", kinds=["floating_shell", "degenerate", "isolated_tri"])
clean = boxes("c", [((0, 0, 0), (1, 1, 1))])
print("RESULT", json.dumps({"res": res, "clean": call("mesh_defect_scan", full=True, object="c"), "trunc": call("mesh_defect_scan", full=True, object="m", max_candidates=1)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    cnt = o["res"]["counts"]
    assert cnt["floating_shell"] >= 1 and cnt["degenerate"] >= 1 and cnt["isolated_tri"] >= 2, cnt
    assert o["clean"]["counts"] == {} and o["clean"]["candidates"] == [], "a clean closed cube: every kind returns zero (the falsifier for the whole scan)"
    assert o["trunc"]["truncated"] is True and len(o["trunc"]["candidates"]) == 1 and o["trunc"]["total"] > 1
    assert any(c["rule_verdict"] == "delete" for c in o["res"]["candidates"] if c["kind"] in ("degenerate", "floating_shell"))


def test_the_scan_never_edits_the_mesh_and_refuses_what_it_cannot_read(tmp_path):
    r = scan(tmp_path, '''
ob = boxes("m", [((0, 0, 0), (1, 1, 1)), ((0.5, 0.5, 0.5), (1, 1, 1))])
before = (len(ob.data.vertices), len(ob.data.polygons), [tuple(v.co) for v in ob.data.vertices][:5])
res = call("mesh_defect_scan", full=True, object="m")
after = (len(ob.data.vertices), len(ob.data.polygons), [tuple(v.co) for v in ob.data.vertices][:5])
empty = bpy.data.objects.new("e", bpy.data.meshes.new("e")); link(empty)
print("RESULT", json.dumps({"same": before == after, "e": call("mesh_defect_scan", full=True, object="e"), "k": call("mesh_defect_scan", full=True, object="m", kinds=["nonsense"]), "t": call("mesh_defect_scan", full=True, object="m", thin_threshold_m=1)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["same"] is True and "no faces" in o["e"]["error"] and "nonsense" in o["k"]["error"] and "0.0001" in o["t"]["error"]


@pytest.mark.skipif(not BOOT.exists(), reason="the shelf's Boots1 Smart UV attempt is not on this machine")
def test_the_real_boots1_attempt_is_scanned_in_bounded_time(tmp_path):
    import shutil
    import time
    shutil.copy(BOOT, tmp_path / "boot.fbx")
    t0 = time.time()
    r = scan(tmp_path, '''
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=root + "/boot.fbx")
ob = next(o for o in bpy.data.objects if o.type == "MESH")
res = call("mesh_defect_scan", full=True, object=ob.name, kinds=["open_loop", "floating_shell", "intersection", "flipped_shell", "degenerate", "isolated_tri"], max_candidates=500)
print("RESULT", json.dumps({"counts": res["counts"], "total": res["total"], "faces": len(ob.data.polygons)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["faces"] == 27753 and o["total"] >= 0 and time.time() - t0 < 300, o
    print("boots1 attempt_2 counts", o["counts"])


def test_defect_default_reply_is_bounded_and_pages_keep_true_totals(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
me=bpy.data.meshes.new('triangles')
verts=[]; faces=[]
for i in range(160):
    n=len(verts); verts.extend([(i*2,0,0),(i*2+1,0,0),(i*2,1,0)]); faces.append((n,n+1,n+2))
me.from_pydata(verts,[],faces)
ob=bpy.data.objects.new('many',me); bpy.context.collection.objects.link(ob)
a=call('mesh_defect_scan',object='many',kinds=['isolated_tri'])
b=call('mesh_defect_scan',object='many',kinds=['isolated_tri'],offset=50,limit=10,full=True)
print('RESULT '+json.dumps({'a':a,'b':b,'bytes':len(json.dumps(a).encode())}))
''')[0]
    assert out['a']['ok'], out
    assert out['a']['total'] == 160
    assert len(out['a']['candidates']) == 50
    assert out['bytes'] < 12000
    assert out['b']['ok'] and len(out['b']['candidates']) == 10
    assert out['b']['candidates'][0]['id'] == 'isolated_tri-50'
    assert 'descriptor' in out['b']['candidates'][0]
