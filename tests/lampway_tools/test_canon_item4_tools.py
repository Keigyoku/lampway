# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 4 at the TOOL level (canon 04): lampway_fit_bind stage=return writes <piece>_rest by the EXACT
inverse of the blended transform (golden C02), refuses a singular blend by vertex, and refuses a return at another pose
than the one the weights were sampled at. Each was observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from test_wave3_weights import PRE  # noqa: E402


def run(body, goldens):
    r = run_script(PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + SETUP + body, timeout=300)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


# The C02 two-bone rig; the body is the tube at REST skinned by the golden's weights, so posed at the fit pose it lies exactly
# on the piece (authored at the fit pose): each piece vertex then takes the golden's own weights from the body.
SETUP = r'''
import numpy as np
from mathutils import Matrix
w = json.load(open(GOLD + "/C02_inverse_lbs/weights.json")); exp = json.load(open(GOLD + "/C02_inverse_lbs/expected.json"))
arm = armature(bones=(("A", (0, 0, 0), (0, 0, 0.3), None), ("B", (0, 0, 0.3), (0, 0, 0.6), "A")))
piece = load_obj(GOLD + "/C02_inverse_lbs/piece_fit_pose.obj", "piece")
vg = piece.vertex_groups.new(name="sleeve"); vg.add([v.index for v in piece.data.vertices], 1.0, "REPLACE")
body = load_obj(GOLD + "/C02_inverse_lbs/piece_fit_pose.obj", "body")
for v, p in zip(body.data.vertices, exp["exact_inverse"]["rest_vertices"]):
    v.co = p
ga, gb = body.vertex_groups.new(name="A"), body.vertex_groups.new(name="B")
for v, (a, b) in zip(body.data.vertices, w["W"]):
    if a > 0: ga.add([v.index], a, "REPLACE")
    if b > 0: gb.add([v.index], b, "REPLACE")
m = body.modifiers.new("Armature", "ARMATURE"); m.object = arm

def pose(MB):
    pb = arm.pose.bones["B"]
    pb.matrix = Matrix(MB) @ arm.data.bones["B"].matrix_local
    bpy.context.view_layer.update()

pose(w["fit_pose"]["B"])
api.fit_bind("plan", piece="piece", armature="rig", roles={"sleeve": "leather"}, bind_overrides={"sleeve": {"bones": ["A", "B"]}}, out_dir="fb")
wt = api.fit_bind("weights", piece="piece", armature="rig", out_dir="fb", body_object="body")
'''


def test_g04_1_the_return_is_the_exact_inverse_and_round_trips_through_blenders_own_skinning(goldens):
    d = run('''
ret = api.fit_bind("return", piece="piece", armature="rig", out_dir="fb")
out = {"ok": ret.get("ok"), "error": ret.get("error")}
if ret.get("ok"):
    rest_ob = bpy.data.objects[ret["object"]]
    out["rest"] = [list(v.co) for v in rest_ob.data.vertices]
    ev = rest_ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    out["posed"] = [list(v.co) for v in me.vertices]; ev.to_mesh_clear()
    out["fit"] = [list(v.co) for v in piece.data.vertices]
    out["receipt"] = {k: ret.get(k) for k in ("round_trip_max_m", "singular", "vertices")}
res(out)
''', goldens)
    assert d["ok"], d["error"]
    want = np.array(J(goldens, "C02_inverse_lbs/expected.json")["exact_inverse"]["rest_vertices"])
    assert np.abs(np.array(d["rest"]) - want).max() < 1e-6
    assert np.abs(np.array(d["posed"]) - np.array(d["fit"])).max() < 1e-6 and d["receipt"]["round_trip_max_m"] < 1e-6
    assert d["receipt"]["singular"] == [] and d["receipt"]["vertices"] == len(want)


def test_g04_1_falsifier_the_blend_of_inverses_misses_by_ten_millimetres(goldens):
    w, exp = J(goldens, "C02_inverse_lbs/weights.json"), J(goldens, "C02_inverse_lbs/expected.json")
    from canon_support import reference as R
    from canon_support import obj
    V, *_ = obj(goldens, "C02_inverse_lbs/piece_fit_pose.obj")
    mats = [np.eye(4), np.array(w["fit_pose"]["B"])]
    wrong = np.array([R.blend_of_inverses(p, ww, mats) for p, ww in zip(V, w["W"])])
    err = np.linalg.norm(np.array([R.lbs(q, ww, mats) for q, ww in zip(wrong, w["W"])]) - V, axis=1)
    assert err.max() == pytest.approx(exp["blend_of_inverses"]["max_round_trip_m"], abs=1e-7)


def test_g04_3_a_singular_blend_is_refused_naming_its_vertices(goldens):
    d = run('''
fit = bpy.data.objects[wt["object"]]
for g in ("A", "B"):
    fit.vertex_groups[g].add([0], 0.5, "REPLACE")                       # vertex 0 blended half and half
pose(exp["singular"]["fit_pose_B"])                                       # ... with B turned 180 degrees: rank 1
from mixar.modules.lampway_tools.features import fit_bind as FB           # as if the weights had been sampled at this pose
st = FB._load(root, "fb"); st["weights"]["pose"] = FB._pose_record(arm); FB._save(root, "fb", st)
ret = api.fit_bind("return", piece="piece", armature="rig", out_dir="fb")
res({"ok": ret.get("ok"), "error": ret.get("error")})
''', goldens)
    assert not d["ok"] and "singular" in d["error"]


def test_a_return_at_another_pose_than_the_weights_were_sampled_at_is_refused(goldens):
    d = run('''
arm.pose.bones["B"].matrix_basis = Matrix.Identity(4); bpy.context.view_layer.update()
ret = api.fit_bind("return", piece="piece", armature="rig", out_dir="fb")
res({"ok": ret.get("ok"), "error": ret.get("error")})
''', goldens)
    assert not d["ok"] and "another pose" in d["error"]
