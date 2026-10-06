"""The procedural library into the Vault (specs/asset_library/asset_seed_procedural.md): the client's 55 presets become ``material/procedural`` assets with their
script, their measured stats and a ball each. The export is a headless, niced Blender run; here a fake stands in for it, and the live test runs the real one."""
import itertools
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import procedural_seed as PS
from lampway_server.library import render as R
from lampway_server.library.store import AssetLibrary, LibraryError

BIN = os.environ.get("LAMPWAY_BIN")


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def export_doc(version="2", n=3, script_suffix=""):
    cats = ["metal", "leather", "embroidery"]
    mats = [{"material_id": f"m{i}", "name": f"Material {i}", "category": cats[i % 3], "template": "metal_base" if cats[i % 3] == "metal" else "leather_grain",
             "description": f"material {i}", "look_ref": None, "script": f"import bpy\n# m{i}{script_suffix}\n", "build_ms": 5.0, "generator": f"t@{i:016d}",
             "inputs": [{"name": "Wear", "default": 0.2, "min": 0.0, "max": 1.0}], "metallic_mean": 1.0 if cats[i % 3] == "metal" else 0.0, "roughness_mean": 0.3,
             "hue_deg": 30.0, "chroma": 0.4, "value_mean": 0.5, "base_color_mean": [0.6, 0.4, 0.2]} for i in range(n)]
    return {"library_version": version, "manifest_sha256": f"sha-{version}-{script_suffix}", "materials": mats}


def test_seed_makes_one_procedural_material_asset_per_preset_with_its_script_and_stats(tmp_path):
    lib = make_lib(tmp_path)
    out = PS.seed(lib, export_doc(), by="captain")
    assert out["created"] == 3 and out["count"] == 3
    a = lib.get(lib.resolve_asset(out["ids"]["m0"]))
    assert (a["kind"], a["subtype"], a["license_id"]) == ("material", "procedural", "GPL-3.0-or-later")
    assert [f["role"] for f in a["files"]] == ["script"]
    assert open(a["files"][0]["locations"][0]["path"]).read() == "import bpy\n# m0\n"
    assert a["stats"]["metallic_mean"] == 1.0 and a["stats"]["shader"] == "LWP_m0" and a["stats"]["role"] == "metal" and json.loads(a["stats"]["inputs_json"])[0]["name"] == "Wear"
    assert {(t["facet"], t["label"]) for t in a["terms"]} >= {("material_role", "plate_metal"), ("pipeline_stage", "library")}
    assert {(t["facet"], t["label"]) for t in lib.get(out["ids"]["m2"])["terms"]} >= {("material_role", "embroidery")}


def test_seed_is_idempotent_and_a_changed_manifest_at_the_same_version_is_refused(tmp_path):
    lib = make_lib(tmp_path)
    PS.seed(lib, export_doc(), by="captain")
    again = PS.seed(lib, export_doc(), by="captain")
    assert again["created"] == 0 and again["unchanged"] == 3
    with pytest.raises(LibraryError, match="library manifest changed: bump library_version or run seed --upgrade"):
        PS.seed(lib, export_doc(script_suffix="x"), by="captain")
    up = PS.seed(lib, export_doc(script_suffix="x"), by="captain", upgrade=True)
    assert up["new_versions"] == 3
    with pytest.raises(LibraryError, match="the user's click"):
        PS.seed(lib, export_doc(version="3"), by="agent")


def test_the_export_is_a_niced_headless_blender_run(tmp_path):
    calls = []

    def runner(argv, env=None, **kw):
        calls.append((argv, env))
        Path(argv[-1]).write_text(json.dumps(export_doc()))
        return subprocess.CompletedProcess(argv, 0, "", "")

    doc = PS.export("/opt/lampway/mixar", tmp_path / "work", runner=runner)
    argv, env = calls[0]
    assert argv[:3] == ["nice", "-n", "15"] and "-b" in argv and "--factory-startup" in argv and env["LAMPWAY_BRIDGE_PORT"] == "0"
    assert len(doc["materials"]) == 3


def test_a_material_thumbnail_is_its_eevee_ball(tmp_path):
    lib = make_lib(tmp_path)
    ids = PS.seed(lib, export_doc(n=1), by="captain")["ids"]
    calls = []

    def runner(argv, env=None, **kw):
        job = json.loads(open(argv[-1]).read())
        calls.append(job)                                                    # (a good job's directory is removed after it lands)
        Image.new("RGB", (job["size"], job["size"]), (180, 40, 30)).save(Path(job["out_dir"]) / "frame_000.png")
        return subprocess.CompletedProcess(argv, 0, "", "")

    rr = R.Renderer(lib, blender="/fake/mixar", runner=runner, loadavg=lambda: (0, 0, 0), live_window_cpu=lambda: 0.0)
    rr.enqueue(ids["m0"], ["thumb", "ball"])
    rr.drain()
    assert sorted(j["product"] for j in calls) == ["ball", "thumb"] and all(j["engine"] == "eevee" and j["kind"] == "material" and j["input_role"] == "script" for j in calls)
    roles = {f["role"] for f in lib.get(ids["m0"])["files"]}
    assert {"thumb", "ball", "script"} <= roles


@pytest.mark.skipif(not (BIN and Path(BIN).exists()), reason="needs the real binary: set LAMPWAY_BIN")
@pytest.mark.timeout(900)
def test_live_the_55_presets_seed_and_one_ball_per_category_is_lit_not_black_not_white(tmp_path):
    doc = PS.export(BIN, tmp_path / "work")
    assert len(doc["materials"]) == 55 and {m["category"] for m in doc["materials"]} == {"metal", "leather", "cloth", "embroidery"}
    lib = make_lib(tmp_path)
    ids = PS.seed(lib, doc, by="captain")["ids"]
    assert lib._reader().execute("select count(*) from asset where kind='material' and subtype='procedural'").fetchone()[0] == 55
    rr = R.Renderer(lib, blender=BIN, loadavg=lambda: (0, 0, 0), live_window_cpu=lambda: 0.0)
    pick = {"gold_polished", "leather_tan_worn", "cloth_woven_crimson", "embroidery_gold_on_red"}
    for mid in pick:
        rr.enqueue(ids[mid], ["ball"])
    rr.drain()
    for mid in pick:
        st = rr.status(ids[mid])["products"]["ball"]
        assert st["state"] == "done", (mid, st)
        img = np.asarray(Image.open(st["path"]).convert("RGB")).astype(float)
        centre = img[96:160, 96:160]
        assert 15 < centre.mean() < 245 and centre.std() > 1.0 and np.isfinite(centre).all(), (mid, centre.mean(), centre.std())
    sheet = PS.render_sheet(lib, "metal", tmp_path / "sheets")
    assert sheet["cells"] == 1 and Path(sheet["path"]).is_file()
