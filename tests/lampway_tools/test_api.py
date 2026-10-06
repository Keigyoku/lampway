# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tools API: what the panel's buttons, the operators and the agent's tools (through blender.execute_script) all
call. JSON in, JSON out; a failure is {"ok": false, "error", "help"}, never a traceback into the model; every path
stays inside the project root. REAL binary, the synthetic sphere piece."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, bmesh, json, math, os
import numpy as np
from mathutils import Vector, Matrix
from mixar.modules.lampway_tools import api, jobs

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
cube_polys = [p.index for p in me.polygons if p.center.z > 0.31]
os.makedirs(root + "/demo", exist_ok=True)
json.dump({"parts": {"top": {"class": "rigid-metal"}, "bottom": {"class": "cloth-sim"}}}, open(root + "/demo/recipe.json", "w"))
np.save(root + "/demo/owner.npy", np.array([0 if p.center.z >= 0 else 1 for p in me.polygons]))
'''


def run(tmp_path, body):
    return run_script(PRE.replace("ROOT", repr(str(tmp_path))) + body, env={"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home")})


def test_setup_then_candidates_then_status(tmp_path):
    r = run(tmp_path, '''
s = api.qa_setup(object="piece", recipe="demo/recipe.json", owner="demo/owner.npy", piece="demo", offset=[0, 0, 0.5])
c = api.qa_candidates()
st = api.status()
print("RESULT", json.dumps({"setup": s, "cands": c, "status": st["qa"], "tools": len(st["tools"])}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["setup"]["ok"] is True and res["setup"]["piece"] == "demo"
    assert res["cands"]["ok"] is True and res["cands"]["open_loops"] == 1 and res["cands"]["loose_shells"] == 1
    assert res["status"]["configured"] is True and res["status"]["piece"] == "demo"
    assert res["tools"] >= 18


def test_a_path_outside_the_project_root_is_refused_not_raised(tmp_path):
    r = run(tmp_path, '''
s = api.qa_setup(object="piece", recipe="/etc/passwd", owner="demo/owner.npy")
print("RESULT", json.dumps(s))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is False and "outside the project root" in res["error"] and res["help"]


def test_asking_before_setup_says_what_to_do(tmp_path):
    r = run(tmp_path, '''
print("RESULT", json.dumps(api.qa_candidates()))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results[0]["ok"] is False and "qa_setup" in r.results[0]["error"]


def test_reading_the_tags_through_the_api_writes_rulings_and_the_summary(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import marks as M
api.qa_setup(object="piece", recipe="demo/recipe.json", owner="demo/owner.npy", piece="demo", offset=[0, 0, 0.5])
api.qa_candidates()
ann = M.create_tag_layers()
lay = ann.layers["Delete"]; fr = lay.frames.new(0); s = fr.strokes.new(); s.points.add(3)
for p, c in zip(s.points, [(0, 0, 0.845), (0.01, 0, 0.845), (0, 0.01, 0.845)]): p.co = c
rep = api.qa_read_tags(close_round=True)
rul = api.qa_rulings()
print("RESULT", json.dumps({"rep": rep, "rul": rul, "cube": sorted(cube_polys)}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["rep"]["ok"] is True and res["rep"]["shells"] == ["S000"] and res["rep"]["deleted"] == 6
    assert res["rul"]["deletions"] == 6 and res["rul"]["answers"]["loose_shell"] == {"S000": "delete"}
    assert res["rul"]["answers"]["open_loop"] == {"L000": "keep"}            # the round was closed: everything else intentional


def test_mislabel_targets_arrive_as_json_with_string_keys(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import marks as M
api.qa_setup(object="piece", recipe="demo/recipe.json", owner="demo/owner.npy", piece="demo", offset=[0, 0, 0.5])
api.qa_candidates()
ann = M.create_tag_layers()
lay = ann.layers["Mislabel"]; fr = lay.frames.new(0); s = fr.strokes.new(); s.points.add(2)
s.points[0].co = (0, 0, 0.845); s.points[1].co = (0.01, 0, 0.845)
first = api.qa_read_tags(apply=False)
rep = api.qa_read_tags(mislabel_to={"0": "bottom"})
bad = api.qa_read_tags(mislabel_to={"0": "nonesuch"})
print("RESULT", json.dumps({"first": first["relabels_needing_a_target"], "rep": rep["relabelled"], "bad": bad}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert len(res["first"]) == 1 and res["first"][0]["stroke"] == 0
    assert res["rep"] == 1                         # the stroke runs over one face of the cube
    assert res["bad"]["ok"] is False and "unknown part" in res["bad"]["error"]


def test_the_tool_listing_names_every_ported_tool_and_its_kind(tmp_path):
    r = run(tmp_path, '''
t = api.tools()
print("RESULT", json.dumps({"n": len(t), "first": t[0], "kinds": sorted({x["kind"] for x in t})}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results[0]["n"] >= 18 and r.results[0]["kinds"] == ["blender", "numpy", "science"]


def test_run_tool_jails_every_path_argument(tmp_path):
    r = run(tmp_path, '''
out = api.run_tool("render_owner", ["/etc/hosts", "demo/owner.npy", "demo/recipe.json", "demo/out"])
bad = api.run_tool("nope", [])
print("RESULT", json.dumps({"out": out, "bad": bad}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["out"]["ok"] is False and "outside the project root" in res["out"]["error"]
    assert res["bad"]["ok"] is False and "no tool" in res["bad"]["error"]


def test_rebuild_runs_in_the_background_then_loads_the_mesh_beside_the_previous(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import rebuild as RB, live_load
# a fake rebuild result: an FBX + masks dir, standing in for the minutes-long batch run
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2, 0, 0)); bpy.context.object.name = "tmp_cube"
os.makedirs(root + "/demo/out/patched", exist_ok=True); os.makedirs(root + "/demo/out/t1", exist_ok=True)
bpy.ops.export_scene.fbx(filepath=root + "/demo/out/patched/demo_t1_uv.fbx", use_selection=True)
bpy.data.objects.remove(bpy.data.objects["tmp_cube"])
for n in ("mask_plate.png", "detail_height_u16.png"):
    im = bpy.data.images.new(n, 4, 4); im.filepath_raw = root + "/demo/out/t1/" + n; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
tm = bpy.data.materials.new("textured_old"); tm.use_nodes = True
for n in ("mask_plate.png", "detail_height_u16.png"):
    node = tm.node_tree.nodes.new("ShaderNodeTexImage"); node.image = bpy.data.images.new(n, 4, 4); node.image.filepath = root + "/demo/out/t1/" + n
def fake_run(spec, tag, settings, **kw):
    return {"ok": True, "steps": [], "skipped": [], "failed": None, "out": root + "/demo/out/" + tag, "patched": root + "/demo/out/patched",
            "mesh": root + "/demo/out/patched/demo_" + tag + "_uv.fbx"}
api._rebuild_run = fake_run
api.qa_setup(object="piece", recipe="demo/recipe.json", owner="demo/owner.npy", piece="demo", offset=[0, 0, 0.5])
api.rebuild_setup(source_mesh="demo/recipe.json", source_owner="demo/owner.npy", relief_dir="demo", plates_dir="demo", template_material="textured_old", lift=0.5, out_root="demo/out", previous=["piece"])
started = api.rebuild("t1", read_tags=False)
import time
for _ in range(200):
    if jobs.get(started["job"]).state != "running": break
    time.sleep(0.01)
jobs.pump()
st = api.job_status(started["job"])
print("RESULT", json.dumps({"started": started, "status": st, "loaded": "demo_t1_textured" in bpy.data.objects, "prev_hidden": bpy.data.objects["piece"].hide_get()}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["started"]["ok"] is True and res["started"]["job"].startswith("rebuild-")
    assert res["status"]["state"] == "done" and res["status"]["loaded"] == "demo_t1_textured"
    assert res["loaded"] is True and res["prev_hidden"] is True


def test_call_is_the_one_door_the_agent_scripts_use(tmp_path):
    r = run(tmp_path, '''
ok = api.call("status", "{}")
unknown = api.call("settings_set_everything", "{}")
bad_json = api.call("status", "{nope")
private = api.call("_settings", "{}")
tool = api.call("run_tool", json.dumps({"name": "nope", "args": []}))
print("RESULT", json.dumps({"ok": ok["ok"], "unknown": unknown, "bad_json": bad_json["ok"], "private": private["ok"], "tool": tool["error"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is True and res["bad_json"] is False and res["private"] is False
    assert res["unknown"]["ok"] is False and "no tool function" in res["unknown"]["error"]
    assert "no tool" in res["tool"]


def test_run_tool_runs_in_the_project_root_with_every_path_token_jailed(tmp_path):
    """A bare file name is resolved by the tool against its working directory, so that directory is the project root;
    a path inside a `--flag=` or a `name=path:turn` token is jailed like a positional one."""
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import runner as RUN
seen = {}
class _R:
    rc, stdout, log, timed_out = 0, "", None, False
def fake_run(name, args, s, **kw):
    seen.update(name=name, args=list(args), cwd=kw.get("cwd"))
    return _R()
RUN.run = fake_run
out = api.run_tool("render_owner", ["demo/mesh.fbx", "--out=demo/x.npy", "name=demo/p.npz:12", "bare.png"])
print("RESULT", json.dumps({"out": out, "seen": seen}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    root = str(tmp_path)
    assert res["out"]["ok"] is True
    assert res["seen"]["cwd"] == root
    assert res["seen"]["args"] == [f"{root}/demo/mesh.fbx", f"--out={root}/demo/x.npy", f"name={root}/demo/p.npz:12", "bare.png"]


def test_a_batch_tool_whose_worker_failed_is_not_ok(tmp_path):
    """Audit F6: lampway_place_piece and its batch siblings returned ok: true with rc: 1 and a traceback. A non-zero rc or a
    timeout is ok: false, its error the worker's last error line, with a next step; rc, output and log stay in the reply."""
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import runner as RUN
class _Fail:
    rc, log, timed_out = 1, "/root/logs/place_piece.log", False
    stdout = "loading body\\nTraceback (most recent call last):\\n  File \\"place_piece.py\\", line 9\\nValueError: the piece has no chest landmarks\\n"
class _Late:
    rc, stdout, log, timed_out = -1, "error: place_piece timed out after 5 s and was killed", None, True
RUN.run = lambda name, args, s, **kw: _Fail()
fail = api.run_tool("render_owner", [])
RUN.run = lambda name, args, s, **kw: _Late()
late = api.run_tool("render_owner", [])
print("RESULT", json.dumps({"fail": fail, "late": late}))
''')
    assert r.rc == 0, r.out[-2500:]
    fail, late = r.results[0]["fail"], r.results[0]["late"]
    assert fail["ok"] is False and fail["rc"] == 1 and fail["error"] == "ValueError: the piece has no chest landmarks", fail
    assert fail["help"] and "Traceback" in fail["output"]
    assert late["ok"] is False and late["timed_out"] is True and "timed out" in late["error"] and late["help"]


def test_an_argument_refusal_names_the_call_it_wants(tmp_path):
    """Audit F13: about 30 in-Blender refusals said only "Fix the argument named in the error". The help now carries the tool's
    call shape (its arguments and their defaults), so the next call can be right."""
    r = run(tmp_path, '''
out = api.call("model_compare", json.dumps({"action": "stats", "set": "a.glb"}))
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["ok"] is False
    assert any("model_compare(action='stats', set=None" in h for h in out["help"]), out["help"]
