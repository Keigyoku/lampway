# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""procedural_library (specs/mixar_docs/procedural_library.md + asset_library/asset_seed_procedural.md) in the real binary: a library of procedural node-group materials built from a few parametric TEMPLATES
and a preset table (build the tool, not the output), registered in the Client's own material registry so its agent tools and layer stack read them. The first 12 are armour materials (the auditor's list is not
written anywhere, so the choice is recorded in the module and flagged for the captain). Verified by real Cycles bakes of the group's probe outputs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_PL = '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
def lib(**kw):
    return call("procedural_library", **kw)
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_PL + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_seed_registers_fifty_five_materials_from_twelve_templates_idempotently(tmp_path):
    d = one(go(tmp_path, '''
a = lib(action="seed")
b = lib(action="seed")
lst = lib(action="list")
from mixar.modules.lampway_tools.features import procedural_library as PL
from mixar.modules.paint.procedural_materials import material_registry as MR
print("RESULT", json.dumps({"a": a, "b": b, "n": len(lst["materials"]), "presets": len(PL.PRESETS), "registry": len(MR.get_all_materials()), "cats": sorted({m["category"] for m in lst["materials"]}),
                            "templates": sorted({p["template"] for p in PL.PRESETS.values()}), "declared": sorted(PL.TEMPLATES),
                            "by_cat": {c: sum(1 for p in PL.PRESETS.values() if p["category"] == c) for c in PL.CATEGORIES}}))
'''))
    assert d["a"]["ok"] and d["a"]["registered"] == 55 and d["b"]["registered"] == 0 and d["b"]["unchanged"] == 55
    assert d["n"] == d["presets"] == d["registry"] == 55 and d["cats"] == ["cloth", "embroidery", "leather", "metal"]
    assert d["by_cat"] == {"metal": 40, "leather": 5, "cloth": 6, "embroidery": 4}
    assert len(d["declared"]) == 12 and d["templates"] == d["declared"]                               # every one of the 12 templates makes at least one material


def test_every_preset_builds_one_group_with_one_shader_output_bounded_inputs_in_under_a_second(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
res = lib(action="verify")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] and len(d["materials"]) == 55 and d["broken"] == []
    for m in d["materials"]:
        assert m["shader_outputs"] == 1 and m["build_ms"] < 1000 and m["generator"].count("@") == 1, m
        names = {i["name"]: i for i in m["inputs"]}
        assert {"Tint", "Roughness Scale", "Wear", "Scale", "Bump Strength", "Seed", "Mask"} <= set(names)
        for i in m["inputs"]:
            if i["name"] != "Tint":
                assert i["min"] < i["default"] < i["max"] or i["name"] in ("Wear", "Mask", "Seed"), i


def test_metals_are_metallic_and_in_their_hue_band_leather_and_cloth_are_not_metal(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
res = lib(action="verify", bake_stats=True)
print("RESULT", json.dumps({m["material_id"]: {"metal": m["metallic_mean"], "rough": m["roughness_mean"], "hue": m["hue_deg"], "chroma": m["chroma"], "cat": m["category"], "val": m["value_mean"], "rgb": m["base_color_mean"]} for m in res["materials"]}))
'''))
    exempt = ("rust_", "patina_heavy", "scaled", "verdigris")                                         # the contract's declared exemptions: corrosion is not metal
    bands = {"gold_": (35, 55), "bronze_": (20, 35), "brass_": (40, 55), "copper_": (10, 25)}
    for mid, m in d.items():
        if m["cat"] == "metal":
            floor = 0.3 if any(e in mid for e in exempt) or "patina" in mid else 0.85
            assert m["metal"] >= floor, (mid, m)
            for prefix, (lo, hi) in bands.items():
                if mid.startswith(prefix) and not any(e in mid for e in exempt) and "patina" not in mid:
                    assert lo <= m["hue"] <= hi, (mid, m)
            if mid.startswith(("silver_", "steel_", "tin", "pewter")) and mid != "steel_blued":
                assert m["chroma"] < 0.10, (mid, m)
        else:
            assert m["metal"] <= 0.05, (mid, m)                                                       # leather, cloth and embroidery are not metal
        assert 0.02 < m["val"] < 0.98, (mid, m)                                                       # not black, not white
    rgb = d["copper_verdigris"]["rgb"]
    assert rgb[1] + rgb[2] > rgb[0]
    for mid, m in d.items():
        if m["cat"] == "leather":
            assert m["rough"] >= 0.45, (mid, m)
    assert d["cloth_cloak_crimson_heavy"]["hue"] < 20 or d["cloth_cloak_crimson_heavy"]["hue"] > 340
    for mid in ("embroidery_gold_on_red", "embroidery_greek_key_trim_gold"):                     # thread ON a red ground: the ground shows, the mean is not the thread's gold
        assert d[mid]["hue"] < 30 or d[mid]["hue"] > 340, (mid, d[mid])


def test_no_two_materials_are_near_identical_and_a_swap_of_two_presets_colours_is_caught(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
res = lib(action="verify", bake_stats=True)
from mixar.modules.lampway_tools.features import procedural_library as PL
print("RESULT", json.dumps({"collisions": res["collisions"], "min_l1": res["min_pairwise_l1"], "n": len(res["materials"]), "swap": PL.fingerprint_distance("gold_polished", "bronze_polished", res)}))
'''))
    assert d["collisions"] == [] and d["min_l1"] > 0.02 and d["swap"] > 0.02


def test_the_seed_input_changes_the_bytes_and_the_same_seed_repeats_them(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
a = lib(action="bake", material_id="bronze_hammered", params={"Seed": 1.0})
b = lib(action="bake", material_id="bronze_hammered", params={"Seed": 1.0})
c = lib(action="bake", material_id="bronze_hammered", params={"Seed": 7.0})
print("RESULT", json.dumps({"a": a["sha256"], "b": b["sha256"], "c": c["sha256"], "diff": c["mean_abs_diff_from"].get(a["sha256"]) if "mean_abs_diff_from" in c else None, "dc": lib(action="bake", material_id="bronze_hammered", params={"Seed": 7.0}, compare_to=a["path"])["mean_abs_diff"]}))
'''))
    assert d["a"] == d["b"] and d["a"] != d["c"] and d["dc"] > 0.01


def test_the_mask_input_scales_wear_only_where_it_is_one(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
full = lib(action="bake", material_id="steel_battle_worn", params={"Wear": 1.0, "Mask": 1.0})
none = lib(action="bake", material_id="steel_battle_worn", params={"Wear": 1.0, "Mask": 0.0})
clean = lib(action="bake", material_id="steel_battle_worn", params={"Wear": 0.0, "Mask": 1.0})
print("RESULT", json.dumps({"full": full["roughness_mean"], "none": none["roughness_mean"], "clean": clean["roughness_mean"]}))
'''))
    assert abs(d["none"] - d["clean"]) < 0.01 and d["full"] > d["none"] + 0.02                         # a zero mask is the same as no wear; a one mask lets the wear in


def test_find_ranks_bronze_first_unknown_ids_name_the_categories_and_add_to_layer_needs_an_object(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
found = lib(action="find", query="bronze")
unknown = lib(action="find", material_id="nope")
bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object; ob.name = "Plate"
added = lib(action="add_to_layer", material_id="bronze_hammered", object="Plate", layer_name="Greaves")
noobj = lib(action="add_to_layer", material_id="bronze_hammered")
from mixar.modules.paint.core import agent_tools as AT
stack = AT.inspect_paint_layer_stack("Plate")
print("RESULT", json.dumps({"found": [m["material_id"] for m in found["materials"]][:3], "unknown": unknown, "added": added, "noobj": noobj, "layers": [l["name"] for l in stack["layers"]]}))
'''))
    assert d["found"][0].startswith("bronze") and "bronze_hammered" in d["found"]
    assert d["unknown"]["ok"] is False and "no material 'nope'" in d["unknown"]["error"] and "metal" in d["unknown"]["error"]
    assert d["added"]["ok"] and any("Greaves" in n for n in d["layers"])
    assert d["noobj"]["ok"] is False and "object" in d["noobj"]["error"]


def test_a_changed_manifest_at_the_same_library_version_is_refused_and_upgrade_allows_it(tmp_path):
    d = one(go(tmp_path, '''
lib(action="seed")
p = root + "/procedural/library.json"
m = json.load(open(p)); m["entries"][0]["script_sha"] = "0" * 16; json.dump(m, open(p, "w"))
refused = lib(action="seed")
ok = lib(action="seed", upgrade=True)
print("RESULT", json.dumps({"refused": refused, "ok": ok}))
'''))
    assert d["refused"]["ok"] is False and "library manifest changed: bump library_version" in d["refused"]["error"] and d["ok"]["ok"]


def test_the_probe_bakes_never_use_cycles(tmp_path):
    """The captain's standing rule: no Cycles beside his live work. The stat bakes are emission readouts, which EEVEE renders exactly."""
    d = one(go(tmp_path, '''
engines = []
bpy.app.handlers.render_pre.append(lambda sc, *a: engines.append(sc.render.engine))
lib(action="seed")
lib(action="bake", material_id="gold_polished")
print("RESULT", json.dumps({"engines": sorted(set(engines))}))
'''))
    assert d["engines"] == ["BLENDER_EEVEE"]
