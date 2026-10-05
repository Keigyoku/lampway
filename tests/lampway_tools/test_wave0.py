# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wave 0: correctness defects found by reading the shipped tools (specs/BUILD_ORDER.md). Each test was RED first against the code as shipped:
asset_acceptance's identity gate that could not fail, rig_armor's rigid-mode stretch that cannot fail and its 4-pose set, a seam tear that the 1.35
stretch limit passes, auto_rig mutating its source, mesh_prep missing a flipped OPEN shell and hashing without UVs, and detail_normals having no caller.
REAL binary, synthetic shapes."""

from features_support import run

WIKI8 = ["idle", "shoulders_raised", "arm_across_chest", "elbow_flexion", "crouch", "torso_twist", "walk", "weapon_grip"]


# ------------------------------------------------------------------------------------------------ asset_acceptance: identity
def test_identity_fails_for_a_derivative_with_no_source_and_passes_once_its_source_is_the_reference(tmp_path):
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.features.workflows import mesh_hash
ref = boxes("ref", [((0, 0, 0), (1, 1, 1))])
deriv = boxes("deriv", [((0, 0, 0), (1, 1, 1.2))])
a = call("asset_acceptance", object="deriv", reference="ref")                     # a derivative that says where it came from: nothing
deriv["lw_source_hash"] = mesh_hash(ref)
b = call("asset_acceptance", object="deriv", reference="ref")                     # ... and now it does
deriv["lw_source_hash"] = "0" * 64
c = call("asset_acceptance", object="deriv", reference="ref")                     # a source that is NOT the reference
d = call("asset_acceptance", object="deriv", reference="deriv")
e = call("asset_acceptance", object="deriv")                                      # no reference, a bogus recorded source, no claim to check it against
del deriv["lw_source_hash"]
f = call("asset_acceptance", object="deriv")
g = call("asset_acceptance", object="deriv", source_hash="0" * 64)
print("RESULT", json.dumps({"a": a, "b": b, "c": c, "d": d, "e": e, "f": f, "g": g}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    gate = lambda k: o[k]["gates"]["identity"]                       # noqa: E731
    assert gate("a")["pass"] is False and "source" in " ".join(gate("a")["reasons"]) and o["a"]["accepted"] is False
    assert gate("b")["pass"] is True
    assert gate("c")["pass"] is False and "not the reference" in " ".join(gate("c")["reasons"])
    assert o["d"]["ok"] is False and "against itself" in o["d"]["error"]
    assert gate("f")["pass"] is False, "no reference, no recorded source: nothing says what this is derived from"
    assert gate("g")["pass"] is False
    assert any(c["id"] == "source_recorded" for c in gate("a")["checks"]), "each gate lists typed checks"


# ------------------------------------------------------------------------------------------------ rig_armor
RIG = '''
body = humanoid("body")
rigged = call("auto_rig", object="body", kind="humanoid")
'''


def test_the_pose_set_is_the_wikis_eight_and_a_pose_can_move_several_bones(tmp_path):
    r = run(tmp_path, RIG + '''
plate = boxes("plate", [((0, -0.2, 1.15), (0.5, 0.06, 0.5))])
res = call("rig_armor", object="plate", armature="body_rig", bone="spine_03")
one = call("pose_test", armature="body_rig", object="plate", poses=[{"name": "u", "bone": "upperarm_l", "rotate": [80, 0, 0]}])
two = call("pose_test", armature="body_rig", object=rigged["mesh"], poses=[
    {"name": "u", "bone": "upperarm_l", "rotate": [80, 0, 0]},
    {"name": "both", "bones": [{"bone": "upperarm_l", "rotate": [80, 0, 0]}, {"bone": "lowerarm_l", "rotate": [0, 0, -90]}]}])
print("RESULT", json.dumps({"names": [p["name"] for p in res["poses"]], "two": two, "one": one}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["names"] == WIKI8
    u, both = o["two"]["poses"]
    assert both["bones"] == ["upperarm_l", "lowerarm_l"] and u["bones"] == ["upperarm_l"] and both["max_vertex_displacement"] != u["max_vertex_displacement"], "the second bone moved the mesh"


def test_rigid_mode_fails_when_a_posed_leg_sweeps_through_the_plate(tmp_path):
    """Rigid on one bone cannot stretch (1.0 by construction), so the old pose test could not fail. The check that can: the plate against the POSED body."""
    r = run(tmp_path, RIG + '''
plate = sphere("plate", radius=0.05, subdiv=3, loc=(0.38, 0, 0.78))              # on the path the left leg sweeps when abducted 60 degrees (13 cm clear of it at rest), rigid on the pelvis
poses = [{"name": "leg_out", "bone": "thigh_l", "rotate": [0, 0, -60]}, {"name": "leg_in", "bone": "thigh_l", "rotate": [0, 0, 60]}]
bad = call("rig_armor", object="plate", armature="body_rig", bone="pelvis", poses=poses, clearance_body=rigged["mesh"])
rest = call("rig_armor", object="plate", armature="body_rig", bone="pelvis", poses=poses[1:], clearance_body=rigged["mesh"])
no_body = call("rig_armor", object="plate", armature="body_rig", bone="pelvis", poses=poses)
print("RESULT", json.dumps({"bad": bad, "rest": rest, "no_body": no_body}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    out, away = o["bad"]["poses"]
    assert o["bad"]["accepted"] is False and out["clearance"]["penetrating_vertices"] > 0 and out["clearance"]["min_m"] < 0
    assert away["clearance"]["penetrating_vertices"] == 0 and away["clearance"]["min_m"] > 0.0, "the leg moving away leaves a gap"
    assert all(p["max_edge_stretch"] < 1.001 for p in o["bad"]["poses"]), "stretch is 1.0 here: only the clearance can fail it"
    assert o["rest"]["accepted"] is True and o["rest"]["worst_clearance_m"] > 0
    assert o["no_body"]["stretch_check"] == "vacuous in rigid mode" and "clearance" in " ".join(o["no_body"]["not_checked"])


def test_a_seam_that_tears_fails_even_though_every_edge_stays_under_the_1_35_stretch_limit(tmp_path):
    """The user measured a 7.3 cm cuirass seam tear: two plates weighted to different bones. Edge stretch is per mesh edge and never sees a gap between shells."""
    r = run(tmp_path, RIG + '''
cuirass = boxes("cuirass", [((0.105, -0.2, 1.15), (0.2, 0.1, 0.4)), ((-0.105, -0.2, 1.15), (0.2, 0.1, 0.4))])          # two plates, a 5 mm seam gap
donor = boxes("donor", [((0.155, -0.2, 1.15), (0.29, 0.14, 0.44)), ((-0.155, -0.2, 1.15), (0.29, 0.14, 0.44))])        # the weights: left on the arm, right on the spine
for n in ("upperarm_l", "spine_03"):
    donor.vertex_groups.new(name=n)
for v in donor.data.vertices:
    donor.vertex_groups["upperarm_l" if v.co.x > 0 else "spine_03"].add([v.index], 1.0, "REPLACE")
res = call("rig_armor", object="cuirass", armature="body_rig", body="donor",
           poses=[{"name": "shoulder", "bone": "upperarm_l", "rotate": [80, 0, 0]}])
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["worst_stretch"] < 1.35, "each plate is rigid: the old limit passes it"
    assert res["max_seam_gap_m"] > 0.05 and res["accepted"] is False and res["max_seam_gap_limit_m"] == 0.01
    assert res["poses"][0]["seam_gap_m"] == res["max_seam_gap_m"]


# ------------------------------------------------------------------------------------------------ auto_rig
def test_auto_rig_leaves_its_source_alone_by_default_and_rigs_a_copy(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
res = call("auto_rig", object="body")
copy = bpy.data.objects.get(res.get("mesh", ""))
legacy = humanoid("old")
res2 = call("auto_rig", object="old", copy=False)
print("RESULT", json.dumps({"res": res, "src_parent": body.parent.name if body.parent else None, "src_vgs": len(body.vertex_groups), "src_mods": len(body.modifiers),
    "copy_parent": copy.parent.name if copy and copy.parent else None, "copy_vgs": len(copy.vertex_groups) if copy else 0, "copy_name": copy.name if copy else None,
    "legacy_parent": legacy.parent.name if legacy.parent else None, "res2_mesh": res2.get("mesh")}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["src_parent"] is None and o["src_vgs"] == 0 and o["src_mods"] == 0, "the source is untouched"
    assert o["copy_name"] == "body_rigged" and o["copy_parent"] == "body_rig" and o["copy_vgs"] >= 20 and o["res"]["mesh"] == "body_rigged"
    assert o["legacy_parent"] == "old_rig" and o["res2_mesh"] == "old", "copy=False is the explicit opt-in to rig in place"


# ------------------------------------------------------------------------------------------------ mesh_prep
def test_a_flipped_open_shell_is_flagged_and_repaired_and_a_correct_open_shell_is_not(tmp_path):
    r = run(tmp_path, '''
def open_tube(name, flip):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=24, radius1=0.5, radius2=0.5, depth=1.0)
    if flip:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
open_tube("good", False); open_tube("flipped", True)
good = call("mesh_prep", object="good")
flipped = call("mesh_prep", object="flipped")
fixed = bpy.data.objects[flipped["object"]]
from mixar.modules.lampway_tools.features import workflows as W
print("RESULT", json.dumps({"good": good, "flipped": flipped, "after": W.shell_orientation(fixed)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["good"]["found"]["inverted"] is False and o["good"]["shell_orientation"][0]["outward_fraction"] > 0.8
    assert o["flipped"]["found"]["inverted"] is True and o["flipped"]["shell_orientation"][0]["outward_fraction"] < 0.2
    assert o["after"][0]["outward_fraction"] > 0.8, "the branch has the shell turned right way out"


def test_a_uv_edit_changes_the_uv_hash_and_not_the_geometry_hash(tmp_path):
    r = run(tmp_path, '''
src = boxes("p", [((0, 0, 0), (1, 1, 1))])
bm = bmesh.new(); bm.from_mesh(src.data); uv = bm.loops.layers.uv.new("UVMap")
for f in bm.faces:
    for l in f.loops: l[uv].uv = (l.vert.co.x * 0.5 + 0.5, l.vert.co.y * 0.5 + 0.5)
bm.to_mesh(src.data); bm.free()
a = call("mesh_prep", object="p")
for d in src.data.uv_layers[0].data: d.uv = (d.uv[0] * 0.9, d.uv[1])
b = call("mesh_prep", object="p")
print("RESULT", json.dumps({"a": a["hash"], "b": b["hash"], "src_hash": a["source_hash"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["geometry"] == o["b"]["geometry"] == o["src_hash"] and o["a"]["uv"] != o["b"]["uv"]
    assert o["a"]["material"] == o["b"]["material"] and len(o["a"]["uv"]) == 64


# ------------------------------------------------------------------------------------------------ detail_normals has a caller
def test_detail_normals_is_a_tool_with_an_operator_feature_and_a_server_definition(tmp_path):
    r = run(tmp_path, '''
import os
acg = root + "/acg"
for d, f in (("Metal009", "Metal009_2K-PNG_NormalGL.png"), ("Metal048C", "Metal048C_2K-PNG_NormalGL.png")):
    os.makedirs(acg + "/" + d, exist_ok=True)
    im = bpy.data.images.new(f, 4, 4); im.filepath_raw = acg + "/" + d + "/" + f; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
mat = bpy.data.materials.new("textured_x"); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear(); N = nt.nodes; L = nt.links
out = N.new("ShaderNodeOutputMaterial"); bs = N.new("ShaderNodeBsdfPrincipled"); L.new(bs.outputs["BSDF"], out.inputs["Surface"])
N.new("ShaderNodeTexCoord"); bump = N.new("ShaderNodeBump"); L.new(bump.outputs["Normal"], bs.inputs["Normal"])
ok = call("detail_normals", material="textured_x", ambientcg_dir=acg, strengths={"plate": 0.9})
missing = call("detail_normals", material="nope", ambientcg_dir=acg)
from mixar.modules.lampway_tools.ui.properties import lampway_props as LP
import inspect
items = "detail_normals" in inspect.getsource(LP)
print("RESULT", json.dumps({"ok": ok, "missing": missing, "items": items,
                            "dn": sum(n.label.startswith("DN:") for n in nt.nodes)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["ok"]["ok"] is True and o["ok"]["strengths"]["plate"] == 0.9 and o["dn"] > 0
    assert o["missing"]["ok"] is False and "nope" in o["missing"]["error"]
    assert o["items"] is True, "the Features panel lists it"
