# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lod_chain (specs/wiki/lod_chain.md) in the real binary: LOD copies by collapse decimation with a protected vertex group and UV seams kept, each measured (faces,
the deviation from the source, the silhouette IoU, a weight audit when skinned), textures downsized per LOD; the visual approval alone is not a measurement."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

BUMPY = '''
def bumpy(name="piece", subdiv=5):
    """A dense sphere with ridges (so decimation has something to lose) and a protected cap group 'emblem' (z > 0.35)."""
    ob = sphere(name, 0.5, subdiv=subdiv)
    for v in ob.data.vertices:
        d = v.co.normalized()
        v.co = d * (0.5 + 0.03 * math.sin(14 * d.x) * math.cos(11 * d.y))
    g = ob.vertex_groups.new(name="emblem")
    g.add([v.index for v in ob.data.vertices if v.co.z > 0.35], 1.0, "REPLACE")
    return ob
'''


def test_face_counts_follow_ratios_within_10_percent_and_deviation_grows(tmp_path):
    d = one(go(tmp_path, BUMPY + '''
ob = bumpy()
n0 = len(ob.data.polygons)
canon("piece")
res = call("lod_chain", object="piece", ratios=[0.5, 0.25, 0.1])
print("RESULT", json.dumps({"res": res, "n0": n0, "src": len(bpy.data.objects["piece"].data.polygons)}))
'''))
    res, n0 = d["res"], d["n0"]
    assert res["ok"], res
    assert [l["object"] for l in res["lods"]] == ["piece_LOD1", "piece_LOD2", "piece_LOD3"] and d["src"] == n0
    for lod, r in zip(res["lods"], (0.5, 0.25, 0.1)):
        assert abs(lod["faces"] - r * n0) <= 0.1 * r * n0, (lod, r * n0)
    devs = [l["max_deviation_rel"] for l in res["lods"]]
    assert devs[0] <= devs[1] <= devs[2] and devs[2] > devs[0]
    assert all(0.8 < l["silhouette_iou"] <= 1.0 for l in res["lods"]) and all(l["weight_audit_pass"] is None for l in res["lods"])


def test_protected_group_vertices_survive_and_protecting_everything_keeps_counts_above_ratio(tmp_path):
    d = one(go(tmp_path, BUMPY + '''
ob = bumpy()
cap = sorted((round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5)) for v in ob.data.vertices if v.co.z > 0.35)
canon("piece")
res = call("lod_chain", object="piece", ratios=[0.3], protect="emblem")
lod = bpy.data.objects[res["lods"][0]["object"]]
kept = {(round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5)) for v in lod.data.vertices}
g = ob.vertex_groups.new(name="all"); g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
canon("piece")
allp = call("lod_chain", object="piece", ratios=[0.3], protect="all", naming="{name}_ALL{n}")
print("RESULT", json.dumps({"res": res, "missing": len([c for c in cap if c not in kept]), "cap": len(cap), "allp": allp, "n0": len(ob.data.polygons)}))
'''))
    assert d["res"]["ok"] and d["cap"] > 50 and d["missing"] == 0
    assert d["allp"]["ok"] and d["allp"]["lods"][0]["faces"] > 0.9 * d["n0"]          # the falsifier: protect everything and the count stays above the ratio


def test_uv_seam_vertices_survive_when_preserved(tmp_path):
    d = one(go(tmp_path, BUMPY + '''
ob = bumpy()
uv = ob.data.uv_layers.new(name="UVMap")
for poly in ob.data.polygons:                                         # two islands split at x = 0: a seam along the meridian
    for li in poly.loop_indices:
        co = ob.data.vertices[ob.data.loops[li].vertex_index].co
        uv.data[li].uv = ((0.25 if poly.center.x < 0 else 0.75) + co.x * 0.2, 0.5 + co.z * 0.4)
loops_by_vert = {}
for poly in ob.data.polygons:
    for li in poly.loop_indices:
        loops_by_vert.setdefault(ob.data.loops[li].vertex_index, set()).add(tuple(round(x, 5) for x in uv.data[li].uv))
seam = sorted(tuple(round(c, 5) for c in ob.data.vertices[i].co) for i, s in loops_by_vert.items() if len(s) > 1)
canon("piece")
keep = call("lod_chain", object="piece", ratios=[0.2], naming="{name}_K{n}")
canon("piece")
lose = call("lod_chain", object="piece", ratios=[0.2], preserve_uv_seams=False, naming="{name}_L{n}")
def missing(name):
    have = {tuple(round(c, 5) for c in v.co) for v in bpy.data.objects[name].data.vertices}
    return len([s for s in seam if s not in have])
print("RESULT", json.dumps({"seam": len(seam), "keep": missing(keep["lods"][0]["object"]), "lose": missing(lose["lods"][0]["object"])}))
'''))
    assert d["seam"] > 20 and d["keep"] == 0 and d["lose"] > 0


def test_textures_are_downsized_per_lod(tmp_path):
    d = one(go(tmp_path, BUMPY + '''
ob = bumpy(subdiv=3)
img = bpy.data.images.new("albedo", 256, 128); img.filepath_raw = os.path.join(root, "tex", "albedo.png"); img.file_format = "PNG"
os.makedirs(os.path.join(root, "tex"), exist_ok=True); img.save()
canon("piece")
res = call("lod_chain", object="piece", ratios=[0.5, 0.25], texture_scale=[0.5, 0.25], textures=["tex/albedo.png"], out_dir="lods")
sizes = [list(bpy.data.images.load(os.path.join(root, t)).size) for l in res["lods"] for t in l["textures"]]
print("RESULT", json.dumps({"res": res, "sizes": sizes}))
'''))
    assert d["res"]["ok"] and d["sizes"] == [[128, 64], [64, 32]]
    assert d["res"]["lods"][0]["textures"] == ["lods/albedo_LOD1.png"]


def test_refusals_ratios_not_decreasing_out_of_range_and_a_skinned_mesh_without_protect(tmp_path):
    d = one(go(tmp_path, BUMPY + '''
ob = bumpy(subdiv=3)
canon("piece")
up = call("lod_chain", object="piece", ratios=[0.25, 0.5])
canon("piece")
rng = call("lod_chain", object="piece", ratios=[0.95])
canon("piece")
scale = call("lod_chain", object="piece", ratios=[0.5, 0.25], texture_scale=[1.0])
rig = armature()
bind("piece")                                                          # a rigid bind replaces the groups: put the emblem group back
g = ob.vertex_groups.new(name="emblem"); g.add([v.index for v in ob.data.vertices if v.co.z > 0.35], 1.0, "REPLACE")
canon("piece")
skinned = call("lod_chain", object="piece", ratios=[0.5])
canon("piece")
ok = call("lod_chain", object="piece", ratios=[0.5], protect="emblem")
print("RESULT", json.dumps({"up": up, "rng": rng, "scale": scale, "skinned": skinned, "ok": ok}))
'''))
    assert d["up"]["ok"] is False and "strictly decreasing" in d["up"]["error"]
    assert d["rng"]["ok"] is False and "0.05..0.9" in d["rng"]["error"]
    assert d["scale"]["ok"] is False and "texture_scale" in d["scale"]["error"]
    assert d["skinned"]["ok"] is False and "protect the joint loops or run weight_audit after" in d["skinned"]["error"]
    assert d["ok"]["ok"] and d["ok"]["lods"][0]["weight_audit_pass"] is True


def test_the_deviation_counts_detail_the_lod_lost_not_only_where_its_vertices_moved(tmp_path):
    d = one(go(tmp_path, '''
from mixar.modules.lampway_tools.features import lod_chain as L
def grid(name, spike):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=1.0)
    if spike:
        min(bm.verts, key=lambda v: v.co.length).co.z = 0.5
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
src, flat = grid("src", True), grid("flat", False)
print("RESULT", json.dumps({"dev": L._deviation(flat, src), "diag": src.dimensions.length}))
'''))
    assert d["dev"] > 0.4 / d["diag"]                      # the spike's tip is ~0.5 m from the flat LOD, though every flat vertex lies on the source


def test_many_uv_islands_report_achieved_ratios_and_protection_warnings(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
from mixar.modules.lampway_tools.features import lod_chain as L
if os.environ.get('LAMPWAY_REVERT_LOD_WARNING'):
    import inspect
    source=inspect.getsource(L.lod_chain)
    guard=os.environ['LAMPWAY_REVERT_LOD_WARNING']
    old={'ratio':'if abs(achieved_ratio - r) / r > 0.25:', 'previous':'if lods and faces == lods[-1]["faces"]:'}[guard]
    assert old in source,'falsifier no longer matches the implementation'
    exec(source.replace(old,'if False:'),L.__dict__)
ob=sphere(subdiv=3);uv=ob.data.uv_layers.new(name='DisjointTriangles')
for p in ob.data.polygons:
    for j,li in enumerate(p.loop_indices):
        du,dv=((0,0),(.001,0),(0,.001))[j]
        uv.data[li].uv=(p.index*.01+du,p.index*.007+dv)
from mixar.modules.lampway_tools.features import uv_islands as U
measured=U.measure_object(ob,res=64)
assert measured['islands']==len(ob.data.polygons)>100,measured
for p in ob.data.polygons:
    a,b,c=[uv.data[li].uv.copy() for li in p.loop_indices]
    assert abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))>0,'UV islands must have area'
r=call('normalize_mesh',input=ob.name,turn_deg=0)
assert r.get('ok'),r
r=call('lod_chain',object=ob.name,ratios=[.5,.25,.1],preserve_uv_seams=True)
assert r.get('ok'),r
n=len(ob.data.polygons)
for i,row in enumerate(r['lods']):
    assert row['achieved_ratio']==round(row['faces']/n,6),row
    assert row['warnings'] and any('preserve_uv_seams' in w for w in row['warnings']),row
    if i:assert any('previous' in w for w in row['warnings']),row
boundary=call('lod_chain',object=ob.name,ratios=[.8,.7999999],preserve_uv_seams=True,naming='{name}_boundaryLOD{n}')
assert boundary.get('ok'),boundary
assert boundary['lods'][0]['achieved_ratio']==1 and boundary['lods'][0]['warnings']==[],boundary
assert any('over 25%' in w for w in boundary['lods'][1]['warnings']),boundary
assert any('previous' in w for w in boundary['lods'][1]['warnings']),boundary
''')
