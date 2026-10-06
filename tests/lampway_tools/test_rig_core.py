# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig tools' pure core (canon 16-18, rig_tools/ specs) against the canon goldens R01-R03 (synthetic, public-safe; vendored from the canon
spec tree): each test asserts the expected values AND that the upstream behaviour named as the falsifier misses them."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.rig_tools import core as RC  # noqa: E402

GOLD = Path(__file__).resolve().parents[2] / "docs" / "canon" / "goldens"
R01 = json.loads((GOLD / "R01_mapping" / "case.json").read_text())
R02 = json.loads((GOLD / "R02_rest_frames" / "case.json").read_text())
R03 = json.loads((GOLD / "R03_apply_scale" / "case.json").read_text())


# ---------------------------------------------------------------- R01 mapping (canon 16)
def test_the_family_is_the_table_naming_the_most_bones_and_a_tie_refuses():
    i = R01["input"]
    fam, hits = RC.detect_family(i["names"], i["tables"])
    assert fam == R01["expected"]["family"] and hits == R01["expected"]["hits"]
    with pytest.raises(RC.RigRefused, match="no single naming family"):
        RC.detect_family(i["tie_names"], i["tables"])


def test_the_slot_map_is_the_table_never_a_substring_guess():
    i = R01["input"]
    m, missing = RC.map_slots(i["names"], i["tables"]["mixamo"], i["required"])
    assert m == R01["expected"]["map"] and missing == R01["expected"]["missing_required"]
    # the falsifier: a substring rule takes the index finger for the hand
    assert R01["falsifier"]["substring_map"]["hand_l"] != m["hand_l"]


def test_missing_spine_joints_land_at_the_reference_fractions_not_the_midpoint():
    i = R01["input"]
    fr = RC.chain_fractions(i["ref_torso"])
    for k, v in R01["expected"]["fractions"].items():
        assert fr[k] == pytest.approx(v, abs=1e-8), k
    out = RC.synthesize_chain(i["src_torso"], fr)
    for k, v in R01["expected"]["synthesized"].items():
        assert np.allclose(out[k], v, atol=1e-8), (k, out[k])
    mid = np.asarray(R01["falsifier"]["midpoint_spine_03"])
    assert np.linalg.norm(mid - out["spine_03"]) == pytest.approx(R01["falsifier"]["midpoint_error_m"], abs=1e-6)


def test_a_chain_with_fewer_than_two_mapped_joints_cannot_synthesize():
    with pytest.raises(RC.RigRefused, match="two mapped joints"):
        RC.synthesize_chain([("pelvis", [0, 0, 1])], {"pelvis": 0.0, "spine_01": 0.5})


def test_the_shipped_tables_carry_their_provenance_and_name_ue_slots_only():
    for fam in ("mixamo", "rigify"):
        t = RC.load_family(fam)
        assert "MB UE5 Rig Creator Pro 3.1.0" in t["source"] and t["licence"] == "GPL-3.0-or-later"
        assert set(t["map"]) <= set(RC.UE_SLOTS), set(t["map"]) - set(RC.UE_SLOTS)
        assert len(set(t["map"].values())) == len(t["map"]), "one source bone per slot"
    for slot, name in R01["input"]["tables"]["mixamo"].items():
        assert RC.load_family("mixamo")["map"][slot] == name


# ---------------------------------------------------------------- R02 rest frames and conventions (canon 17)
def _chain():
    i = R02["input"]
    return [np.asarray(i["joints"][b]) for b in i["chain"]]


def test_frames_from_joints_and_an_up_hint_for_both_conventions():
    i, e = R02["input"], R02["expected"]
    for k, b in enumerate(i["chain"][:3]):
        head, child = i["joints"][b], i["joints"][i["chain"][k + 1]]
        Rb = RC.frame_from(head, child, i["up_hint"], along="y")
        Ru = RC.frame_from(head, child, i["up_hint"], along="x")
        assert np.allclose(Rb, e["frames_blender"][b], atol=1e-8) and np.allclose(Ru, e["frames_ue_axes"][b], atol=1e-8), b
        assert RC.along_axis_angle(Rb, head, child) == pytest.approx(e["angle_blender_deg"][b], abs=1e-5)
        assert RC.along_axis_angle(Ru, head, child) == pytest.approx(e["angle_ue_axes_deg"][b], abs=1e-5)


def test_the_convention_classifier_and_its_mixed_refusal():
    e = R02["expected"]
    assert RC.classify_convention(list(e["angle_blender_deg"].values())) == e["class_blender"]
    assert RC.classify_convention(list(e["angle_ue_axes_deg"].values())) == e["class_ue_axes"]
    assert RC.classify_convention([0.0, 90.0, 0.0]) == e["class_mixed"]


def test_a_frame_built_from_joints_has_no_input_roll_unlike_a_damped_track():
    i = R02["input"]
    head, child = i["joints"]["upperarm_l"], i["joints"]["lowerarm_l"]
    R = RC.frame_from(head, child, i["up_hint"])
    rolled = R @ RC.rot("y", 40.0)                      # the same bone rolled 40 deg about its own axis
    assert RC.angle_deg(RC.frame_from(head, child, i["up_hint"]), R) == pytest.approx(R02["falsifier"]["frame_from_roll_difference_deg"], abs=1e-6)
    assert RC.angle_deg(RC.damped_track(rolled, "y", np.subtract(child, head)), R) == pytest.approx(R02["falsifier"]["damped_track_roll_difference_deg"], abs=1e-4)


# ---------------------------------------------------------------- R03 apply object scale (canon 18)
def test_applying_a_non_uniform_scale_keeps_the_world_offset_exactly():
    i, e = R03["input"], R03["expected"]
    R = np.asarray(i["R_rest"])
    loc, Rn = RC.apply_scale_loc_exact(R, i["scale"], i["loc"])
    assert np.allclose(loc, e["new_loc"], atol=1e-9) and np.allclose(Rn, e["new_rest"], atol=1e-9)
    assert np.allclose(Rn @ loc, e["world_after"], atol=1e-9) and np.allclose(np.diag(i["scale"]) @ R @ i["loc"], e["world_offset"], atol=1e-9)
    u, _ = RC.apply_scale_loc_exact(R, i["uniform_scale"], i["loc"])
    assert np.allclose(u, e["uniform_new_loc"], atol=1e-9)
    # the falsifier: GRT's per-channel scaling (measured on Blender 5.2.1) misplaces the bone by 0.2236 m
    wrong = np.asarray(i["scale"]) * np.asarray(i["loc"])
    assert np.linalg.norm(Rn @ wrong - np.asarray(e["world_after"])) == pytest.approx(R03["falsifier"]["error_m"], abs=1e-6)


def test_the_unit_factor_is_a_known_factor_within_five_percent_or_refused():
    assert RC.unit_factor(1.80, 1.80) == (1.0, 1.0)
    f, ratio = RC.unit_factor(180.0, 1.80)
    assert f == 0.01 and ratio == pytest.approx(100.0)
    with pytest.raises(RC.RigRefused, match="5 %"):
        RC.unit_factor(2.4, 1.80)


# ---------------------------------------------------------------- R5 read-back rule (canon 21, the bind_mismatch bars)
def test_the_readback_rows_use_the_bind_mismatch_bars():
    ref = {"root": {"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]},
           "arm": {"translation": [10, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}}
    got = {"root": dict(ref["root"]), "arm": {"translation": [10.005, 0, 0], "rotation": [0, 0, 0.00008, 1], "scale": [1, 1, 1.00005]}}
    r = RC.readback_rows(ref, got)
    assert r["over_tolerance"] == [] and r["bones_compared"] == 2
    got["arm"]["translation"] = [10.02, 0, 0]
    assert [x["bone"] for x in RC.readback_rows(ref, got)["over_tolerance"]] == ["arm"]
    with pytest.raises(RC.RigRefused, match="roster"):
        RC.readback_rows(ref, {"root": ref["root"]})


# ---------------------------------------------------------------- R6 rig_conform's plan (canon 16 B.4-B.7, 17)
def _conform_fixture(roll_deg=0.0, extra=None):
    """R02's arm under R01's Mixamo torso: source frames rolled by roll_deg about their own Y; a reference (UE names, X along, Z = R02's up)."""
    i, j = R02["input"], R02["input"]["joints"]
    src_heads = {"Hips": (0, -0.02, 0.93), "Spine": (0, -0.015, 0.99), "Spine1": (0, -0.005, 1.06), "Spine2": (0, 0.0, 1.35),
                 "LeftArm": j["upperarm_l"], "LeftForeArm": j["lowerarm_l"], "LeftHand": j["hand_l"], "LeftMiddle1": j["middle_01_l"]}
    src_parents = {"Hips": None, "Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "LeftArm": "Spine2", "LeftForeArm": "LeftArm",
                   "LeftHand": "LeftForeArm", "LeftMiddle1": "LeftHand"}
    src_parents.update(extra or {})
    for b in extra or {}:
        src_heads.setdefault(b, (0.0, 0.1, 1.5))
    kids = {}
    for b, p in src_parents.items():
        if p:
            kids.setdefault(p, []).append(b)
    frames, lengths = {}, {}
    for b, h in src_heads.items():
        nxt = src_heads[kids[b][0]] if b in kids else np.add(h, (0, 0, 0.05))
        frames[b] = RC.frame_from(h, nxt, (1.0, 0.3, 0.2)) @ RC.rot("y", roll_deg)       # an arbitrary input roll
        lengths[b] = 0.05 + 0.01 * len(b)
    src = {"names": list(src_heads), "parents": src_parents, "heads": src_heads, "frames": frames, "lengths": lengths}
    mapping = {"pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_05": "Spine2", "upperarm_l": "LeftArm", "lowerarm_l": "LeftForeArm",
               "hand_l": "LeftHand", "middle_01_l": "LeftMiddle1"}
    fr = RC.chain_fractions(R01["input"]["ref_torso"])
    synthesized = {"spine_03": fr["spine_03"], "spine_04": fr["spine_04"]}
    ref_heads = dict(R01["input"]["ref_torso"])
    ref_heads.update({"upperarm_l": j["upperarm_l"], "lowerarm_l": j["lowerarm_l"], "hand_l": j["hand_l"], "middle_01_l": j["middle_01_l"],
                      "lowerarm_twist_01_l": j["lowerarm_l"]})
    ref_parents = {"pelvis": None, "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02", "spine_04": "spine_03", "spine_05": "spine_04",
                   "upperarm_l": "spine_05", "lowerarm_l": "upperarm_l", "lowerarm_twist_01_l": "lowerarm_l", "hand_l": "lowerarm_l", "middle_01_l": "hand_l"}
    ref_frames = {}
    for b in ref_heads:
        kid = {"pelvis": "spine_01", "spine_05": "upperarm_l", "upperarm_l": "lowerarm_l", "lowerarm_l": "hand_l", "hand_l": "middle_01_l"}.get(b)
        kid = kid or next((c for c, p in ref_parents.items() if p == b), None)
        nxt = ref_heads[kid] if kid else np.add(ref_heads[b], (0.05, 0, -0.02))
        if np.linalg.norm(np.subtract(nxt, ref_heads[b])) < 1e-9:
            nxt = np.add(ref_heads[b], (0.05, 0, -0.02))
        ref_frames[b] = RC.frame_from(ref_heads[b], nxt, i["up_hint"], along="x")
    ref = {"names": list(ref_heads), "parents": ref_parents, "heads": ref_heads, "frames": ref_frames}
    return src, mapping, synthesized, ref


def test_the_conform_plan_renames_synthesizes_at_r01_fractions_and_takes_the_reference_hierarchy():
    src, mapping, synth, ref = _conform_fixture(extra={"Prop": "LeftHand"})
    p = RC.conform_plan(src, mapping, synth, ref, convention="blender")
    by = {b["name"]: b for b in p["bones"]}
    assert p["renamed"] == {"Hips": "pelvis", "Spine": "spine_01", "Spine1": "spine_02", "Spine2": "spine_05", "LeftArm": "upperarm_l",
                            "LeftForeArm": "lowerarm_l", "LeftHand": "hand_l", "LeftMiddle1": "middle_01_l"}
    for k, v in R01["expected"]["synthesized"].items():          # R01: spine_03 / spine_04 at the reference's arc-length fractions
        assert np.allclose(by[k]["head"], v, atol=1e-8) and by[k]["kind"] == "synthesized", (k, by[k]["head"])
    assert [by[b]["parent"] for b in ("spine_03", "spine_04", "spine_05", "upperarm_l")] == ["spine_02", "spine_03", "spine_04", "spine_05"]
    assert by["Prop"]["parent"] == "hand_l" and by["Prop"]["kind"] == "unmapped", "an unmapped bone stays under its (renamed) parent"
    assert {"bone": "spine_05", "from": "spine_02", "to": "spine_04"} in p["reparented"]
    names = [b["name"] for b in p["bones"]]
    assert all(names.index(b["parent"]) < names.index(b["name"]) for b in p["bones"] if b["parent"]), "parents before children"
    for b in src["names"]:                                        # heads never move
        assert by[p["renamed"].get(b, b)]["head"] == tuple(float(x) for x in src["heads"][b])


def test_the_conform_frames_are_r02s_frames_whatever_the_input_roll():
    e = R02["expected"]
    plans = [RC.conform_plan(*_conform_fixture(roll), convention=c) for roll in (0.0, 40.0) for c in ("blender", "ue_axes")]
    for k, c in enumerate(("blender", "ue_axes") * 2):
        by = {b["name"]: b for b in plans[k]["bones"]}
        for bone in ("upperarm_l", "lowerarm_l", "hand_l"):
            assert np.allclose(by[bone]["frame"], e[f"frames_{c}"][bone], atol=1e-8), (c, bone)
            assert plans[k]["frames"][bone] == pytest.approx(0.0, abs=1e-6), "the reference's own frame, re-expressed in the convention"
    # the falsifier: the source's own (rolled) frame differs by the roll; the plan's does not
    src0, src40 = _conform_fixture(0.0)[0], _conform_fixture(40.0)[0]
    assert RC.angle_deg(src0["frames"]["LeftArm"], src40["frames"]["LeftArm"]) == pytest.approx(40.0, abs=1e-6)


def test_the_conform_plan_applies_a_named_roll_offset_and_refuses_a_mixed_convention():
    src, mapping, synth, ref = _conform_fixture()
    p = RC.conform_plan(src, mapping, synth, ref, convention="blender", offsets={"hand_l": {"roll_deg": 15.0}})
    assert {b["name"]: b for b in p["bones"]} and p["frames"]["hand_l"] == pytest.approx(15.0, abs=1e-6)
    with pytest.raises(RC.RigRefused, match="blender or ue_axes"):
        RC.conform_plan(src, mapping, synth, ref, convention="mixed")
    with pytest.raises(RC.RigRefused, match="no bone named 'nope'"):
        RC.conform_plan(src, mapping, synth, ref, offsets={"nope": {"roll_deg": 1.0}})


def test_a_colliding_unmapped_bone_is_renamed_out_of_the_way_first():
    src, mapping, synth, ref = _conform_fixture(extra={"spine_03": "Spine1"})      # an unmapped source bone already named like a synthesized slot
    p = RC.conform_plan(src, mapping, synth, ref)
    by = {b["name"]: b for b in p["bones"]}
    assert p["renamed"]["spine_03"] == "spine_03_src" and by["spine_03_src"]["kind"] == "unmapped" and by["spine_03"]["kind"] == "synthesized"
    assert by["spine_03_src"]["parent"] == "spine_02"


def test_ue_axes_follow_the_references_mirrored_side_where_x_points_back_along_the_limb():
    src, mapping, synth, ref = _conform_fixture()
    for b in ("upperarm_l", "lowerarm_l", "hand_l"):                   # UE's right-side style: X (and Y) turned to point back
        ref["frames"][b] = ref["frames"][b] @ RC.rot("z", 180.0)
    p = RC.conform_plan(src, mapping, synth, ref, convention="ue_axes")
    by = {b["name"]: b for b in p["bones"]}
    d = np.subtract(R02["input"]["joints"]["lowerarm_l"], R02["input"]["joints"]["upperarm_l"])
    assert float(np.asarray(by["upperarm_l"]["frame"])[:, 0] @ d) < 0 and p["frames"]["upperarm_l"] == pytest.approx(0.0, abs=1e-6)
    assert RC.angle_deg(by["upperarm_l"]["frame"], R02["expected"]["frames_ue_axes"]["upperarm_l"]) == pytest.approx(180.0, abs=1e-6)


def test_small_angles_are_measured_well_conditioned_on_float32_rest_data():
    """Blender stores rests in float32: an arccos of the trace (or of a quaternion dot) reads its rounding as ~0.02 deg, above the
    bind_mismatch bar (0.01 deg). The angle is measured by a chord formula instead (measured on 400 Blender bones: true error <= 1e-3 deg)."""
    rng = np.random.default_rng(7)
    worst_m = worst_q = 0.0
    for _ in range(200):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        x, y, z, w = q
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        worst_m = max(worst_m, RC.angle_deg(R.astype(np.float32).astype(float), R))
        worst_q = max(worst_q, RC._qangle_deg(q.astype(np.float32).astype(float), q))
    assert worst_m < 1e-4 and worst_q < 1e-4, (worst_m, worst_q)
    assert RC.angle_deg(np.eye(3), RC.rot("y", 1e-6)) == pytest.approx(1e-6, rel=1e-6)
    assert RC.angle_deg(np.eye(3), RC.rot("x", 179.0)) == pytest.approx(179.0, abs=1e-9)
    assert RC._qangle_deg([0, 0, 0, 1], [0, 0, np.sin(np.radians(0.5)), np.cos(np.radians(0.5))]) == pytest.approx(1.0, abs=1e-9)
    assert RC._qangle_deg([0, 0, 0, 1], [0, 0, 0, -1]) == pytest.approx(0.0, abs=1e-9), "q and -q are one rotation"


# ---------------------------------------------------------------- R7 rig_fit_template (canon 20) against R06
R06 = json.loads((GOLD / "R06_template_fit" / "case.json").read_text())


def _r06_template(extra=None):
    i = R06["input"]
    names = list(i["template"])
    heads = {n: tuple(i["template"][n]) for n in names}
    parents = dict(i["parents"])
    for n, (p, h) in (extra or {}).items():
        names.append(n)
        heads[n], parents[n] = tuple(h), p
    return {"names": names, "parents": parents, "heads": heads, "frames": {n: np.eye(3) for n in names}}


def test_the_fit_writes_the_measured_joints_and_reports_r06s_ratios():
    i, e = R06["input"], R06["expected"]
    f = RC.fit_template(_r06_template(), i["example_joints"], required=list(i["template"]))
    for n, v in e["heads"].items():
        assert np.allclose(f["heads"][n], v, atol=1e-12), n
    for n, v in e["length_ratios"].items():
        assert f["ratios"][n] == pytest.approx(v, abs=1e-9), n
    assert f["residual"]["max_m"] == e["residual_m"] and f["copied_not_fitted"] is e["copied_flag_fitted"]


def test_joints_copied_from_the_template_body_are_flagged_and_a_missing_joint_refuses():
    i = R06["input"]
    f = RC.fit_template(_r06_template(), i["template"], required=list(i["template"]))
    assert f["copied_not_fitted"] is R06["expected"]["copied_flag_copied"], "the falsifier: every ratio 1.000"
    j = dict(i["example_joints"])
    del j["head"]
    with pytest.raises(RC.RigRefused, match="head"):
        RC.fit_template(_r06_template(), j, required=list(i["template"]))


def test_unmeasured_bones_follow_their_measured_segment_and_a_parentless_one_the_whole_fit():
    i = R06["input"]
    t = i["template"]
    mid = tuple((np.add(t["lowerarm_l"], t["hand_l"]) / 2).tolist())
    extra = {"lowerarm_twist_01_l": ("lowerarm_l", mid), "root": (None, (0.0, 0.0, 0.0))}
    tpl = _r06_template(extra)
    tpl["parents"]["pelvis"] = "root"
    f = RC.fit_template(tpl, i["example_joints"], required=list(t))
    j = i["example_joints"]
    assert np.allclose(f["heads"]["lowerarm_twist_01_l"], np.add(j["lowerarm_l"], j["hand_l"]) / 2, atol=1e-9), "half way along the MEASURED forearm"
    assert f["synthesized"]["lowerarm_twist_01_l"]["rule"] == "segment lowerarm_l -> hand_l"
    assert f["synthesized"]["root"]["rule"] == "similarity of all measured joints" and "root" not in f["ratios"]


# ---------------------------------------------------------------- R8 rig_retarget (canon 19 B.1, B.5) against R04 / R05
R04 = json.loads((GOLD / "R04_retarget" / "case.json").read_text())
R05 = json.loads((GOLD / "R05_root_motion" / "case.json").read_text())


def test_the_retarget_rule_reproduces_r04_and_the_local_copy_misses_by_55_degrees():
    i = R04["input"]
    Rs = {k: np.asarray(v) for k, v in i["Rs_rest"].items()}
    Rt = {k: np.asarray(v) for k, v in i["Rt_rest"].items()}
    worst = 0.0
    for f in R04["expected"]["frames"]:
        Ws = {k: np.asarray(v) for k, v in f["Ws"].items()}
        Wt = {k: RC.retarget_world(Ws[k], Rs[k], Rt[k]) for k in Ws}
        for k in Wt:
            assert np.allclose(Wt[k], f["Wt"][k], atol=1e-8), k
        assert np.allclose(RC.local_from_world(Wt["B"], Wt["A"], Rt["B"], Rt["A"]), f["key"]["B"], atol=1e-8)
        worst = max(worst, RC.angle_deg(Rt["B"] @ (Rs["B"].T @ Ws["B"]), Wt["B"]))      # the falsifier: a local copy
    assert worst == pytest.approx(R04["falsifier"]["local_copy_max_error_deg"], abs=1e-4)


def test_the_root_comes_from_the_pelvis_never_tilted_and_recomposes_exactly():
    for f in R05["expected"]["frames"]:
        P = np.asarray(f["pelvis"])
        for mode in ("none", "heading"):
            root, local = RC.root_from_pelvis(P, yaw=mode)
            e = f["modes"][mode]
            assert np.allclose(root, e["root"], atol=1e-8) and np.allclose(local, e["pelvis_local"], atol=1e-8), (f["t"], mode)
            assert np.abs(root @ local - P).max() <= 1e-12 and root[2, 3] == 0.0 and RC.tilt_deg(root) == pytest.approx(0.0, abs=1e-9)
    full = max(RC.tilt_deg(np.asarray(f["pelvis"])) for f in R05["expected"]["frames"])
    assert full == pytest.approx(R05["falsifier"]["max_tilt_deg"], abs=1e-6), "copying the pelvis's whole rotation tilts the root"
    with pytest.raises(RC.RigRefused, match="none | heading"):
        RC.root_from_pelvis(np.eye(4), yaw="full")


def _quat(R):
    """xyzw of a rotation matrix (Shepperd)."""
    R = np.asarray(R, float)
    t = np.trace(R)
    if t > 0:
        s = 2.0 * np.sqrt(1.0 + t)
        return [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = 2.0 * np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k])
    q = [0.0, 0.0, 0.0, 0.0]
    q[i], q[j], q[k], q[3] = 0.25 * s, (R[j, i] + R[i, j]) / s, (R[k, i] + R[i, k]) / s, (R[k, j] - R[j, k]) / s
    return q


def test_g22_2_the_canonical_retarget_agrees_with_the_blender_rule_on_r04():
    """canon 22 G22.2: rig_convert's canonical retarget (TITAN's animation_canon, reference = bind) gives R04's W_s R_s^-1 R_t."""
    from mixar.modules.lampway_tools.rig_convert import animation_canon as ac
    i = R04["input"]
    Rs = {k: np.asarray(v) for k, v in i["Rs_rest"].items()}
    Rt = {k: np.asarray(v) for k, v in i["Rt_rest"].items()}

    def tf(p, R=None):
        return {"translation": [float(x) for x in p], "rotation": _quat(np.eye(3) if R is None else R), "scale": [1, 1, 1]}

    def prof(name, R, la):
        a, b = np.array([0.0, 0.0, 100.0]), None
        b = a + R["A"][:, 1] * la
        bones = [{"name": "root", "parent": None, "bind": tf([0, 0, 0]), "reference": tf([0, 0, 0])},
                 {"name": "A", "parent": "root", "bind": tf(a, R["A"]), "reference": tf(a, R["A"])},
                 {"name": "B", "parent": "A", "bind": tf(b, R["B"]), "reference": tf(b, R["B"])}]
        return ac.make_profile(name, bones, basis=[0, 0, 0, 1], centimeters_per_unit=1)
    src, tgt = prof("s", Rs, 100 * i["lengths"]["source_A"]), prof("t", Rt, 100 * i["lengths"]["target_A"])
    frames = R04["expected"]["frames"]
    times = ac.sample_times(f"{(len(frames) - 1) / 30:.9f}")
    assert len(times) == len(frames)
    samples = []
    for t, f in zip(times, frames):
        a = np.array([0.0, 0.0, 100.0])
        WsA, WsB = np.asarray(f["Ws"]["A"]), np.asarray(f["Ws"]["B"])
        samples.append({"time": t, "pose": {"root": tf([0, 0, 0]), "A": tf(a, WsA), "B": tf(a + WsA[:, 1] * 100 * i["lengths"]["source_A"], WsB)}})
    packet = ac.normalize(samples, src, duration=f"{(len(frames) - 1) / 30:.9f}", channels={})
    rules = {"map": {"root": "root", "A": "A", "B": "B"}, "reference_follow": [], "translation_scales": {"root": 1, "A": 1, "B": 1}, "anchors": {}}
    out = ac.adapt(ac.retarget(packet, tgt, rules), tgt)
    worst = 0.0
    for f, pose in zip(frames, out):
        for n in ("A", "B"):
            want = _quat(np.asarray(f["Wt"][n]))
            got = pose["pose"][n]["rotation"]
            worst = max(worst, RC._qangle_deg(got, want))
    assert worst < 1e-5, worst
    # the comparison can fail: the source's own world rotations are tens of degrees from R04's target rotations
    assert max(RC._qangle_deg(_quat(np.asarray(f["Ws"][n])), _quat(np.asarray(f["Wt"][n]))) for f in frames for n in ("A", "B")) > 20


# ---------------------------------------------------------------- R11 rig_rest_pose (canon 19 B.7, canon 04) against R07
R07 = json.loads((GOLD / "R07_rest_change" / "case.json").read_text())
C02 = GOLD / "C02_inverse_lbs"


def _c02():
    w = json.loads((C02 / "weights.json").read_text())
    V = np.array([[float(x) for x in ln.split()[1:4]] for ln in (C02 / "piece_fit_pose.obj").read_text().splitlines() if ln.startswith("v ")])
    return V, np.array(w["W"]), [np.eye(4), np.array(w["fit_pose"]["B"])]


def test_the_return_cost_of_a_baked_rest_is_the_blend_of_inverses_and_the_exact_inverse_returns_zero():
    V, W, mats = _c02()
    from mixar.modules.lampway_tools.canon_geom.lbs import lbs_inverse
    v0 = lbs_inverse(V, W, mats)                         # the rest whose pose is V; V becomes the new rest, bind = the pose
    cost = RC.return_cost(V, v0, W, mats)
    f, e = R07["falsifier"], R07["expected"]
    assert cost["blend_of_inverses_max_m"] == pytest.approx(f["apply_pose_as_rest_then_return_max_m"], abs=1e-6)
    assert cost["vertices_over_1mm"] == f["vertices_over_1mm"]
    assert cost["exact_return_max_m"] <= 1e-12 and cost["rigid_vertices_error_m"] == pytest.approx(e["rigid_vertices_error_m"], abs=1e-12)
