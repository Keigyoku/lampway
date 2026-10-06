# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_join_boolean (specs/wiki/mesh_join_boolean.md): fuse parts into one surface (join, then voxel remesh, coarse first), Boolean union / difference with a
clearance on an enlarged cutter, and plug/socket print connectors whose measured gap is the clearance. On copies. REAL binary."""

import json

from features_support import run

TWO = '''
a = boxes("a", [((0, 0, 0.5), (1.0, 1.0, 1.0))])
b = boxes("b", [((0, 0, 1.4), (0.6, 0.6, 1.0))])
'''


def _go(tmp_path, body):
    r = run(tmp_path, TWO + body, timeout=600)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_join_remesh_yields_one_shell(tmp_path):
    res = _go(tmp_path, '''
canon(*["a", "b"])
r = call("mesh_join_boolean", op="join_remesh", objects=["a", "b"], voxel_m="coarse_first")
print("RESULT", json.dumps({"r": r, "objects": sorted(o.name for o in bpy.data.objects)}))
''')
    r = res["r"]
    assert r["ok"] is True and r["shells"] == 1 and r["manifold"] is True and r["coarse"]["shells"] == 1, r
    assert {"a", "b"} <= set(res["objects"]), "the originals are kept"


def test_connector_gap_equals_clearance(tmp_path):
    res = _go(tmp_path, '''
out = {}
for c in (0.35, 0.0):
    for o in list(bpy.data.objects):
        if o.name not in ("a", "b"): bpy.data.objects.remove(o)
    canon(*["a", "b"])
    out[str(c)] = call("mesh_join_boolean", op="connector", objects=["a", "b"], clearance_mm=c, connector={"kind": "plug_socket", "at": [0, 0, 1.0], "size_mm": 40})
print("RESULT", json.dumps(out))
''')
    r = res["0.35"]
    assert r["ok"] is True and abs(r["gap_mm_measured"] - 0.35) < 0.05 and r["plug_object"] and r["socket_object"], r
    assert abs(res["0.0"]["gap_mm_measured"]) < 0.02, "the falsifier: clearance 0 gives gap 0"


def test_difference_with_clearance_cuts_a_larger_hole(tmp_path):
    res = _go(tmp_path, '''
canon(*["a", "b"])
r = call("mesh_join_boolean", op="difference", objects=["a", "b"], clearance_mm=1.0)
o = bpy.data.objects[r["object"]]
floor = min(v.co.z for v in o.data.vertices if abs(v.co.x) < 0.35 and abs(v.co.y) < 0.35 and v.co.z > 0.5)
wall = max(abs(v.co.x) for v in o.data.vertices if abs(v.co.x) < 0.45 and v.co.z > 0.95)
print("RESULT", json.dumps({"r": r, "floor": floor, "wall": wall}))
''')
    assert res["r"]["ok"] is True and res["r"]["manifold"] is True and res["r"]["clearance_mm"] == 1.0, res
    assert abs(res["floor"] - 0.899) < 1e-5 and abs(res["wall"] - 0.301) < 1e-5, "the pocket is the cutter grown by the clearance on every face"


def test_refusals(tmp_path):
    res = _go(tmp_path, '''
arm = bpy.data.armatures.new("rig"); rig = link(bpy.data.objects.new("rig", arm))
m = a.modifiers.new("Armature", "ARMATURE"); m.object = rig
canon(*["a", "b"])
skin = call("mesh_join_boolean", op="join_remesh", objects=["a", "b"])
a.modifiers.remove(m)
canon(*["a", "b"])
noclear = call("mesh_join_boolean", op="connector", objects=["a", "b"], connector={"kind": "plug_socket", "at": [0, 0, 1.0], "size_mm": 40})
me = bpy.data.meshes.new("open"); me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)]); link(bpy.data.objects.new("open", me))
canon(*["a", "open"])
openb = call("mesh_join_boolean", op="union", objects=["a", "open"])
print("RESULT", json.dumps({"skin": skin, "noclear": noclear, "open": openb}))
''')
    # a skinned mesh is not a canonical mesh: the door refuses it first and names the rigged normalizer (not built yet)
    assert res["skin"]["ok"] is False and res["skin"]["error"].startswith("normalize first") and "lampway_normalize_rigged" in res["skin"]["help"][0], res
    assert res["noclear"]["ok"] is False and "clearance is a printer/paint tolerance" in res["noclear"]["error"], res
    assert res["open"]["ok"] is False and "open edges" in res["open"]["error"], res
