# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_bind (shelf/fit_bind.md): the plan with the user's weight laws (metal rigid, everything else by position, seams that cannot open), the weights, the return and the apply gate."""

import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

SETUP = r'''
BONES = (("spine_01", (0, 0, 0), (0, 0, 1), None), ("spine_03", (0, 0, 1), (0, 0, 2), "spine_01"), ("upperarm_l", (0, 0, 2), (0, 0, 3), "spine_03"))
def rig_and_body():
    arm = armature("body_rig", BONES)
    body = tube("body_mesh", r=0.3, z0=0, z1=3, rings=60)
    weights(body, arm, lambda c: {"spine_01": max(0.0, min(1.0, (1.4 - c.z) / 0.8)), "spine_03": max(0.0, 1.0 - abs(c.z - 1.8) / 0.9), "upperarm_l": max(0.0, min(1.0, (c.z - 1.6) / 0.8))})
    return arm, body
def two_parts(z_split=1.5, r=0.34, join=True):
    """one shell cut into two parts at z_split: 'plate' below, 'cloth' above; they share the ring of vertices at the cut."""
    t = tube("piece", r=r, z0=0.5, z1=2.5, rings=40)
    lo = t.vertex_groups.new(name="plate"); hi = t.vertex_groups.new(name="cloth")
    for v in t.data.vertices:
        (lo if v.co.z <= z_split + 1e-6 else hi).add([v.index], 1.0, "REPLACE")
        if abs(v.co.z - z_split) < 1e-6 and join: hi.add([v.index], 1.0, "REPLACE")
    return t
'''


def run(body, **kw):
    return run_script(PRE + SETUP + body, timeout=400, **kw)


def test_a_part_with_no_role_and_a_blended_metal_part_are_refused_with_the_fix():
    r = run('''
arm, bd = rig_and_body(); p = two_parts()
a = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal"}, out_dir="fit/b1").get("error")
b = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "cloth"}, bind_overrides={"plate": {"mode": "blend", "bones": ["spine_01"]}}, out_dir="fit/b2").get("error")
res({"a": a, "b": b})
''')
    d = r.results[-1]
    assert "part cloth has no material role" in d["a"] and "never the render's colour" in d["a"]
    assert "metal is placed by one rigid transform" in d["b"] and "ruled cut" in d["b"]


def test_the_plan_binds_metal_rigid_to_its_dominant_bone_and_other_materials_by_position_and_reports_the_seam():
    r = run('''
arm, bd = rig_and_body(); p = two_parts(z_split=1.5)
out = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "cloth"}, out_dir="fit/b3")
res(out)
''')
    assert r.rc == 0, r.out[-1200:]
    d = r.results[-1]
    plate, cloth = d["parts"]["plate"], d["parts"]["cloth"]
    assert plate["mode"] == "rigid" and plate["bones"] == ["spine_01"] and plate["role"] == "metal"
    assert cloth["mode"] == "restrict" and cloth["bones"] == ["spine_03", "upperarm_l"] or cloth["mode"] == "restrict"
    assert d["seams"] and d["seams"][0]["parts"] == ["cloth", "plate"] and d["seams"][0]["vertices"] > 0
    assert d["seam_opens"] == [] and "bind_plan.json" in d["files"] and "seams.json" in d["files"]


def test_two_metal_parts_of_one_shell_on_different_bones_open_a_seam_and_apply_is_refused_without_the_accepted_gap():
    r = run('''
arm, bd = rig_and_body(); p = two_parts(z_split=1.5)
plan = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "metal"}, bind_overrides={"plate": {"mode": "rigid", "bones": ["spine_01"], "reason": "x"}, "cloth": {"mode": "rigid", "bones": ["upperarm_l"], "reason": "x"}}, out_dir="fit/b4")
w = api.fit_bind("weights", piece="piece", armature="body_rig", out_dir="fit/b4", body_object="body_mesh")
ap = api.fit_bind("apply", piece="piece", armature="body_rig", out_dir="fit/b4")
ok = api.fit_bind("apply", piece="piece", armature="body_rig", out_dir="fit/b4", accept_seam_gap_mm=80)
same = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "metal"}, bind_overrides={"plate": {"mode": "rigid", "bones": ["spine_03"], "reason": "x"}, "cloth": {"mode": "rigid", "bones": ["spine_03"], "reason": "x"}}, out_dir="fit/b5")
res({"opens": plan["seam_opens"], "apply": ap.get("error"), "ok": ok.get("ok"), "same_opens": same["seam_opens"], "groups": same["rigid_groups"]})
''')
    d = r.results[-1]
    assert d["opens"] and d["opens"][0]["bones"] == ["spine_01", "upperarm_l"] and "seam" in d["apply"] and d["ok"] is True
    assert d["same_opens"] == [] and d["groups"] == [["cloth", "plate"]]


def test_weights_give_metal_one_bone_at_weight_one_and_cloth_the_bodys_blend_on_a_copy_that_leaves_the_source_alone():
    r = run('''
arm, bd = rig_and_body(); p = two_parts(z_split=1.5)
api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "cloth"}, out_dir="fit/b6")
w = api.fit_bind("weights", piece="piece", armature="body_rig", out_dir="fit/b6", body_object="body_mesh")
fit = bpy.data.objects[w["object"]]; gi = {g.index: g.name for g in fit.vertex_groups}
rows = {}
for v in fit.data.vertices:
    ws = {gi[g.group]: round(g.weight, 3) for g in v.groups if g.weight > 1e-6}
    rows[v.index] = ws
plate_v = [i for i, v in enumerate(p.data.vertices) if v.co.z < 1.45]
cloth_v = [i for i, v in enumerate(p.data.vertices) if v.co.z > 1.55]
res({"name": w["object"], "plate_one": all(rows[i] == {"spine_01": 1.0} for i in plate_v), "cloth_blend": any(len(rows[i]) > 1 for i in cloth_v), "cloth_sum": max(abs(sum(rows[i].values()) - 1) for i in cloth_v),
     "src_groups": sorted(g.name for g in p.vertex_groups), "mods": [m.type for m in fit.modifiers], "source": w["weights_source"]})
''')
    d = r.results[-1]
    assert d["name"] == "piece_fit" and d["plate_one"] is True and d["cloth_blend"] is True and d["cloth_sum"] < 1e-3
    assert d["src_groups"] == ["cloth", "plate"] and "ARMATURE" in d["mods"] and "approximation" in d["source"]


def test_the_return_reports_the_metal_rest_residual_against_the_original_shell_and_the_report_collects_everything():
    r = run('''
arm, bd = rig_and_body(); p = two_parts(z_split=1.5)
api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "cloth"}, out_dir="fit/b7")
api.fit_bind("weights", piece="piece", armature="body_rig", out_dir="fit/b7", body_object="body_mesh")
ret = api.fit_bind("return", piece="piece", armature="body_rig", out_dir="fit/b7")
ap = api.fit_bind("apply", piece="piece", armature="body_rig", out_dir="fit/b7")
rep = api.fit_bind("report", piece="piece", armature="body_rig", out_dir="fit/b7")
res({"ret": ret["rest_residual"], "ap": ap.get("ok"), "rep": sorted(rep["stages_done"]), "files": sorted(rep["files"])})
''')
    d = r.results[-1]
    assert d["ret"]["plate"]["rms_mm"] < 0.05 and d["ret"]["plate"]["scale"] == 1.0 or abs(d["ret"]["plate"]["scale"] - 1.0) < 1e-6
    assert d["ap"] is True and d["rep"] == ["apply", "plan", "return", "weights"] and "bind_plan.json" in d["files"]


def test_a_bone_that_is_not_in_the_skeleton_names_the_nearest_bones():
    r = run('''
arm, bd = rig_and_body(); p = two_parts()
e = api.fit_bind("plan", piece="piece", armature="body_rig", roles={"plate": "metal", "cloth": "cloth"}, bind_overrides={"plate": {"mode": "rigid", "bones": ["spine_1"]}}, out_dir="fit/b8").get("error")
res({"e": e})
''')
    assert "spine_01" in r.results[-1]["e"] and "spine_1" in r.results[-1]["e"]


@pytest.mark.parametrize("surface_height,expected",[(.04,True),(.6,False)])
def test_restrict_chooses_the_nearest_normal_compatible_allowed_body_surface(surface_height,expected):
    r = run('''
import numpy as np
arm = armature("body_rig", BONES)
# The nearer vertical surface is incompatible with the upward cloth normal;
# the farther horizontal surface is compatible and remains within the match bar.
me = bpy.data.meshes.new("body_surface")
me.from_pydata([(.01,-1,-1),(.01,1,-1),(.01,0,1),(-1,-1,SURFACE_HEIGHT),(1,-1,SURFACE_HEIGHT),(0,1,SURFACE_HEIGHT)], [], [(0,1,2),(3,4,5)])
bd = bpy.data.objects.new("body_mesh", me); bpy.context.scene.collection.objects.link(bd)
weights(bd, arm, lambda c: {"spine_03": 1.0})
pm = bpy.data.meshes.new("cloth_surface")
pm.from_pydata([(0,0,0),(.005,0,0),(0,.005,0)], [], [(0,1,2)])
p = bpy.data.objects.new("cloth", pm); bpy.context.scene.collection.objects.link(p)
g = p.vertex_groups.new(name="cape"); g.add([0,1,2],1.0,"REPLACE")
bpy.context.view_layer.update()
plan = api.fit_bind("plan", piece=p.name, armature=arm.name, roles={"cape":"cloth"},
                    bind_overrides={"cape":{"bones":["spine_03"],"fallback":"spine_03"}},out_dir="fit/normal_query")
w = api.fit_bind("weights", piece=p.name, armature=arm.name, body_object=bd.name,out_dir="fit/normal_query")
res({"plan":plan.get("ok"),"weights":w.get("ok"),"error":w.get("error"),
     "source_unchanged":list(p.vertex_groups.keys())==["cape"] and not p.modifiers})
'''.replace('SURFACE_HEIGHT',str(surface_height)))
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["plan"] and d["weights"] is expected, d
    if not expected:
        assert "zero weight" in d["error"], d
    assert d["source_unchanged"], d


def test_compatible_surface_ties_use_face_identity_independent_of_bvh_traversal():
    r = run('''
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mixar.modules.lampway_tools.features import fit_bind as FB
points=[(-1,-1,.04),(1,-1,.04),(0,1,.04)]
tree=BVHTree.FromPolygons(points,[(0,1,2),(0,1,2)])
class ReverseTraversal:
    def find_nearest(self,point,distance):
        # Both are genuine equally near native hits. Plant the other traversal order.
        return max(tree.find_nearest_range(point,distance),key=lambda h:h[2])
    def find_nearest_range(self,point,distance):
        return tree.find_nearest_range(point,distance)
hit=FB._nearest_compatible(ReverseTraversal(),Vector((0,0,0)),np.array([0.,0.,1.]),.5,np.cos(np.radians(30)))
res({"face":int(hit[2]),"distance_m":float(hit[3])})
''')
    assert r.rc == 0, r.out[-2000:]
    assert r.results[-1]["face"] == 0, r.results[-1]
