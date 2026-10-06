# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_local_edit + edit_locality_check (specs/wiki/mesh_local_edit.md, edit_locality_check.md): a bounded edit on a COPY of a derivative with a lineage
(deform: a move/rotate/scale with falloff, counts and UVs kept; studio:tripo: the exact-box Edit Mesh retry as a plan that clicks nothing), then the locality
measured: what changed OUTSIDE the region. REAL binary."""

import json

from features_support import run

PLATE = '''
bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20, size=1.0)
ob = bpy.context.active_object; ob.name = "plate"
g = ob.vertex_groups.new(name="body"); g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
canon("plate", welded=True)                       # the door: a local edit reads a welded canonical mesh at real scale
def lineage():
    return call("asset_lineage", action="record", object="plate", transform="seed", anchors=[
        {"name": "a", "point": [-0.5, -0.5, 0.0]}, {"name": "b", "point": [0.5, -0.5, 0.0]}, {"name": "c", "point": [0.0, 0.5, 0.0]}])
BOX = [-0.1, -0.1, -0.05, 0.1, 0.1, 0.05]
'''


def _go(tmp_path, body):
    r = run(tmp_path, PLATE + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_deform_moves_only_region_and_keeps_uv_and_counts(tmp_path):
    res = _go(tmp_path, '''
lineage()
r = call("mesh_local_edit", object="plate", region={"bbox": BOX}, op="move", delta=[0, 0, 0.05], falloff_m=0.05)
src, new = bpy.data.objects["plate"], bpy.data.objects[r["object"]] if r.get("ok") else None
far = [i for i, v in enumerate(src.data.vertices) if max(abs(v.co.x), abs(v.co.y)) > 0.1 + 0.05 + 1e-6]
moved_far = max(abs(new.data.vertices[i].co.z - src.data.vertices[i].co.z) for i in far) if new else None
from mixar.modules.lampway_tools import canon_asset as CA, canon_io
stamp = json.loads(new["lw_canon"]) if new is not None and "lw_canon" in new.keys() else None
print("RESULT", json.dumps({"r": r, "moved_far": moved_far, "src_z": max(v.co.z for v in src.data.vertices),
                            "out_check": CA.check(stamp, canon_io.facts(new)) if stamp else ["no stamp"],
                            "out_welded": stamp["body"]["topology"]["welded"] if stamp else None}))
''')
    r = res["r"]
    assert r["ok"] is True and r["object"] == "plate_edit" and r["topology_changed"] is False and abs(r["moved_max_m"] - 0.05) < 1e-6, r
    assert res["moved_far"] == 0.0 and res["src_z"] == 0.0, "nothing outside the falloff moved; the source is untouched"
    # the edited copy is canonical again (inherits the source's decisions), so edit_locality_check and the next tool can read it
    assert res["out_check"] == [] and res["out_welded"] is True, res
    loc = r["locality"]
    assert loc["pass"] is True and loc["outside"]["moved_vertices"] == 0 and loc["uv_changed"] is False and loc["material_changed"] is False, loc


def test_region_over_60_percent_refused_and_an_edit_without_lineage_refused(tmp_path):
    res = _go(tmp_path, '''
nolin = call("mesh_local_edit", object="plate", region={"bbox": BOX}, op="move", delta=[0, 0, 0.05])
lineage()
big = call("mesh_local_edit", object="plate", region={"bbox": [-0.45, -0.45, -1, 0.45, 0.45, 1]}, op="move", delta=[0, 0, 0.05])
print("RESULT", json.dumps({"nolin": nolin, "big": big}))
''')
    assert res["nolin"]["ok"] is False and "record the lineage first" in res["nolin"]["error"], res
    assert res["big"]["ok"] is False and "use the smallest region" in res["big"]["error"], res


def test_studio_engine_returns_needs_approval_and_clicks_nothing(tmp_path):
    res = _go(tmp_path, '''
lineage()
out = {"tripo": call("mesh_local_edit", object="plate", region={"bbox": BOX}, engine="studio:tripo", side="left", anchors=["a", "b", "c"], instruction="fix the dent"),
       "noside": call("mesh_local_edit", object="plate", region={"bbox": BOX}, engine="studio:tripo"),
       "rodin": call("mesh_local_edit", object="plate", region={"bbox": BOX}, engine="studio:rodin", side="left", anchors=["a", "b", "c"]),
       "objects": sorted(o.name for o in bpy.data.objects)}
print("RESULT", json.dumps(out))
''')
    t = res["tripo"]
    assert t["ok"] is False and t["needs_approval"] is True and t["studio_action"] == "tripo.regen.region" and "0 credits" in t["price"], t
    assert t["plan_args"]["bbox_blender"] == [-0.1, -0.1, -0.05, 0.1, 0.1, 0.05], t
    assert res["noside"]["ok"] is False and "side" in res["noside"]["error"], res
    assert res["rodin"]["ok"] is False and "no studio:rodin driver" in res["rodin"]["error"], res
    assert res["objects"] == ["plate"], "a plan makes nothing"


def test_locality_flags_a_move_outside_the_region_with_its_count(tmp_path):
    res = _go(tmp_path, '''
src = bpy.data.objects["plate"]
a = src.copy(); a.data = src.data.copy(); a.name = "after"; bpy.context.scene.collection.objects.link(a)
for i in (0, 1, 2):
    a.data.vertices[i].co.z += 0.01                       # three corner-row vertices, far outside the box
canon("after", welded=True)
inside = call("edit_locality_check", before="plate", after="after", region=BOX)
whole = call("edit_locality_check", before="plate", after="after", region=[-1, -1, -1, 1, 1, 1])
print("RESULT", json.dumps({"inside": inside, "whole": whole}))
''')
    assert res["inside"]["pass"] is False and res["inside"]["outside"]["moved_vertices"] == 3 and abs(res["inside"]["outside"]["max_move_m"] - 0.01) < 1e-6, res
    assert res["whole"]["pass"] is True, "the falsifier: a region covering everything lets any move pass"


def test_uv_change_and_a_filled_hole_are_flagged(tmp_path):
    res = _go(tmp_path, '''
import bmesh
src = bpy.data.objects["plate"]
a = src.copy(); a.data = src.data.copy(); a.name = "uvd"; bpy.context.scene.collection.objects.link(a)
for d in a.data.uv_layers[0].data: d.uv = (d.uv[0] * 0.5, d.uv[1])
h = src.copy(); h.data = src.data.copy(); h.name = "holed"; bpy.context.scene.collection.objects.link(h)
bm = bmesh.new(); bm.from_mesh(h.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.calc_center_median().x) < 0.03 and abs(f.calc_center_median().y) < 0.03], context="FACES_ONLY")
bm.to_mesh(h.data); bm.free()
canon("uvd", "holed", welded=True)
out = {"uv": call("edit_locality_check", before="plate", after="uvd", region=BOX),
       "hole": call("edit_locality_check", before="holed", after="plate", region=BOX),
       "noreg": call("edit_locality_check", before="plate", after="uvd")}
print("RESULT", json.dumps(out))
''')
    assert res["uv"]["uv_changed"] is True and res["uv"]["pass"] is False, res["uv"]
    assert res["hole"]["open_edges"]["before"] > res["hole"]["open_edges"]["after"] and res["hole"]["outside"]["moved_vertices"] == 0, res["hole"]
    assert res["noreg"]["ok"] is False and "give the region" in res["noreg"]["error"], res
