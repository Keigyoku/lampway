# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon20 B5 / canon07 B7: fitted body faces, child-owned shorter-bone joints."""

from features_support import run
from test_rig_fit_template import EXAMPLE


def test_public_fit_builds_the_procedural_body_and_transfers_its_faces(tmp_path):
    r = run(tmp_path, EXAMPLE + '''
J = measured(); ob = body(J)
d = call("rig_fit_template", example=ob.name, joints=joints_file("rig/j.json", J, ob), out="rig/b.blend")
m = bpy.data.objects[d["rigged"]]
v = m.data.vertices[280]
row = {m.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>1e-6}
print("RESULT", json.dumps({"done":d,"joints":sorted(J),"row":row,"point":list(v.co),"temporary_body_left":any(o.name.startswith("lw_fit_weight_body") for o in bpy.data.objects)}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    result = r.results[0]
    d = result["done"]
    assert d["ok"], d
    # Independent Titan proc_body / m_weights replay: this point is on the
    # middle finger's mid-limb face. The old global3cm field gives it eleven
    # finger groups and only0.2112600844 on middle_02_l.
    assert result["row"] == {"middle_02_l": 1.0}, result
    assert max(abs(a-b) for a,b in zip(result["point"], (.5075458884,-.2167666256,.9545675516))) < 1e-6, result
    w = d["weights"]
    assert w.get("method") == "procedural_body_nearest_face", w
    assert w["body_verts"] == 72 * w["bones"] and w["body_faces"] == 60 * w["bones"], w
    assert w["joint_blend_fraction"] == 0.25 and w["unweighted"] == 0, w
    assert set(w["joint_blends_m"]) == set(result["joints"]) - {"pelvis"}, w
    assert not result["temporary_body_left"], result


def test_joint_widths_share_the_child_rule_on_both_sides_and_refuse_overlap(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.canon_geom import procedural_body as P
F = lambda y: ((1,0,0,0),(0,1,0,y),(0,0,1,0),(0,0,0,1))
B = {"upper": {"parent":None,"frame":F(0),"length":3.0,"head":(.6,.5),"tail":(.5,.4)},
     "lower": {"parent":"upper","frame":F(3),"length":2.0,"head":(.5,.4),"tail":(.3,.2)}}
jb = P.joint_blends(B, .25)
B["lower"]["blend"] = 1.0
mesh = P.body(B, stations=7, sides=6, blend=.1)
tail = [w for w,n,t in zip(mesh["weights"],mesh["bone"],mesh["station"]) if n=="upper" and abs(t-5/6)<1e-9][0]
head = [w for w,n,t in zip(mesh["weights"],mesh["bone"],mesh["station"]) if n=="lower" and abs(t-1/6)<1e-9][0]
bad = []
for mutation in ("fraction", "parent", "missing"):
    try:
        if mutation == "fraction": P.joint_blends(B, .6)
        elif mutation == "parent":
            B["upper"]["length"] = 1.6; P.body(B, 7, 6, .1)
        else:
            B["upper"]["length"] = 3.; B["lower"]["parent"] = "missing"; P.body(B, 7, 6, .1)
    except ValueError: bad.append(mutation)
print("RESULT", json.dumps({"jb":jb,"tail":tail,"head":head,"bad":bad,"sums":all(abs(sum(w.values())-1)<1e-12 for w in mesh["weights"])}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    assert d["jb"] == {"lower": .5} and d["sums"], d
    assert abs(d["tail"]["lower"] - .25) < 1e-12, d
    assert abs(d["head"]["upper"] - 1/3) < 1e-12, d
    assert d["bad"] == ["fraction", "parent", "missing"], d
