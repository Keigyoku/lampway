# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place, the scene kinds beyond a GLB (real binary): .blend append and link, an image as a reference empty, a video as a Movie Clip or a
sequencer strip, an action onto a matching armature, a rig attached to a mesh; the importers this build has."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402


def test_every_importer_the_tool_names_exists_in_this_build(tmp_path):
    d = one(go(tmp_path, '''
from mixar.modules.lampway_tools.features import asset_place as AP
ok = {}
for ext, op in AP.IMPORTER_OPS.items():
    mod, name = op.split(".")
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type(); ok[ext] = True
    except Exception as e:
        ok[ext] = repr(e)
print("RESULT", json.dumps(ok))
'''))
    assert set(d) >= {".glb", ".gltf", ".fbx", ".obj", ".usd", ".usdc", ".usdz"}, d
    assert all(v is True for v in d.values()), d


def test_place_blend_mesh_appends_and_link_refuses_managed_files(tmp_path):
    d = one(go(tmp_path, f'''
lib = {str(tmp_path / "helm.blend")!r}
bpy.ops.mesh.primitive_uv_sphere_add(); ob = bpy.context.active_object; ob.name = "Helm"
for c in list(ob.users_collection):
    c.objects.unlink(ob)
write_blend(lib, [ob])
a = place(asset=rec("mesh", lib, name="Helm"), mode="auto", target={{"where": "origin"}})
appended = bpy.data.objects.get(a["placed"][0]["object"]) if a.get("ok") else None
cas = rec("mesh", lib, name="Helm", aid="asset-cas"); cas["files"][0]["locations"][0]["storage"] = "cas"
l_cas = place(asset=cas, mode="link")
l_ext = place(asset=rec("mesh", lib, name="Helm", aid="asset-ext"), mode="link", target={{"where": "origin"}})
linked = bpy.data.objects.get(l_ext["placed"][0]["object"]) if l_ext.get("ok") else None
print("RESULT", json.dumps({{"a": a, "lib": appended.library is not None if appended else None, "lw": str(appended.get("lw_asset_id")) if appended else None,
    "in_scene": bool(appended and appended.name in bpy.context.scene.objects), "l_cas": l_cas, "l_ext": l_ext,
    "linked_lib": bool(linked and linked.instance_collection and all(o.library for o in linked.instance_collection.all_objects)),
    "linked_lw": str(linked.get("lw_asset_id")) if linked else None}}))
'''))
    assert d["a"]["ok"] and d["a"]["mode_used"] == "append", d["a"]
    assert d["lib"] is False and d["in_scene"] and d["lw"] == "asset-1"
    assert d["l_cas"]["ok"] is False and "managed files are immutable: use append or import" in d["l_cas"]["error"]
    assert d["l_ext"]["ok"] and d["l_ext"]["mode_used"] == "link" and d["linked_lib"] and d["linked_lw"] == "asset-ext", d


def test_place_image_as_a_reference_empty_and_attribution_is_returned(tmp_path):
    d = one(go(tmp_path, f'''
p = {str(tmp_path / "plate.png")!r}
png(p, w=16, h=8)
bpy.context.scene.cursor.location = (0.0, 1.0, 0.0)
r = place(asset=rec("image", p, subtype="plate", name="Plate", attribution="Plate by A. Person, CC-BY 4.0", license_id="cc-by-4.0"), mode="auto")
ob = bpy.data.objects.get(r["placed"][0]["object"]) if r.get("ok") else None
print("RESULT", json.dumps({{"r": r, "type": ob.type if ob else None, "disp": ob.empty_display_type if ob else None,
    "img": os.path.basename(ob.data.filepath) if ob and ob.data else None, "loc": list(ob.location) if ob else None, "lw": str(ob.get("lw_asset_id")) if ob else None}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "reference_image", d["r"]
    assert d["type"] == "EMPTY" and d["disp"] == "IMAGE" and d["img"] == "plate.png"
    assert d["loc"] == [0.0, 1.0, 0.0] and d["lw"] == "asset-1"
    assert d["r"]["attribution"] == "Plate by A. Person, CC-BY 4.0"


def test_place_video_adds_movieclip_or_a_sequencer_strip(tmp_path):
    d = one(go(tmp_path, f'''
p = {str(tmp_path / "walk.mp4")!r}
video(p)
r = place(asset=rec("video", p, subtype="reference", name="Walk"), mode="auto")
clip = bpy.data.movieclips.get(r["placed"][0]["datablock"]) if r.get("ok") else None
bpy.context.scene.frame_current = 7
s = place(asset=rec("video", p, subtype="reference", name="Walk", aid="asset-v2"), mode="add_clip", target={{"where": "sequencer"}})
se = bpy.context.scene.sequence_editor
strips = [(x.type, x.frame_start, str(x.get("lw_asset_id"))) for x in (se.strips_all if se else [])]
print("RESULT", json.dumps({{"r": r, "clip": [clip.frame_duration, list(clip.size), str(clip.get("lw_asset_id"))] if clip else None, "s": s, "strips": strips}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "add_clip" and d["r"]["placed"][0]["kind"] == "movieclip", d["r"]
    assert d["clip"] == [12, [64, 48], "asset-1"], d
    assert d["s"]["ok"] and d["s"]["placed"][0]["kind"] == "strip", d["s"]
    assert d["strips"] == [["MOVIE", 7.0, "asset-v2"]], d


def test_apply_animation_assigns_a_matching_action_and_refuses_a_bone_mismatch(tmp_path):
    d = one(go(tmp_path, f'''
lib = {str(tmp_path / "walk.blend")!r}
write_blend(lib, [keyed_action("WalkCycle", ("hip", "spine"))])
good = armature("Good", ("hip", "spine", "head"))
r = place(asset=rec("animation", lib, subtype="clip", name="WalkCycle"), mode="auto", target={{"where": "object:Good"}})
act = good.animation_data.action if good.animation_data else None
bad = armature("Bad", ("a", "b"))
r_bad = place(asset=rec("animation", lib, subtype="clip", name="WalkCycle", aid="asset-a2"), mode="apply_animation", target={{"where": "object:Bad"}})
print("RESULT", json.dumps({{"r": r, "act": act.name if act else None, "slot": bool(good.animation_data and good.animation_data.action_slot),
    "lw": str(act.get("lw_asset_id")) if act else None, "bad": r_bad, "bad_action": bool(bad.animation_data and bad.animation_data.action),
    "actions": sorted(a.name for a in bpy.data.actions)}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "apply_animation", d["r"]
    assert d["act"] == "WalkCycle" and d["slot"] and d["lw"] == "asset-1"
    assert d["bad"]["ok"] is False and "hip" in d["bad"]["error"] and "spine" in d["bad"]["error"] and "animation_retarget" in d["bad"]["error"]
    assert d["bad_action"] is False and d["actions"] == ["WalkCycle"], d


def test_attach_rig_brings_the_armature_and_binds_the_target_mesh(tmp_path):
    d = one(go(tmp_path, f'''
lib = {str(tmp_path / "rig.blend")!r}
rig = armature("BodyRig", ("hip", "spine"))
bpy.context.scene.collection.objects.unlink(rig)
write_blend(lib, [rig])
bpy.ops.mesh.primitive_cube_add(); body = bpy.context.active_object; body.name = "Body"
r = place(asset=rec("rig", lib, subtype="skeleton", name="BodyRig"), mode="auto", target={{"where": "object:Body"}})
arm = bpy.data.objects.get(r["placed"][0]["object"]) if r.get("ok") else None
mods = [(m.type, m.object.name if m.object else None) for m in body.modifiers]
print("RESULT", json.dumps({{"r": r, "arm": arm.type if arm else None, "parent": body.parent.name if body.parent else None, "mods": mods,
    "lw": str(arm.get("lw_asset_id")) if arm else None}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "attach_rig", d["r"]
    assert d["arm"] == "ARMATURE" and d["lw"] == "asset-1"
    assert d["parent"] == d["r"]["placed"][0]["object"] and d["mods"] == [["ARMATURE", d["r"]["placed"][0]["object"]]], d
