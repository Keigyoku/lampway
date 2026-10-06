# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_parity, the Lampway half (specs/ue_parity/contracts/ue_parity.md §4-§6, T-HAR-01/02) in the REAL binary: a standard scene
built from one JSON description in a throw-away scene, rendered headless in EEVEE under ue_look parity=true to float EXR, a
report naming versions and hashes; the UE half is needs_box until the captain's box time. Given UE captures, the same report
compares them per class (here a Lampway render stands in for the UE capture, so every class must pass)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uelook_support as U  # noqa: E402
from features_support import run  # noqa: E402

PARITY_EDITS = {"project__cvars__r.ReflectionMethod": 0, "post__bloom": 0.0, "post__vignette": 0.0, "post__ssao": 0.0, "exposure__bias": 0.0,
                "exposure__apply_physical_camera": False}

PROFILE = r'''
def parity_profile(**edits):
    p = json.loads(open(CUBE_PROFILE).read())
    for path, v in edits.items():
        node = p; keys = path.split("__")
        for k in keys[:-1]: node = node[k]
        node[keys[-1]] = v
    q = os.path.join(root, f"parity_{len(os.listdir(root))}.json"); open(q, "w").write(json.dumps(p)); return q
'''


def go(tmp_path, body):
    """A live-dump parity profile naming a SYNTHETIC cube; its view's config is generated in a first run and the body runs in a
    session started with it."""
    prof = U.profile_with_cube(tmp_path, "parity_base.json", edits=PARITY_EDITS)
    g = run(tmp_path, f'print("RESULT", json.dumps(call("ue_look", action="generate", profile={str(prof)!r})))', timeout=600)
    assert g.rc == 0 and g.results[0]["ok"], g.out[-3000:]
    r = run(tmp_path, f"CUBE_PROFILE = {str(prof)!r}\n" + PROFILE + body, env={"OCIO": g.results[0]["config_path"]}, timeout=900)
    assert r.rc == 0, r.out[-3000:]
    return r.results[0]


def test_har01_the_report_names_versions_hashes_and_the_ue_half_needs_box(tmp_path):
    d = go(tmp_path, '''
scenes0 = sorted(s.name for s in bpy.data.scenes); objs0 = sorted(o.name for o in bpy.data.objects)
prof = parity_profile()
r = call("ue_parity", scene="chart", profile=prof, size=64, views=["front"], out_dir="parity/chart/t1")
rep = json.load(open(os.path.join(r["out_dir"], "report.json"))) if r.get("ok") else None
exr = open(rep["views"]["front"]["lampway"]["exr"], "rb").read(4) if rep else None
print("RESULT", json.dumps({"r": r, "rep": rep, "exr_magic": list(exr) if exr else None, "scenes": sorted(s.name for s in bpy.data.scenes) == scenes0,
                            "objs": sorted(o.name for o in bpy.data.objects) == objs0, "md": os.path.isfile(os.path.join(r.get("out_dir", ""), "report.md"))}))
''')
    assert d["r"]["ok"], d["r"]
    rep = d["rep"]
    assert rep["schema"] == "lampway.ue-parity/1" and rep["versions"]["blender"] and rep["versions"]["ue"] == "5.8.2"
    assert len(rep["profile_sha256"]) == 64 and len(rep["scene_sha256"]) == 64 and len(rep["views"]["front"]["lampway"]["sha256"]) == 64
    assert d["exr_magic"] == [0x76, 0x2F, 0x31, 0x01] and d["md"]
    assert rep["views"]["front"]["ue"]["state"] == "needs_box" and set(rep["views"]["front"]["classes"].values()) == {"needs_box"}
    assert d["scenes"] and d["objs"]                                                    # the throw-away scene is gone
    cube = rep["views"]["front"]["cube"]
    assert len(cube["sha256"]) == 64 and cube["engine_version"] == "5.8.2" and cube["path"].endswith("test.cube")


def test_har02_the_scene_json_regions_are_where_blender_projects_the_patches(tmp_path):
    d = go(tmp_path, '''
from bpy_extras.object_utils import world_to_camera_view
from mixar.modules.lampway_tools.ue import parity_scene as PS
desc = PS.describe("chart", size=64, views=["front"])
sc = PS.build(desc, "front")
cam = sc.camera
err = 0.0
for patch, rect in zip(desc["objects"]["patches"], desc["regions"]["front"]["COL"]):
    v = world_to_camera_view(sc, cam, Vector(patch["location"]))
    px = (v.x * 64, (1 - v.y) * 64)
    err = max(err, abs(px[0] - (rect[0] + rect[2]) / 2), abs(px[1] - (rect[1] + rect[3]) / 2))
PS.discard(sc)
print("RESULT", json.dumps({"err": err, "hfov": desc["cameras"]["front"]["ue_hfov_deg"], "n": len(desc["regions"]["front"]["COL"])}))
''')
    assert d["err"] <= 0.5 and d["n"] == 21 and round(d["hfov"], 3) == 39.598, d


def test_refusals_and_the_compare_path_with_captures(tmp_path):
    d = go(tmp_path, '''
import shutil
bad = call("ue_parity", scene="chart", profile=parity_profile(post__bloom=0.675), size=64, out_dir="parity/x1")
dflt = call("ue_parity", scene="chart", size=64, out_dir="parity/x2")
armour = call("ue_parity", scene="armour:export/none", profile=parity_profile(), size=64, out_dir="parity/x3")
prof = parity_profile()
a = call("ue_parity", scene="furnace", profile=prof, size=64, views=["front"], out_dir="parity/f1")
cap = os.path.join(root, "caps"); os.makedirs(cap)
shutil.copy(os.path.join(a["out_dir"], "lampway_front.exr"), os.path.join(cap, "ue_front.exr"))
b = call("ue_parity", scene="furnace", profile=prof, size=64, views=["front"], out_dir="parity/f2", ue_captures="caps")
shutil.copy(os.path.join(a["out_dir"], "lampway_front.exr"), os.path.join(cap, "ue_front.png")); os.remove(os.path.join(cap, "ue_front.exr"))
c = call("ue_parity", scene="furnace", profile=prof, size=64, views=["front"], out_dir="parity/f3", ue_captures="caps")
rep = json.load(open(os.path.join(b["out_dir"], "report.json")))
print("RESULT", json.dumps({"bad": bad, "dflt": dflt, "armour": armour, "b": b, "c": c, "classes": rep["views"]["front"]["classes"], "shd": rep["views"]["front"]["metrics"]["SHD"]}))
''')
    assert "parity scenes compare with these off" in d["bad"]["error"] and "bloom" in d["bad"]["error"]
    assert not d["dflt"]["ok"] and "engine defaults are not the Titan project" in d["dflt"]["error"]
    assert not d["armour"]["ok"] and "ue_export receipt" in d["armour"]["error"]
    assert d["b"]["ok"] and d["classes"]["SHD"] == "pass" and d["classes"]["GEO"] == "pass" and d["shd"]["spheres"] == 10, d
    assert not d["c"]["ok"] and "mislabelled" in d["c"]["error"]
