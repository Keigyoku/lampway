# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""modular_character (specs/wiki/modular_character.md) in the real binary: a typed manifest of a character's parts, one shared armature, an outfit matrix
that proves every allowed outfit covers the body before a hidden-body variant may exist, and per-part exports with the same armature."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

SCENE = '''
rig = armature()
capped_sphere("body", radius=0.5)
capped_sphere("robe", radius=0.6)
capped_sphere("vest", radius=0.6, cut_z=GAP)
for o in ("body", "robe", "vest"):
    bind(o)
PARTS = [{"object": "body", "role": "body", "fixed_or_deforming": "fixed", "wearer_side": "center", "bone": "root"},
         {"object": "robe", "role": "garment", "fixed_or_deforming": "fixed", "wearer_side": "center", "bone": "root"},
         {"object": "vest", "role": "garment", "fixed_or_deforming": "fixed", "wearer_side": "center", "bone": "root"}]
m = call("modular_character", action="manifest", character_id="hero", parts=PARTS, armature="rig", allowed_outfits=[["robe"], ["vest"]])
assert m["ok"], m
'''


def test_hidden_body_is_refused_before_a_passing_outfit_matrix(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "0.3") + '''
res = call("modular_character", action="hidden_body", character_id="hero")
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    assert d["res"]["ok"] is False and "test every wardrobe combination first" in d["res"]["error"]
    assert "body_hidden" not in d["objects"]


def test_the_matrix_reports_uncovered_faces_for_an_outfit_that_leaves_a_gap_and_zero_once_the_gap_is_covered(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "0.3") + '''
gap = call("modular_character", action="outfit_matrix", character_id="hero")
bpy.data.objects.remove(bpy.data.objects["vest"])
capped_sphere("vest", radius=0.6)
bind("vest")
closed = call("modular_character", action="outfit_matrix", character_id="hero")
print("RESULT", json.dumps({"gap": gap, "closed": closed}))
'''))
    rows = {tuple(r["outfit"]): r for r in d["gap"]["matrix"]}
    assert d["gap"]["ok"] and rows[("robe",)]["uncovered_body_faces"] == 0 and rows[("robe",)]["pass"] is True
    assert rows[("vest",)]["uncovered_body_faces"] > 0 and rows[("vest",)]["pass"] is False and d["gap"]["pass"] is False
    closed = {tuple(r["outfit"]): r for r in d["closed"]["matrix"]}
    assert closed[("vest",)]["uncovered_body_faces"] == 0 and d["closed"]["pass"] is True          # the falsifier: the same outfit with the gap covered


def test_a_body_poking_through_a_garment_counts_penetrating_vertices(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None").replace('capped_sphere("robe", radius=0.6)', 'capped_sphere("robe", radius=0.49)') + '''
res = call("modular_character", action="outfit_matrix", character_id="hero")
print("RESULT", json.dumps(res))
'''))
    rows = {tuple(r["outfit"]): r for r in d["matrix"]}
    assert rows[("robe",)]["penetrating_vertices"] > 0 and rows[("robe",)]["pass"] is False
    assert rows[("vest",)]["penetrating_vertices"] == 0


def test_hidden_body_after_a_passing_matrix_is_a_copy_without_the_covered_faces_and_the_body_is_untouched(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
before = len(bpy.data.objects["body"].data.polygons)
mx = call("modular_character", action="outfit_matrix", character_id="hero")
res = call("modular_character", action="hidden_body", character_id="hero")
print("RESULT", json.dumps({"mx": mx, "res": res, "before": before, "after": len(bpy.data.objects["body"].data.polygons),
                            "hidden": len(bpy.data.objects[res["object"]].data.polygons) if res.get("ok") else None}))
'''))
    assert d["mx"]["pass"] is True and d["res"]["ok"], d["res"]
    assert d["res"]["object"] == "body_hidden" and d["after"] == d["before"] and d["res"]["removed_faces"] == d["before"] and d["hidden"] == 0


def test_a_change_after_the_matrix_makes_hidden_body_refuse_again(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
call("modular_character", action="outfit_matrix", character_id="hero")
bpy.data.objects["vest"].data.vertices[0].co.z += 0.2
res = call("modular_character", action="hidden_body", character_id="hero")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] is False and "test every wardrobe combination first" in d["error"] and "changed" in d["error"]


def test_parts_bound_to_two_armatures_are_refused(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
armature("rig2", loc=(0, 0, 0))
bind("vest", arm="rig2")
res = call("modular_character", action="validate", character_id="hero")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] is False and "all parts must share one armature" in d["error"] and "rig2" in d["error"]


def test_validate_reports_the_shared_armature_rest_pose_scale_and_sides(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
capped_sphere("glove_l", radius=0.05, loc=(0.4, 0, 0.5)); bind("glove_l")
call("modular_character", action="manifest", character_id="hero", parts=PARTS + [{"object": "glove_l", "role": "hands", "fixed_or_deforming": "fixed", "wearer_side": "left", "bone": "root"}],
     armature="rig", allowed_outfits=[["robe"], ["vest"]])
ok = call("modular_character", action="validate", character_id="hero")
bpy.data.objects["glove_l"].location.x = -0.4
bpy.context.view_layer.update()
wrong = call("modular_character", action="validate", character_id="hero")
bpy.data.objects["glove_l"].location.x = 0.4
bpy.data.objects["glove_l"].scale = (2, 2, 2)
scaled = call("modular_character", action="validate", character_id="hero")
print("RESULT", json.dumps({"ok": ok, "wrong": wrong, "scaled": scaled}))
'''))
    ok = d["ok"]
    assert ok["ok"] and ok["shared_armature"] is True and ok["rest_pose_equal"] is True and ok["unit_scale_equal"] is True and ok["sides_ok"] is True and ok["pass"] is True
    assert d["wrong"]["sides_ok"] is False and d["wrong"]["sides"]["glove_l"] == {"declared": "left", "measured": "right"} and d["wrong"]["pass"] is False
    assert d["scaled"]["unit_scale_equal"] is False and d["scaled"]["pass"] is False


def test_the_manifest_has_the_template_fields_and_refuses_a_fixed_part_without_a_bone(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
bad = call("modular_character", action="manifest", character_id="hero", parts=PARTS[:1] + [{"object": "robe", "role": "garment", "fixed_or_deforming": "fixed", "wearer_side": "center"}], armature="rig")
role = call("modular_character", action="manifest", character_id="hero", parts=[dict(PARTS[0], role="cape")], armature="rig")
print("RESULT", json.dumps({"m": m, "bad": bad, "role": role, "file": json.load(open(os.path.join(root, "hero", "manifest.json")))}))
'''))
    f = d["file"]
    for k in ("character_id", "source_part_ids", "target_skeleton", "rest_pose", "unit_scale", "wearer_left_right", "fixed_deforming", "shared_materials",
              "allowed_outfits", "tested_poses", "accepted_checkpoint"):
        assert k in f, k
    assert f["source_part_ids"] == ["body", "robe", "vest"] and f["target_skeleton"] == "rig" and f["allowed_outfits"] == [["robe"], ["vest"]]
    assert d["bad"]["ok"] is False and "robe" in d["bad"]["error"] and "bone" in d["bad"]["error"]
    assert d["role"]["ok"] is False and "head, body, hands, hair, garment, accessory" in d["role"]["error"]


def test_export_parts_writes_one_fbx_per_part_with_the_same_armature(tmp_path):
    d = one(go(tmp_path, SCENE.replace("GAP", "None") + '''
res = call("modular_character", action="export_parts", character_id="hero", out_dir="exports")
arms = {}
for f in res.get("files", []):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.fbx(filepath=os.path.join(root, f["path"]))
    arms[f["part"]] = sorted(o.name for o in bpy.data.objects if o.type == "ARMATURE")
print("RESULT", json.dumps({"res": res, "arms": arms}))
'''))
    res = d["res"]
    assert res["ok"] and [f["part"] for f in res["files"]] == ["body", "robe", "vest"]
    assert all(f["path"].startswith("exports/hero/") and f["path"].endswith(".fbx") and len(f["sha256"]) == 64 for f in res["files"])
    assert d["arms"] == {"body": ["rig"], "robe": ["rig"], "vest": ["rig"]}
