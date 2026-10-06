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

GOLD = Path(__file__).parent / "canon_goldens" / "rig"
R01 = json.loads((GOLD / "R01_mapping.json").read_text())
R02 = json.loads((GOLD / "R02_rest_frames.json").read_text())
R03 = json.loads((GOLD / "R03_apply_scale.json").read_text())


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
