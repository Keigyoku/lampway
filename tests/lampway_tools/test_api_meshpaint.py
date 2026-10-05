# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""api.meshpaint(stage, ...): the one entry the panel button and the agent tool share. Stages: setup, clay, prompt, pick, plates,
project, run, albedo, status. The image backend and the minutes-long projection are stubbed; the clay renders and the plate set
are the REAL tools. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import lampway_bin, run_script  # noqa: E402

PRE = '''
import bpy, json, os, time, shutil
import numpy as np
from PIL import Image
from mixar.modules.lampway_tools import api, jobs, meshpaint as MP

root = ROOT
# our mesh: a box with a smaller box on top, as FBX under the project root
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0)); bpy.context.object.scale = (0.8, 0.4, 1.0)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.8)); bpy.context.object.scale = (0.3, 0.3, 0.3)
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.join()
os.makedirs(root + "/demo/v3", exist_ok=True)
bpy.ops.export_scene.fbx(filepath=root + "/demo/m.fbx", use_selection=True)
for v in ("Front", "Back", "Left", "Right"):
    Image.fromarray(np.full((16, 16, 3), 200, np.uint8)).save(root + "/demo/v3/%s.png" % v)
tm = bpy.data.materials.new("textured_demo"); tm.use_nodes = True
def setup(**kw):
    return api.meshpaint("setup", piece="demo", mesh="demo/m.fbx", design_dir="demo/v3", tag="p1", template_material="textured_demo", lift=0.0,
                         recipe="demo/v3/Front.png", relief_dir="demo/v3", out_root="demo/out", **kw)
'''


def run(tmp_path, body, **kw):
    return run_script(PRE.replace("ROOT", repr(str(tmp_path))) + body,
                      env={"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home"), "LAMPWAY_BLENDER": str(lampway_bin())}, **kw)   # the binary under test, never a hard-coded Dev build


def test_setup_then_clay_renders_the_four_views_with_the_real_tool(tmp_path):
    r = run(tmp_path, '''
s = setup()
c = api.meshpaint("clay", res=128)
print("RESULT", json.dumps({"s": s, "c": c, "files": sorted(os.listdir(root + "/demo/meshpaint/clay"))}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["s"]["ok"] is True and res["c"]["ok"] is True and res["c"]["views"] == ["Front", "Back", "Left", "Right"]
    assert res["files"] == ["clay_Back.png", "clay_Back.png.json", "clay_Front.png", "clay_Front.png.json", "clay_Left.png",
                            "clay_Left.png.json", "clay_Right.png", "clay_Right.png.json"]


def test_prompt_writes_the_views_prompt_file_and_returns_the_references_in_order(tmp_path):
    r = run(tmp_path, '''
setup(); api.meshpaint("clay", res=128)
p1 = api.meshpaint("prompt", view="Left")
MP.record_pick(MP.MeshPaintSpec("demo", "m", "d", root + "/demo/meshpaint"), "Left", root + "/demo/meshpaint/runs/Left/2.png")
p2 = api.meshpaint("prompt", view="Front")
print("RESULT", json.dumps({"p1": p1, "p2": p2, "text": open(p1["prompt_file"]).read()[:60]}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    p1, p2 = res["p1"], res["p2"]
    assert p1["ok"] and p1["consistency"] is None and len(p1["refs"]) == 2 and p1["refs"][0].endswith("clay_Left.png") and p1["refs"][1].endswith("v3/Left.png")
    assert p2["consistency"] == "Left" and len(p2["refs"]) == 3 and p2["refs"][1].endswith("runs/Left/2.png")
    assert p1["out_dir"].endswith("runs/Left") and res["text"].startswith("The FIRST image")


def test_pick_chooses_by_silhouette_iou_unless_a_file_is_named_then_plates_use_the_real_tool(tmp_path):
    r = run(tmp_path, '''
setup(); api.meshpaint("clay", res=128)
clay = np.asarray(Image.open(root + "/demo/meshpaint/clay/clay_Front.png").convert("RGB"))
os.makedirs(root + "/demo/meshpaint/runs/Front", exist_ok=True)
bg = clay[0, 0]; mask = np.abs(clay.astype(int) - bg.astype(int)).max(-1) > 8
good = np.where(mask[..., None], np.array([120, 60, 30], np.uint8), np.uint8(255)).astype(np.uint8)
bad = np.roll(good, 30, axis=1)
Image.fromarray(bad).save(root + "/demo/meshpaint/runs/Front/1.png"); Image.fromarray(good).save(root + "/demo/meshpaint/runs/Front/2.png")
pk = api.meshpaint("pick", view="Front")
pl = api.meshpaint("plates", require_all=False)
plate = np.asarray(Image.open(root + "/demo/meshpaint/set/Front.png"))
print("RESULT", json.dumps({"pk": pk, "pl_ok": pl["ok"], "mode": Image.open(root + "/demo/meshpaint/set/Front.png").mode, "alpha_frac": float((plate[..., 3] > 127).mean())}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["pk"]["ok"] and res["pk"]["picked"].endswith("2.png") and res["pk"]["iou"] > 0.9
    assert res["pl_ok"] is True and res["mode"] == "RGBA" and 0.05 < res["alpha_frac"] < 0.9


def test_project_runs_in_the_background_with_the_plates_then_loads_the_result_and_the_albedo_toggle(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import rebuild as RB
os.makedirs(root + "/demo/out/patched", exist_ok=True); os.makedirs(root + "/demo/out/p1_meshpaint", exist_ok=True)
shutil.copy(root + "/demo/m.fbx", root + "/demo/out/patched/demo_p1_uv.fbx")
np.savez(root + "/demo/out/patched/demo_p1_uv_front-y.npz", POLY=np.zeros(1))   # the rebuild's patched mesh the projection reuses
for n in ("mask_plate.png", "detail_height_u16.png", "v3_colour_atlas.png"):
    Image.fromarray(np.full((4, 4, 3), 99, np.uint8)).save(root + "/demo/out/p1_meshpaint/" + n)
n = tm.node_tree.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(root + "/demo/out/p1_meshpaint/mask_plate.png")
seen = {}
def fake_run(spec, tag, settings, **kw):
    seen.update(res=spec.res, no_flow=spec.no_flow, color_full=spec.color_full, plates=spec.plates_dir, only=kw.get("only"), out_name=kw.get("out_name"), tag=tag)
    return {"ok": True, "steps": [], "skipped": [], "failed": None, "out": root + "/demo/out/p1_meshpaint", "patched": root + "/demo/out/patched",
            "mesh": root + "/demo/out/patched/demo_p1_uv.fbx"}
api._rebuild_run = fake_run
setup()
os.makedirs(root + "/demo/meshpaint/set", exist_ok=True)           # the plate set (made by stage plates)
started = api.meshpaint("project")
for _ in range(300):
    if jobs.get(started["job"]).state != "running": break
    time.sleep(0.01)
jobs.pump()
st = api.job_status(started["job"])
print("RESULT", json.dumps({"started": started, "seen": seen, "st": st, "obj": "demo_p1_meshpaint_textured" in bpy.data.objects,
                             "albedo": "textured_demo_albedo" in bpy.data.materials or any("albedo" in m.name for m in bpy.data.materials)}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["started"]["ok"] is True, res["started"]
    assert res["seen"]["res"] == 4096 and res["seen"]["no_flow"] is True and res["seen"]["color_full"] is True
    assert res["seen"]["only"] == ["relief_project", "material_masks"] and res["seen"]["out_name"] == "p1_meshpaint" and res["seen"]["plates"].endswith("meshpaint/set")
    assert res["st"]["state"] == "done" and res["obj"] is True and res["albedo"] is True


def test_albedo_stage_flips_the_toggle(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import albedo as AB
Image.fromarray(np.full((4, 4, 3), 99, np.uint8)).save(root + "/atlas.png")
AB.apply("textured_demo", root + "/atlas.png")
off = api.meshpaint("albedo", material="textured_demo_albedo", on=False)
st1 = AB.state("textured_demo_albedo")
on = api.meshpaint("albedo", material="textured_demo_albedo", on=True)
print("RESULT", json.dumps({"off": off, "on": on, "st1": st1, "st2": AB.state("textured_demo_albedo")}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["off"]["ok"] and res["st1"] is False and res["st2"] is True


def test_an_unknown_stage_and_a_missing_setup_are_refused_with_what_to_do(tmp_path):
    r = run(tmp_path, '''
a = api.meshpaint("nope")
b = api.meshpaint("clay")
print("RESULT", json.dumps({"a": a, "b": b}), flush=True)
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["a"]["ok"] is False and "stages are" in res["a"]["error"]
    assert res["b"]["ok"] is False and "setup" in res["b"]["error"]


def test_the_one_button_run_goes_clay_then_each_view_then_plates_then_the_projection_and_loads_it(tmp_path):
    r = run(tmp_path, '''
os.makedirs(root + "/demo/out/patched", exist_ok=True); os.makedirs(root + "/demo/out/p1_meshpaint", exist_ok=True)
shutil.copy(root + "/demo/m.fbx", root + "/demo/out/patched/demo_p1_uv.fbx")
np.savez(root + "/demo/out/patched/demo_p1_uv_front-y.npz", POLY=np.zeros(1))   # the rebuild's patched mesh the projection reuses
for n in ("mask_plate.png", "detail_height_u16.png", "v3_colour_atlas.png"):
    Image.fromarray(np.full((4, 4, 3), 99, np.uint8)).save(root + "/demo/out/p1_meshpaint/" + n)
n = tm.node_tree.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(root + "/demo/out/p1_meshpaint/mask_plate.png")
order = []
def fake_generate(view, prompt_file, refs, out_dir, live, count=4):
    order.append((view, len(refs), live))
    clay = np.asarray(Image.open(refs[0]).convert("RGB")).astype(int)
    mask = np.abs(clay - clay[0, 0]).max(-1) > 8
    good = np.where(mask[..., None], np.array([120, 60, 30]), 255).astype(np.uint8)
    os.makedirs(out_dir, exist_ok=True)
    for i, shift in enumerate((20, 0, 9, 14), start=1):
        Image.fromarray(np.roll(good, shift, axis=1)).save(out_dir + "/%d.png" % i)
    return [out_dir + "/%d.png" % i for i in (1, 2, 3, 4)]
api._mp_generate_cmd = fake_generate
def fake_run(spec, tag, settings, **kw):
    return {"ok": True, "steps": [], "skipped": [], "failed": None, "out": root + "/demo/out/p1_meshpaint", "patched": root + "/demo/out/patched",
            "mesh": root + "/demo/out/patched/demo_p1_uv.fbx"}
api._rebuild_run = fake_run
setup(clay_res=96)
started = api.meshpaint("run", live=True)
for _ in range(1500):
    jobs.pump()
    j = jobs.get(started["job"])
    follow = getattr(j, "followup", None)
    if j.state == "done" and follow and jobs.get(follow).state != "running":
        break
    time.sleep(0.02)
jobs.pump()
st = api.job_status(started["job"])
print("RESULT", json.dumps({"order": order, "state": j.state, "err": j.error, "picks": sorted(MP.load_picks(MP.MeshPaintSpec("demo", "m", "d", root + "/demo/meshpaint"))),
                             "set": sorted(os.listdir(root + "/demo/meshpaint/set")), "loaded": "demo_p1_meshpaint_textured" in bpy.data.objects,
                             "follow": follow}), flush=True)
''', timeout=600)
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["state"] == "done", res
    assert [o[0] for o in res["order"]] == ["Left", "Front", "Back", "Right"] and [o[1] for o in res["order"]] == [2, 3, 3, 3]
    assert all(o[2] is True for o in res["order"])
    assert res["picks"] == ["Back", "Front", "Left", "Right"]
    assert {"Front.png", "Back.png", "Left.png", "Right.png", "set.json"} <= set(res["set"]) and res["loaded"] is True


def test_a_dry_run_backend_stops_the_job_with_the_instruction_to_pass_live(tmp_path):
    r = run(tmp_path, '''
setup(clay_res=64)
def refuse(view, pf, refs, out, live, count=4):
    raise RuntimeError("the image backend ran as a DRY RUN: pass live=true")
api._mp_generate_cmd = refuse
started = api.meshpaint("run")
for _ in range(600):
    if jobs.get(started["job"]).state != "running": break
    time.sleep(0.02)
print("RESULT", json.dumps({"state": jobs.get(started["job"]).state, "err": jobs.get(started["job"]).error}), flush=True)
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    assert r.results[0]["state"] == "failed" and "live=true" in r.results[0]["err"]


def test_the_image_stage_makes_images_for_ONE_view_through_the_backend_with_the_clay_render_first_and_the_requested_count(tmp_path):
    r = run(tmp_path, '''
seen = []
def fake_generate(view, prompt_file, refs, out_dir, live, count=4):
    seen.append({"view": view, "refs": [os.path.basename(x) for x in refs], "live": live, "count": count, "prompt": open(prompt_file).read()[:40]})
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(np.full((8, 8, 3), 50, np.uint8)).save(out_dir + "/1.png")
    return [out_dir + "/1.png"]
api._mp_generate_cmd = fake_generate
setup(clay_res=64); api.meshpaint("clay", res=64)
dry = api.meshpaint("image", view="Front")
live = api.meshpaint("image", view="Front", live=True, count=1)
bad = api.meshpaint("image", view="Front", live=True, count=9)
print("RESULT", json.dumps({"seen": seen, "dry": dry, "live": live, "bad": bad}), flush=True)
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert [x["view"] for x in res["seen"]] == ["Front", "Front"] and res["seen"][0]["live"] is False and res["seen"][1]["live"] is True
    assert res["seen"][0]["count"] == 4 and res["seen"][1]["count"] == 1
    assert res["seen"][1]["refs"][0] == "clay_Front.png" and res["seen"][1]["prompt"]
    assert res["live"]["ok"] is True and len(res["live"]["files"]) == 1 and res["live"]["view"] == "Front"
    assert res["bad"]["ok"] is False and "count" in res["bad"]["error"]


def test_the_image_stage_passes_the_configured_backend_to_the_image_command(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import api as A, settings as S
A.settings_set(image_backend="openrouter", python_server="/usr/bin/python3", server_dir="/tmp")
seen = {}
import subprocess
def fake_run(cmd, **kw):
    seen["cmd"] = list(cmd)
    class P: returncode, stdout, stderr = 0, "", ""
    return P()
subprocess.run = fake_run
setup(); api.meshpaint("clay", res=64)
res = api.meshpaint("image", view="Front", live=True, count=1)
print("RESULT", json.dumps({"cmd": seen.get("cmd"), "res": res}))
''')
    assert r.rc == 0, r.out[-2500:]
    cmd = r.results[0]["cmd"]
    assert cmd is not None and "--backend" in cmd and cmd[cmd.index("--backend") + 1] == "openrouter"
    assert "--live" in cmd and cmd[cmd.index("--count") + 1] == "1"


def test_the_image_stage_does_not_hand_the_apps_python_environment_to_the_server_python(tmp_path):
    """Blender exports PYTHONHOME (and a PYTHONPATH) for its own interpreter; a venv python that inherits them imports
    Blender's stdlib and site-packages instead of its own (seen live: `No module named 'httpx'` from the venv that
    serves the API). The server python gets a clean Python environment plus the server directory."""
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import api as A
A.settings_set(image_backend="openrouter", python_server="/usr/bin/python3", server_dir="/tmp/srv")
import os, subprocess
os.environ["PYTHONHOME"] = "/the/app/python"; os.environ["PYTHONPATH"] = "/the/app/scripts"
seen = {}
def fake_run(cmd, **kw):
    seen["env"] = dict(kw.get("env") or {})
    class P: returncode, stdout, stderr = 0, "", ""
    return P()
subprocess.run = fake_run
setup(); api.meshpaint("clay", res=64)
api.meshpaint("image", view="Front", live=True, count=1)
print("RESULT", json.dumps({"PYTHONHOME": seen["env"].get("PYTHONHOME"), "PYTHONPATH": seen["env"].get("PYTHONPATH")}))
''')
    assert r.rc == 0, r.out[-2500:]
    env = r.results[0]
    assert env["PYTHONHOME"] is None
    assert env["PYTHONPATH"] == "/tmp/srv"


def test_project_refuses_with_the_instruction_when_the_tags_rebuild_does_not_exist_yet(tmp_path):
    """The projection reuses the rebuild's patched mesh (<out_root>/patched/<piece>_<tag>_uv_front-y.npz); without it the
    job died on a numpy FileNotFoundError minutes later (seen live). It is a refusal up front now, naming the step."""
    r = run(tmp_path, '''
setup(); api.meshpaint("clay", res=64)
os.makedirs(root + "/demo/meshpaint/set", exist_ok=True)
res = api.meshpaint("project", tag="p1")
print("RESULT", json.dumps({"res": res}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]["res"]
    assert res["ok"] is False and "rebuild" in res["error"] and "p1" in res["error"]
