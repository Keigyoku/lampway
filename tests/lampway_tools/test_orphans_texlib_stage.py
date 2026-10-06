# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Texture-library staging (STATUS O33): the rules of the shelf's stage_library_delta.py (a one-off recorded build for one library delta) made a tool
driven by a delta manifest: immutable versioned files with sha256 and size, lineage (parents) that resolves INSIDE the library (this delta or the current
library listing), unknown model / seed / cost recorded as null and never guessed, a colour space declared for every colour image, no inferred PBR map
(a data map needs the tool that measured or baked it), nothing written under an approved-release folder, and a staging root this tool made or none. Plus
the INDEX delta against a baseline listing (the shelf's index_delta.py, ported)."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import texlib_stage as TS  # noqa: E402

INDEX_DELTA = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts/texlib/index_delta.py"


def png(p, color=(120, 20, 20), size=(16, 8)):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(p)
    return p


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def manifest(tmp_path, **over):
    raw = png(tmp_path / "work" / "cape_raw.png")
    tile = png(tmp_path / "work" / "cape_tile.png", (100, 10, 10), (8, 8))
    m = {"library": "Texture Library", "library_version": "v0008", "previous_index": "INDEX.v0007.json",
         "approved_folders": ["09 Approved Textures/"],
         "catalog": {"file": "00 Catalog and Recipes/catalog.soft_materials.v0003.json", "previous": "catalog.soft_materials.v0002.json", "status": "RAW_CANDIDATES"},
         "files": [
             {"src": str(raw), "dst": "02 Generated Inputs/Cape_v0001/Cape_BaseColor_v0001.png", "role": "basecolor", "color_space": "sRGB",
              "provider": "OpenAI", "method": "image slot", "model_version": None, "seed": None, "cost": None, "parents": [], "status": "RAW_GENERATED"},
             {"src": str(tile), "dst": "07 QA/Tiles_v0004/Cape_BaseColor_Tile8_v0004.png", "role": "basecolor", "color_space": "sRGB",
              "provider": None, "method": "seamless_tile 1.7", "model_version": None, "seed": None, "cost": None,
              "parents": [{"file": "02 Generated Inputs/Cape_v0001/Cape_BaseColor_v0001.png", "sha256": sha(raw)}], "status": "SEAMLESS_GATE_PASSED"}]}
    m.update(over)
    return m


def test_a_delta_is_staged_with_hashes_lineage_a_catalog_and_an_index(tmp_path):
    out = TS.stage(manifest(tmp_path), tmp_path / "staging")
    lib = tmp_path / "staging" / "Texture Library"
    f = lib / "07 QA/Tiles_v0004/Cape_BaseColor_Tile8_v0004.png"
    rec = json.loads((lib / "07 QA/Tiles_v0004/Cape_BaseColor_Tile8_v0004.manifest.json").read_text())
    assert f.exists() and rec["sha256"] == sha(f) and rec["dimensions"] == [8, 8] and rec["approved_final_release"] is False and rec["seed"] is None
    idx = json.loads((lib / "INDEX.v0008.json").read_text())
    assert idx["previous_index"] == "INDEX.v0007.json" and idx["delta"] is True and "07 QA/Tiles_v0004/Cape_BaseColor_Tile8_v0004.png" in idx["files"]
    cat = json.loads((lib / "00 Catalog and Recipes/catalog.soft_materials.v0003.json").read_text())
    assert len(cat["adds"]) == 2 and cat["approved_final_release"] is False and out["files"] == 2


@pytest.mark.parametrize("mutate, needle", [
    (lambda m: m["files"][1]["parents"][0].update(file="02 Generated Inputs/Elsewhere.png"), "resolve inside the library"),
    (lambda m: m["files"][1]["parents"][0].update(sha256="0" * 64), "sha256"),
    (lambda m: m["files"][0].pop("seed"), "seed"),
    (lambda m: m["files"][0].update(seed="probably 42"), "seed"),
    (lambda m: m["files"][0].pop("color_space"), "colour space"),
    (lambda m: m["files"][0].update(role="normal", color_space="Non-Color"), "inferred"),
    (lambda m: m["files"][0].update(dst="09 Approved Textures/Cape/Cape_BaseColor_v0001.png"), "approved"),
    (lambda m: m["files"][0].update(dst="02 Generated Inputs/Cape_v0001/Cape_BaseColor.png"), "version"),
    (lambda m: m["files"][0].update(dst="../escape/Cape_v0001.png"), "inside the library")])
def test_each_rule_refuses_by_name(tmp_path, mutate, needle):
    m = manifest(tmp_path)
    mutate(m)
    with pytest.raises(TS.StageRefused, match=needle):
        TS.stage(m, tmp_path / "staging")
    assert not (tmp_path / "staging").exists(), "a refused delta leaves nothing staged"


def test_a_parent_already_in_the_library_listing_resolves_and_a_data_map_needs_its_maker(tmp_path):
    m = manifest(tmp_path)
    m["files"] = m["files"][1:]
    m["files"][0]["parents"] = [{"file": "02 Generated Inputs/Old/Cape_BaseColor_v0001.png", "sha256": "a" * 64}]
    listing = [{"Path": "02 Generated Inputs/Old/Cape_BaseColor_v0001.png", "Size": 3, "IsDir": False, "Hashes": {"sha256": "a" * 64}}]
    assert TS.stage(m, tmp_path / "s1", library_listing=listing)["files"] == 1
    m2 = manifest(tmp_path)
    m2["files"][0].update(role="roughness", color_space="Non-Color", derived_by="pbr_merge 2.0 (measured from the albedo's height bake)")
    assert TS.stage(m2, tmp_path / "s2")["files"] == 2


def test_a_staging_root_this_tool_did_not_make_is_never_replaced(tmp_path):
    other = tmp_path / "staging"; other.mkdir(); (other / "KEEP.txt").write_text("keep")
    with pytest.raises(TS.StageRefused, match="not made by this tool"):
        TS.stage(manifest(tmp_path), other)
    assert (other / "KEEP.txt").exists()
    TS.stage(manifest(tmp_path), tmp_path / "mine")
    TS.stage(manifest(tmp_path), tmp_path / "mine")                 # its own staging is replaced


def test_the_index_delta_lists_added_changed_and_removed_against_the_baseline(tmp_path):
    base = [{"Path": "a.png", "Size": 1, "Hashes": {"sha256": "1" * 64}}, {"Path": "b.png", "Size": 1, "Hashes": {"sha256": "2" * 64}},
            {"Path": "index.md", "Size": 1, "Hashes": {"sha256": "3" * 64}}]
    cur = [{"Path": "a.png", "Size": 1, "Hashes": {"sha256": "1" * 64}}, {"Path": "b.png", "Size": 1, "Hashes": {"sha256": "9" * 64}},
           {"Path": "c.png", "Size": 2, "Hashes": {"sha256": "4" * 64}}, {"Path": "02 x", "IsDir": True, "Size": -1}]
    (tmp_path / "base.json").write_text(json.dumps(base)); (tmp_path / "cur.json").write_text(json.dumps(cur))
    out = tmp_path / "INDEX.v0009.json"
    p = subprocess.run([sys.executable, str(INDEX_DELTA), str(tmp_path / "base.json"), str(tmp_path / "cur.json"), str(out), "INDEX.v0008.json", "a note"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    d = json.loads(out.read_text())
    assert list(d["added"]) == ["c.png"] and list(d["changed"]) == ["b.png"] and d["removed"] == [] and d["index_version"] == "v0009"
    again = subprocess.run([sys.executable, str(INDEX_DELTA), str(tmp_path / "base.json"), str(tmp_path / "cur.json"), str(out), "x", "y"], capture_output=True, text=True)
    assert again.returncode != 0 and "never overwritten" in again.stdout


def test_the_tool_answers_through_api_inside_the_root(tmp_path):
    from features_support import run
    m = manifest(tmp_path)
    for f in m["files"]:
        f["src"] = str(Path(f["src"]).relative_to(tmp_path))
    (tmp_path / "delta.json").write_text(json.dumps(m))
    r = run(tmp_path, '''
ok = call("texture_library_stage", manifest="delta.json", staging_root="staging")
out = call("texture_library_stage", manifest="delta.json", staging_root="/etc/x")
print("RESULT", json.dumps({"ok": ok, "out": out}))
''')
    assert r.rc == 0, r.out[-2000:]
    o = r.results[0]
    assert o["ok"]["ok"] and o["ok"]["files"] == 2 and Path(o["ok"]["index"]).exists(), o["ok"]
    assert o["out"]["ok"] is False, o["out"]
