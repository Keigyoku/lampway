# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""skeleton_export_check and engine_import_check (wiki/skeleton_export_check.md, wiki/engine_import_check.md): FBX files written by the real binary and read back."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

EXPORT = r'''
def export(path, objs, leaf=False, scale=1.0, unit=True):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, add_leaf_bones=leaf, global_scale=scale, apply_unit_scale=unit, bake_anim=False,
                             object_types={"ARMATURE", "MESH"}, primary_bone_axis="Z", secondary_bone_axis="X", path_mode="COPY")
BONES = (("pelvis", (0, 0, 1), (0, 0, 1.2), None), ("spine_01", (0, 0, 1.2), (0, 0, 1.5), "pelvis"), ("head", (0, 0, 1.5), (0, 0, 1.8), "spine_01"))
'''


def run(body, **kw):
    return run_script(PRE + EXPORT + body, timeout=300, **kw)


def test_an_export_with_leaf_bones_is_flagged_and_without_them_is_not():
    r = run('''
arm = armature("Armature", BONES)
a = os.path.join(root, "leaf.fbx"); b = os.path.join(root, "noleaf.fbx")
export(a, [arm], leaf=True); export(b, [arm], leaf=False)
ra = api.skeleton_export_check(fbx="leaf.fbx", target={"names_from": "noleaf.fbx"}); rb = api.skeleton_export_check(fbx="noleaf.fbx", target={"names_from": "noleaf.fbx"})
res({"a": ra, "b": rb})
''')
    assert r.rc == 0, r.out[-1200:]
    a, b = r.results[-1]["a"], r.results[-1]["b"]
    assert a["leaf_bones"] and all(n.endswith("_end") for n in a["leaf_bones"]) and a["pass"] is False and any("leaf" in x for x in a["reasons"])
    assert b["leaf_bones"] == [] and b["pass"] is True, b


def test_a_missing_bone_and_an_extra_bone_and_a_changed_parent_are_named_against_the_reference():
    r = run('''
ref = armature("Armature", BONES)
export(os.path.join(root, "ref.fbx"), [ref])
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
cand = armature("Armature", (("pelvis", (0, 0, 1), (0, 0, 1.2), None), ("spine_01", (0, 0, 1.2), (0, 0, 1.5), None), ("extra_bone", (0, 0, 1.5), (0, 0, 1.8), "spine_01")))
export(os.path.join(root, "cand.fbx"), [cand])
out = api.skeleton_export_check(fbx="cand.fbx", target={"names_from": "ref.fbx"})
res(out)
''')
    d = r.results[-1]
    assert d["missing_bones"] == ["head"] and d["extra_bones"] == ["extra_bone"] and d["hierarchy_mismatch"] == [{"bone": "spine_01", "parent": None, "expected_parent": "pelvis"}] and d["pass"] is False


def test_a_hundred_times_scale_is_reported_as_the_unit_scale():
    r = run('''
arm = armature("Armature", BONES)
export(os.path.join(root, "m.fbx"), [arm], scale=1.0)
export(os.path.join(root, "cm.fbx"), [arm], scale=100.0, unit=False)
out = api.skeleton_export_check(fbx="cm.fbx", target={"names_from": "m.fbx"})
ok = api.skeleton_export_check(fbx="m.fbx", target={"names_from": "m.fbx"})
res({"out": out, "ok": ok["unit_scale"]})
''')
    d = r.results[-1]
    assert abs(d["out"]["unit_scale"] - 100.0) < 5.0 and d["out"]["pass"] is False and any("scale" in x for x in d["out"]["reasons"]) and abs(d["ok"] - 1.0) < 0.05


def test_a_posed_armature_with_no_animation_is_reported_as_a_rest_pose_that_is_a_frame_and_a_clean_one_is_not():
    r = run('''
arm = armature("Armature", BONES)
clean = api.skeleton_export_check(armature="Armature", target={"names_from": None}) if False else None
a = api.skeleton_export_check(armature="Armature")
arm.pose.bones["spine_01"].rotation_mode = "XYZ"; arm.pose.bones["spine_01"].rotation_euler = (0.5, 0, 0)
b = api.skeleton_export_check(armature="Armature")
arm.pose.bones["spine_01"].rotation_euler = (0, 0, 0)
res({"clean": a["rest_vs_frame"], "posed": b["rest_vs_frame"], "posed_pass": b["pass"], "after": list(arm.pose.bones["spine_01"].rotation_euler)})
''')
    d = r.results[-1]
    assert d["clean"]["rest_pose_is_frame_zero"] is False and d["posed"]["rest_pose_is_frame_zero"] is True and d["posed"]["posed_bones"] == ["spine_01"] and d["posed_pass"] is False


def test_give_one_source_and_an_unreadable_reference_are_refused():
    r = run('''
armature("Armature", BONES)
res({"none": api.skeleton_export_check().get("error"), "both": api.skeleton_export_check(armature="Armature", fbx="x.fbx").get("error"), "bad": api.skeleton_export_check(armature="Armature", target={"names_from": "nope.fbx"}).get("error")})
''')
    d = r.results[-1]
    assert "give one" in d["none"] and "exactly one" in d["both"] and "nope.fbx" in d["bad"]


def test_the_fbx_header_version_collision_names_and_textures_are_checked_on_a_package():
    r = run('''
arm = armature("Armature", BONES); t = tube("Body", r=0.2, z0=1, z1=1.8)
pkg = os.path.join(root, "pkg"); os.makedirs(pkg + "/Textures")
from PIL import Image
Image.new("RGB", (4, 4)).save(pkg + "/Textures/BaseColor.png"); Image.new("RGB", (4, 4)).save(pkg + "/Textures/Unused.png")
m = bpy.data.materials.new("mat"); m.use_nodes = True; t.data.materials.append(m)
n = m.node_tree.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(pkg + "/Textures/BaseColor.png"); m.node_tree.links.new(n.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
n2 = m.node_tree.nodes.new("ShaderNodeTexImage"); n2.image = bpy.data.images.new("Gone", 4, 4); n2.image.filepath = pkg + "/Textures/Missing.png"; n2.image.source = "FILE"; m.node_tree.links.new(n2.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Roughness"])
good = tube("UCX_Body_00", r=0.2, z0=1, z1=1.8); orphan = tube("UCX_Wing_00", r=0.1, z0=1, z1=1.2)
export(pkg + "/Body.fbx", [arm, t, good, orphan])
out = api.engine_import_check(package_dir="pkg", engine="unreal", collision=["UCX_Body_00", "UCX_Wing_00"])
res(out)
''')
    d = r.results[-1]
    assert d["fbx"]["version_header"] >= 7400 and "Body" in d["fbx"]["mesh_names"]
    assert d["collision"]["mismatched"] == ["UCX_Wing_00"] and d["collision"]["found"] and any("Missing.png" in x for x in d["textures"]["missing"]) and any("Unused.png" in x for x in d["textures"]["unreferenced"])
    assert d["pass"] is False and d["receipt_recorded"] is False


def test_a_package_with_no_fbx_is_told_to_export_first_and_a_receipt_is_recorded_not_judged():
    r = run('''
os.makedirs(root + "/empty")
a = api.engine_import_check(package_dir="empty").get("error")
arm = armature("Armature", BONES); t = tube("Body", r=0.2, z0=1, z1=1.8); os.makedirs(root + "/p2")
export(root + "/p2/Body.fbx", [arm, t])
b = api.engine_import_check(package_dir="p2", receipt={"engine_version": "5.8", "wired_channels": ["BaseColor"], "notes": "by hand"})
res({"a": a, "b": b["receipt_recorded"], "pass": b["pass"]})
''')
    d = r.results[-1]
    assert "run export_piece first" in d["a"] and d["b"] is True and d["pass"] is True


def test_empty_comparison_and_missing_root_cannot_pass(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
from mixar.modules.lampway_tools.features import export_checks as E
if os.environ.get('LAMPWAY_REVERT_EXPORT_GUARD'):
    import inspect
    source=inspect.getsource(E.skeleton_check)
    guard=os.environ['LAMPWAY_REVERT_EXPORT_GUARD']
    block={'comparison': '    if frames["bones_compared"] == 0:' + chr(10) + '        reasons.append("no bone frames compared: provide target.names_from with a matching reference skeleton")' + chr(10),
           'root': '    if root_info["name"] is None:' + chr(10) + '        reasons.append("the checked skeleton has no root bone")' + chr(10)}[guard]
    assert block in source,'falsifier no longer matches the implementation'
    exec(source.replace(block,''),E.__dict__)
arm=bpy.data.armatures.new('Rig');ob=bpy.data.objects.new('Rig',arm);bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active=ob;ob.select_set(True)
bpy.ops.object.mode_set(mode='EDIT');bone=arm.edit_bones.new('root');bone.head=(0,0,0);bone.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
r=call('skeleton_export_check',armature=ob.name)
assert r['frames']['bones_compared']==0 and r['pass'] is False,r
assert r['root']['name']=='root' and any('compared' in x for x in r['reasons']),r
bpy.ops.object.mode_set(mode='EDIT');arm.edit_bones.remove(arm.edit_bones['root']);bpy.ops.object.mode_set(mode='OBJECT')
r=call('skeleton_export_check',armature=ob.name)
assert r.get('ok') and r['root']['name'] is None and r['pass'] is False,r
assert any('root' in x for x in r['reasons']),r
''')
