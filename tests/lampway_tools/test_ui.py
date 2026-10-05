# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Lampway tools panel and operators. The bootstrap loads UI modules from a timer (a window's event loop); a headless
run drives the same loader by hand, so what registers here is what registers in a window. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, bmesh, json, math, os
import numpy as np
from mathutils import Vector, Matrix
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
root = ROOT
me = bpy.data.meshes.new("piece")
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.3)
bm.faces.ensure_lookup_table()
cut = [f for f in bm.faces if math.degrees(f.calc_center_median().angle(Vector((1, 0, 0)))) < 25]
bmesh.ops.delete(bm, geom=cut, context="FACES_ONLY")
bmesh.ops.create_cube(bm, size=0.05, matrix=Matrix.Translation((0, 0, 0.345)))
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("piece", me); ob.location = (0, 0, 0.5)
bpy.context.scene.collection.objects.link(ob); bpy.context.view_layer.update()
bpy.context.view_layer.objects.active = ob
os.makedirs(root + "/demo", exist_ok=True)
json.dump({"parts": {"top": {"class": "rigid-metal"}, "bottom": {"class": "cloth-sim"}}}, open(root + "/demo/recipe.json", "w"))
np.save(root + "/demo/owner.npy", np.array([0 if p.center.z >= 0 else 1 for p in me.polygons]))
'''


def run(tmp_path, body):
    return run_script(PRE.replace("ROOT", repr(str(tmp_path))) + body, env={"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home")})


def test_the_panel_and_operators_register_without_errors(tmp_path):
    r = run(tmp_path, '''
ops = [n for n in dir(bpy.ops.lampway)]
panels = sorted(c.__name__ for c in bpy.types.Panel.__subclasses__() if c.__name__.startswith("LAMPWAY_"))
print("RESULT", json.dumps({"ops": ops, "panels": panels, "has_props": hasattr(bpy.context.scene, "lampway_tools")}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    for op in ("qa_setup", "qa_tag_layers", "qa_candidates", "qa_draw", "qa_read_tags", "rebuild", "run_tool", "settings_open", "meshpaint_run", "meshpaint_albedo"):
        assert op in res["ops"], op
    assert {"LAMPWAY_PT_main", "LAMPWAY_PT_qa", "LAMPWAY_PT_meshpaint"} <= set(res["panels"]) and res["has_props"] is True
    assert "Traceback" not in r.out and "Failed to" not in r.out


def test_the_buttons_do_what_the_api_does(tmp_path):
    r = run(tmp_path, '''
p = bpy.context.scene.lampway_tools
p.qa_recipe = root + "/demo/recipe.json"; p.qa_owner = root + "/demo/owner.npy"; p.qa_piece = "demo"; p.qa_offset_z = 0.5
a = bpy.ops.lampway.qa_setup()
b = bpy.ops.lampway.qa_tag_layers()
c = bpy.ops.lampway.qa_candidates()
cmsg = p.last_message
d = bpy.ops.lampway.qa_draw()
print("RESULT", json.dumps({"ops": [sorted(x) for x in (a, b, c, d)], "msg": cmsg, "draw_msg": p.last_message, "cands": os.path.exists(root + "/demo/rulings/demo_candidates.json"),
                             "layers": [l.info for l in bpy.context.scene.annotation.layers], "col": "QA_candidates" in bpy.data.collections}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ops"] == [["FINISHED"]] * 4
    assert res["cands"] is True and res["col"] is True
    assert {"Delete", "Mislabel", "Hole"} <= set(res["layers"])
    assert res["msg"] == "2 candidates (1 open loops, 1 floating shells)" and res["draw_msg"].startswith("drew 2 candidates")


def test_a_refusal_is_reported_to_the_user_and_cancels(tmp_path):
    r = run(tmp_path, '''
p = bpy.context.scene.lampway_tools
p.qa_recipe = "/etc/passwd"; p.qa_owner = root + "/demo/owner.npy"
try:
    res = sorted(bpy.ops.lampway.qa_setup())
except RuntimeError as e:                                  # an operator that reports ERROR and cancels raises in Python
    res = ["RuntimeError", str(e)]
print("RESULT", json.dumps({"res": res, "msg": p.last_message}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results[0]["res"][0] == "RuntimeError" and "outside the project root" in r.results[0]["res"][1]
    assert "outside the project root" in r.results[0]["msg"]


def test_the_features_panel_runs_a_feature_on_the_active_object_and_reports_one_line(tmp_path):
    r = run(tmp_path, '''
p = bpy.context.scene.lampway_tools
def go():
    try:
        return bpy.ops.lampway.feature_run()
    except RuntimeError:                      # an operator that reports ERROR raises in a script: that is its refusal
        return {"CANCELLED"}
p.feature = "segment_mesh"
p.feature_args = '{"method": "shells"}'
res = go()
msg1 = p.last_message
p.feature = "retopo"
p.feature_args = '{"engine": "studio:tripo"}'
res2 = go()
p.feature_args = "not json"
res3 = go()
print("RESULT", json.dumps({"r1": sorted(res), "msg1": msg1, "r2": sorted(res2), "msg2": p.last_message if False else "", "r3": sorted(res3),
                            "msg3": p.last_message, "panel": any(c.__name__ == "LAMPWAY_PT_features" for c in bpy.types.Panel.__subclasses__())}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["r1"] == ["FINISHED"] and "parts" in out["msg1"], out
    assert out["r2"] == ["CANCELLED"], "the studio slot refuses without a click, so the operator reports a refusal"
    assert out["r3"] == ["CANCELLED"] and "JSON" in out["msg3"]
    assert out["panel"] is True
