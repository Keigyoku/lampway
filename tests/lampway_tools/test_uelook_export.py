# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_export (specs/ue_parity/contracts/ue_export.md §10) in the REAL binary: one canonical export path per asset type, fixed
settings, a content hash with the FBX CreationTimeStamp zeroed, the UE import settings the editor leg must apply, and a read-back.
The input is canonical only (metres, transforms applied, +Z up: specs/canon/normalization/SCHEMA.md): an unapplied or negative
transform and a non-metre scene are refused, never fixed here. Colour spaces and the normal convention come from the declared
roles (pbr_pack's merge.json), never guessed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_fit_body_export import SETUP  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

HELP = r'''
from PIL import Image
from mixar.modules.lampway_tools.ue import export as UX
def cube(name="Prop", size=1.0):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.uv_layers.new(name="UVMap")
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob
def skinned():
    arm, body = body_package()
    pkg = api.fit_body("build", armature="body_rig", mesh="body_mesh", out="fit/body")["package"]
    p = piece_fit(arm); p.data.uv_layers.new(name="UVMap")
    write_json(os.path.join(root, "validation.json"), GOOD_VALIDATION); write_json(os.path.join(root, "bind_check.json"), {"ok": True})
    return arm, p, pkg
def pbr_dir(tag, colorspace=None):
    d = os.path.join(root, tag); os.makedirs(d, exist_ok=True)
    for n in ("BaseColor", "ORM", "Normal_DX"): Image.new("RGB", (4, 4)).save(os.path.join(d, n + ".png"))
    cs = colorspace if colorspace is not None else {"BaseColor": "sRGB", "ORM": "Non-Color", "Normal_DX": "Non-Color"}
    write_json(os.path.join(d, "merge.json"), {"convention": "dx", "colorspace": cs, "orm": "R occlusion, G roughness, B metallic (Unreal order), linear"})
    return d
'''


def run(body, **kw):
    r = run_script(PRE + SETUP + HELP + body, timeout=600, **kw)
    assert r.rc == 0, r.out[-3000:]
    return r.results[-1]


def test_exp01_one_path_per_type_with_exactly_its_settings_row():
    d = run('''
cube("Prop")
st = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/t1")
arm, p, pkg = skinned()
sk = api.ue_export(type="skinned_piece", object="piece_fit", armature="body_rig", body=pkg, validation="validation.json", bind_check="bind_check.json", out_dir="export/piece/t1")
gl = api.ue_export(type="skinned_piece", object="piece_fit", armature="body_rig", body=pkg, validation="validation.json", bind_check="bind_check.json", out_dir="export/piece/t2", format="gltf")
odd = api.ue_export(type="hair", object="Prop", out_dir="export/x")
ex = lambda r: json.load(open(os.path.join(r["out_dir"], "export.json"))) if r.get("ok") else None
res({"st": st, "sk": sk, "gl": gl, "odd": odd, "st_json": ex(st), "sk_json": ex(sk), "rows": {k: sorted(v) for k, v in UX.SETTINGS.items()},
     "st_imp": json.load(open(os.path.join(st["out_dir"], "ue_import.json"))), "files": sorted(os.listdir(st["out_dir"]))})
''')
    assert d["st"]["ok"] and d["sk"]["ok"], (d["st"], d["sk"])
    sj, kj = d["st_json"], d["sk_json"]
    assert sj["schema"] == "lampway.ue-export/1" and sj["type"] == "static_prop" and sorted(sj["settings"]) == d["rows"]["static_prop"]
    assert sj["settings"]["object_types"] == ["MESH"] and sj["settings"]["use_tspace"] is True and sj["settings"]["use_triangles"] is True
    assert kj["settings"]["object_types"] == ["ARMATURE", "MESH"] and kj["settings"]["primary_bone_axis"] == "Z" and kj["settings"]["add_leaf_bones"] is False
    assert kj["readback"]["joints"]["ok"] is True and kj["readback"]["joints"]["bones_compared"] == 3
    assert "UE 5.8 reads only 4 influences from glTF: FBX is the path" in d["gl"]["error"]
    assert "one canonical path per type" in d["odd"]["error"]
    assert d["st_imp"]["recompute_normals"] is False and d["st_imp"]["recompute_tangents"] is False and d["st_imp"]["high_precision_tangents"] is False
    assert {"Prop.fbx", "README.md", "export.json", "ue_import.json"} <= set(d["files"])


def test_exp02_the_skinned_readback_fails_with_primary_bone_axis_y():
    d = run('''
arm, p, pkg = skinned()
y = api.ue_export(type="skinned_piece", object="piece_fit", armature="body_rig", body=pkg, validation="validation.json", bind_check="bind_check.json", out_dir="export/piece/y", _bone_axis="Y")
res({"y": y})
''')
    assert d["y"]["ok"] is False and "read-back" in d["y"]["error"] and d["y"]["readback"]["joints"]["axis_max_deg"] > 45, d


def test_exp03_uv_range_without_hero_and_shape_keys_ue_drops():
    d = run('''
ob = cube("Prop")
ob.data.uv_layers[0].data[0].uv = (1.2, 0.5)
out = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/uv")
hero = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/uvhero", hero=True)
ob2 = cube("Morph")
ob2.shape_key_add(name="Basis"); k = ob2.shape_key_add(name="Tiny"); k.data[0].co.x += 0.0001
big = ob2.shape_key_add(name="Big"); big.data[1].co.z += 0.01
mo = api.ue_export(type="static_prop", object="Morph", out_dir="export/morph/t1")
res({"out": out, "hero": hero, "mo": mo})
''')
    assert d["out"]["ok"] is False and "16-bit UVs lose about 4 texels at 4096 outside [0,1]: keep UVs in range or set hero" in d["out"]["error"]
    assert d["hero"]["ok"] and d["mo"]["ok"]
    assert [x["shape_key"] for x in d["mo"]["losses"] if x["kind"] == "shape_key_below_ue_threshold"] == ["Tiny"], d["mo"]


def test_exp04_content_hash_is_stable_while_the_raw_bytes_differ():
    d = run('''
import time
cube("Prop")
a = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/a")
time.sleep(1.2)
b = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/b")
res({"a": a, "b": b})
''')
    a, b = d["a"], d["b"]
    assert a["ok"] and b["ok"], d
    assert a["file_sha256"] != b["file_sha256"], "the raw FBX bytes should differ (CreationTimeStamp)"
    assert a["content_sha256"] == b["content_sha256"] and len(a["content_sha256"]) == 64


def test_nrm03_nrm04_triangles_shared_with_the_bake_and_tangents_written():
    d = run('''
ob = cube("Prop")
tri = UX.triangles_sha256(ob)
write_json(os.path.join(root, "bake.json"), {"triangles_sha256": tri})
ok = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/b1", bake_receipt="bake.json")
write_json(os.path.join(root, "bake_other.json"), {"triangles_sha256": UX.triangles_sha256(ob, quad_method="ALTERNATE")})
other = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/b2", bake_receipt="bake_other.json")
res({"ok": ok, "other": other, "tri": tri, "polys": len(ob.data.polygons)})
''')
    ok = d["ok"]
    assert ok["ok"] and ok["triangles_sha256"] == d["tri"] and d["polys"] == 6                     # the captain's mesh keeps its quads
    rb = ok["readback"]
    assert rb["tangents_present"] and rb["binormals_present"] and rb["smoothing_present"] and rb["all_triangles"] and rb["triangles_match"]
    assert d["other"]["ok"] is False and "the normal map was baked on other triangles: re-bake after triangulation" in d["other"]["error"]


def test_anm01_animation_keys_every_frame_at_the_scene_rate():
    d = run('''
arm = armature("rig")
bpy.context.scene.render.fps = 30; bpy.context.scene.frame_start = 1; bpy.context.scene.frame_end = 31
arm.animation_data_create(); act = bpy.data.actions.new("Wave"); arm.animation_data.action = act
pb = arm.pose.bones["upperarm_l"]; pb.rotation_mode = "XYZ"
for f, a in ((1, 0.0), (16, 0.6), (31, 0.0)):
    pb.rotation_euler = (a, 0, 0); pb.keyframe_insert("rotation_euler", frame=f)
out = api.ue_export(type="animation", armature="rig", action="Wave", frame_rate=30, out_dir="export/anim/t1")
bad = api.ue_export(type="animation", armature="rig", action="Wave", frame_rate=24, out_dir="export/anim/t2")
res({"out": out, "bad": bad})
''')
    out = d["out"]
    assert out["ok"], out
    assert out["readback"]["frames"] == 31 and out["readback"]["animated_curves"] > 0
    assert out["readback"]["keys_per_curve"] == [31], out["readback"]
    assert "frame_rate 24 differs from the scene's 30 fps" in d["bad"]["error"]


def test_tex01_every_texture_carries_its_declared_colour_space():
    d = run('''
good = api.ue_export(type="texture_set", textures=pbr_dir("pbr1"), out_dir="export/tex/t1")
bad = api.ue_export(type="texture_set", textures=pbr_dir("pbr2", {"BaseColor": "sRGB", "Normal_DX": "Non-Color"}), out_dir="export/tex/t2")
res({"good": good, "bad": bad, "ej": json.load(open(os.path.join(good["out_dir"], "export.json"))) if good.get("ok") else None})
''')
    assert d["good"]["ok"], d["good"]
    tx = d["ej"]["textures"]
    assert tx["BaseColor.png"]["colorspace"] == "sRGB" and tx["ORM.png"]["colorspace"] == "Non-Color" and tx["Normal_DX.png"]["convention"] == "DirectX"
    assert all(len(v["sha256"]) == 64 for v in tx.values())
    assert d["bad"]["ok"] is False and "ORM.png has no colour space in merge.json" in d["bad"]["error"]


def test_geo05_canonical_input_only():
    d = run('''
a = cube("Neg"); a.scale = (-1, 1, 1)
b = cube("Moved"); b.location = (0.5, 0, 0)
neg = api.ue_export(type="static_prop", object="Neg", out_dir="export/neg")
moved = api.ue_export(type="static_prop", object="Moved", out_dir="export/moved")
cube("Prop")
first = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/once")
again = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/once")
bpy.context.scene.unit_settings.scale_length = 0.01
cm = api.ue_export(type="static_prop", object="Prop", out_dir="export/prop/cm")
res({"neg": neg, "moved": moved, "first": first, "again": again, "cm": cm, "names": sorted(o.name for o in bpy.data.objects), "loc": list(b.location)})
''')
    assert "negative scale" in d["neg"]["error"]
    assert "not canonical: its transform is not applied" in d["moved"]["error"] and d["loc"] == [0.5, 0.0, 0.0]
    assert d["first"]["ok"] and "exists" in d["again"]["error"]
    assert "metres" in d["cm"]["error"]
    assert d["names"] == ["Moved", "Neg", "Prop"]                                         # no temporary copy left behind
