# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Auto-rig and fitting (Mixar docs "Auto Rig"; Stefan's rigging-existing-armor workflow: transfer weights from the aligned
body for deforming pieces, ONE bone at full influence for rigid plates, then test poses and look at stretch). Proven code: a
skeleton placed from measured landmarks of a T-pose mesh, Blender's heat-map weights with a proximity fallback, the Data
Transfer weight transfer, and a pose test that measures edge stretch instead of asserting it."""

from features_support import run


def test_a_humanoid_gets_a_ue_named_skeleton_inside_its_bounds_and_every_vertex_is_weighted(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
res = call("auto_rig", object="body", kind="humanoid")
rig = bpy.data.objects.get(res.get("armature", ""))
bones = {b.name: [list(b.head_local), list(b.tail_local)] for b in rig.data.bones} if rig else {}
me = body.data
unweighted = sum(1 for v in me.vertices if sum(g.weight for g in v.groups) < 1e-4)
arm_r = [v for v in me.vertices if v.co.x < -0.3]            # facing -Y (Blender front), the figure's RIGHT is -X
wsum = lambda v, names: sum(g.weight for g in v.groups if body.vertex_groups[g.group].name in names)
arm_share = sum(wsum(v, {"clavicle_r", "upperarm_r", "lowerarm_r", "hand_r"}) for v in arm_r) / max(1, len(arm_r))
print("RESULT", json.dumps({"res": res, "bones": bones, "unweighted": unweighted, "arm_share": arm_share,
                            "parent": body.parent.name if body.parent else None,
                            "mods": [m.type for m in body.modifiers]}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["armature"] == "body_rig" and out["parent"] == "body_rig" and "ARMATURE" in out["mods"]
    need = {"pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
            "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r"}
    assert need <= set(out["bones"]), need - set(out["bones"])
    assert out["unweighted"] == 0 and out["arm_share"] > 0.8, (out["unweighted"], out["arm_share"])
    b = out["bones"]
    assert b["head"][0][2] > b["spine_03"][0][2] > b["pelvis"][0][2] > b["foot_l"][0][2]        # head above chest above pelvis above feet
    assert b["hand_r"][0][0] < b["lowerarm_r"][0][0] < b["upperarm_r"][0][0] < 0 and b["hand_l"][0][0] > 0, "_r is the figure's right: -X when facing -Y"
    assert res["report"]["bones"] >= 20 and res["report"]["unweighted_vertices"] == 0 and res["report"]["weights"] in ("heat", "proximity")


def test_a_rigid_plate_binds_to_one_bone_at_full_weight_and_does_not_stretch_in_any_pose(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
rig = call("auto_rig", object="body", kind="humanoid")
plate = boxes("plate", [((0, -0.2, 1.15), (0.5, 0.06, 0.5))])
res = call("bind_to_armature", object="plate", armature="body_rig", mode="rigid", bone="spine_03")
vg = [g.name for g in plate.vertex_groups]
weights = {round(g.weight, 3) for v in plate.data.vertices for g in v.groups}
pose = call("pose_test", armature="body_rig", object="plate",
            poses=[{"name": "shoulders_up", "bone": "upperarm_r", "rotate": [0, 0, 80]}, {"name": "twist", "bone": "spine_03", "rotate": [0, 0, 40]}])
print("RESULT", json.dumps({"res": res, "vg": vg, "weights": sorted(weights), "pose": pose}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["vg"] == ["spine_03"] and out["weights"] == [1.0]
    assert out["pose"]["ok"] is True and [p["name"] for p in out["pose"]["poses"]] == ["shoulders_up", "twist"]
    assert all(p["max_edge_stretch"] < 1.001 for p in out["pose"]["poses"]), "a rigid plate on one bone keeps its shape"
    twist = next(p for p in out["pose"]["poses"] if p["name"] == "twist")
    assert twist["max_vertex_displacement"] > 0.02, "the twist actually moved the plate"


def test_a_deforming_piece_gets_its_weights_transferred_from_the_body_and_bends_where_the_body_does(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
call("auto_rig", object="body", kind="humanoid")
sleeve = boxes("sleeve", [((-0.55, 0, 1.30), (0.62, 0.16, 0.16))])      # the right arm: -X
res = call("bind_to_armature", object="sleeve", armature="body_rig", mode="transfer", source="body")
vg = sorted(g.name for g in sleeve.vertex_groups)
arm = sum(g.weight for v in sleeve.data.vertices for g in v.groups if sleeve.vertex_groups[g.group].name in ("upperarm_r", "lowerarm_r", "hand_r", "clavicle_r"))
tot = sum(g.weight for v in sleeve.data.vertices for g in v.groups)
pose = call("pose_test", armature="body_rig", object="sleeve", poses=[{"name": "elbow", "bone": "lowerarm_r", "rotate": [0, 0, 70]}])
print("RESULT", json.dumps({"res": res, "vg": vg, "arm_share": arm / tot, "pose": pose}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["res"]["mode"] == "transfer" and out["arm_share"] > 0.9
    assert out["pose"]["poses"][0]["max_vertex_displacement"] > 0.05


def test_studio_slot_and_refusals(tmp_path):
    r = run(tmp_path, '''
humanoid("body")
print("RESULT", json.dumps({"studio": call("auto_rig", object="body", engine="studio:tripo"),
                            "no_rig": call("bind_to_armature", object="body", armature="nope", mode="rigid", bone="x"),
                            "bad_kind": call("auto_rig", object="body", kind="dragon")}))
''')
    out = r.results[0]
    assert out["studio"]["needs_approval"] is True and "Auto Rig" in out["studio"]["action"]
    assert out["no_rig"]["ok"] is False and "nope" in out["no_rig"]["error"]
    assert out["bad_kind"]["ok"] is False and "dragon" in out["bad_kind"]["error"]


def test_the_proximity_fallback_weights_every_vertex_on_its_nearest_bones(tmp_path):
    """Heat can fail on non-manifold or open meshes; the fallback is a real algorithm, tested on its own."""
    r = run(tmp_path, '''
body = humanoid("body")
res = call("auto_rig", object="body", weights="proximity")
me = body.data
bad = sum(1 for v in me.vertices if abs(sum(g.weight for g in v.groups) - 1.0) > 1e-3)
arm_l = [v for v in me.vertices if v.co.x > 0.3]
share = sum(g.weight for v in arm_l for g in v.groups if body.vertex_groups[g.group].name in ("clavicle_l", "upperarm_l", "lowerarm_l", "hand_l")) / len(arm_l)
print("RESULT", json.dumps({"res": res, "not_normalised": bad, "arm_share": share}))
''')
    out = r.results[0]
    assert out["res"]["report"]["weights"] == "proximity" and out["res"]["report"]["unweighted_vertices"] == 0
    assert out["not_normalised"] == 0 and out["arm_share"] > 0.7
