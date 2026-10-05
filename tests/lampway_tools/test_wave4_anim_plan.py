# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_clip planner, anim_track (a needs_decision stub with the licence and coverage rules) and the anim_from_video orchestrator, on fakes."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import anim_mv as MV  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_plan as AP  # noqa: E402


def test_the_clip_plan_carries_the_locked_camera_prompt_and_prices_the_job_without_spending():
    p = AP.clip_plan("ref_front.png", "front", "walk", has_camera_record=True)
    assert p["ok"] and p["spend"] is False and p["dry_run"] is True
    assert "locked camera, no cuts, no zoom, the whole body and feet in frame, walk in place" in p["video_gen"]["prompt"]
    assert p["video_gen"]["aspect_ratio"] == "9:16" and p["video_gen"]["duration"] == 5 and p["video_gen"]["resolution"] == "720p"
    assert p["price"]["higgsfield_credits"] == 22.5 and p["price"]["openrouter_usd"] == pytest.approx(0.76)
    assert "list price" in p["price"]["basis"] and "derived" in p["price"]["basis"]


def test_the_side_clip_takes_the_front_clip_as_its_video_reference_and_is_priced_lower():
    p = AP.clip_plan("ref_side.png", "side", "walk", driver_video="front_1.mp4", has_camera_record=True, route="openrouter")
    assert p["video_gen"]["videos"] == ["front_1.mp4"] and p["price"]["openrouter_usd"] == pytest.approx(0.46)


@pytest.mark.parametrize("kw,msg", [
    ({"aspect_ratio": "16:9"}, "16:9 halves the figure's pixel height"),
    ({"duration": 3}, "fewer than the 4 strides"),
    ({"has_camera_record": False}, "reference image missing the camera record: run anim_reference_render"),
    ({"view": "top"}, "view is front or side"),
])
def test_the_clip_plan_refuses_what_the_spec_refuses(kw, msg):
    args = {"reference_image": "r.png", "view": "front", "motion": "walk", "has_camera_record": True}
    args.update(kw)
    with pytest.raises(AP.PlanError, match=msg):
        AP.clip_plan(**args)


def test_a_failed_clip_gate_is_not_retried_it_goes_back_to_the_user():
    msg = AP.clip_refusal({"G-CLIP-fps": {"passed": False, "message": "duplicate frames 38 of 120 (the clip is upsampled)"}})
    assert "not accepted, not retried: ask the user" in msg and "duplicate frames 38 of 120" in msg
    assert AP.clip_refusal({"G-CLIP-fps": {"passed": True}}) is None


def test_track_refuses_gvhmr_for_shipping_missing_masks_and_a_windows_only_provider_elsewhere():
    ok = dict(clip="c.mp4", mask_dir="m", camera="cameras.json", skeleton="metahuman_base_skel")
    with pytest.raises(AP.PlanError, match="GVHMR's licence is research and non-profit only and needs SMPL-X; prototype only: pass shipping=false"):
        AP.track_plan(provider="gvhmr", shipping=True, **ok)
    with pytest.raises(AP.PlanError, match="mask_dir"):
        AP.track_plan(provider="sam3d_body", shipping=True, clip="c.mp4", mask_dir="", camera="cameras.json")
    with pytest.raises(AP.PlanError, match="Windows-only"):
        AP.track_plan(provider="mha_markerless", shipping=True, host="linux", **ok)
    proto = AP.track_plan(provider="gvhmr", shipping=False, **ok)
    assert proto["tag"] == "prototype" and proto["exportable"] is False


def test_the_undecided_providers_answer_needs_decision_with_the_question_and_the_slots():
    out = AP.track_plan(provider="sam3d_body", shipping=True, clip="c.mp4", mask_dir="m", camera="cameras.json")
    assert out["state"] == "needs_decision" and "provider" in out["question"]
    assert {s["id"] for s in out["slots"]} >= {"gem_x", "sam3d_body_hosted", "uthana"} and all(s["state"] == "needs_approval" for s in out["slots"])
    assert out["primary"] == "anim_multiview_fit"
    none = AP.track_plan(provider=None, shipping=True, clip="c.mp4", mask_dir="m", camera="cameras.json")
    assert none["state"] == "needs_decision"


def test_tracker_coverage_below_90_percent_fails_and_names_the_numbers():
    low = AP.coverage_gate([i for i in range(33)], 122)
    assert not low["passed"] and "33/122 frames (27 %) < 90 %" in low["message"]
    assert AP.coverage_gate(list(range(122)), 122)["passed"]


def test_the_bone_direction_retarget_equals_the_analytic_rotation_with_no_rest_pose_in_the_inputs():
    rest = np.array([[0.0, 0.0, -1.0]])
    target = np.array([[0.0, 1.0, 0.0]])
    q = MV.bone_rotations(rest, target)[0]
    w, x, y, z = q
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    assert np.allclose(R @ rest[0], target[0], atol=1e-9)


# ------------------------------------------------------------------------------------------------------------- the orchestrator
def _executors(calls, fail_clip=False):
    def render(params, prior):
        calls.append("render")
        return {"artefact": {"cameras": "known"}, "gates": {"rest-overlap": {"passed": True, "value": 0.99}}, "cost": 0}

    def clip(params, prior):
        calls.append("clip")
        return {"artefact": {"clip": "front.mp4"}, "gates": {"G-CLIP-fps": {"passed": not fail_clip, "value": 38, "message": "duplicate frames 38 of 120"}}, "cost": 22.5}

    def track(params, prior):
        calls.append("track")
        return {"artefact": {"poses": [1, 2, 3]}, "gates": {"coverage": {"passed": True, "value": 1.0}}, "cost": 0}

    def check(params, prior):
        calls.append("check")
        return {"artefact": {"check": "ok"}, "gates": {"G-LEGS": {"passed": True, "value": 0.9}}, "cost": 0}

    def export(params, prior):
        calls.append("export")
        return {"artefact": {"sequence": "walk.fbx"}, "gates": {"G-LOOP": {"passed": True, "value": 0.2}}, "cost": 0}
    return {"anim_reference_render": render, "anim_clip": clip, "anim_track": track, "anim_check": check, "anim_loop_export": export}


def test_nothing_is_spent_until_the_user_confirms_and_the_free_step_runs_first(tmp_path):
    calls = []
    out = AP.run_pipeline({"character": "Warrior", "motion": "walk"}, _executors(calls), confirm=False, out_dir=str(tmp_path))
    assert calls == ["render"] and out["state"] == "awaiting_confirm" and out["total_cost"] == 0
    assert out["spend_card"]["credits"] == 45.0 and "2 clips" in out["spend_card"]["text"]


def test_a_confirmed_run_goes_through_every_step_writes_decisions_and_replays_to_identical_hashes(tmp_path):
    calls = []
    out = AP.run_pipeline({"character": "Warrior", "motion": "walk"}, _executors(calls), confirm=True, out_dir=str(tmp_path))
    assert calls == ["render", "clip", "track", "check", "export"] and out["state"] == "done" and out["total_cost"] == 22.5
    rows = [json.loads(l) for l in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert [r["tool"] for r in rows] == ["anim_reference_render", "anim_clip", "anim_track", "anim_check", "anim_loop_export"]
    assert all(r["artefact_sha256"] and "ts" in r and r["by"] for r in rows)
    again = AP.replay(str(tmp_path), _executors([]))
    assert again["identical"] is True
    changed = _executors([])
    changed["anim_track"] = lambda params, prior: {"artefact": {"poses": [9, 9, 9]}, "gates": {}, "cost": 0}
    drift = AP.replay(str(tmp_path), changed)
    assert drift["identical"] is False and drift["mismatches"] == ["anim_track"]


def test_a_clip_that_fails_its_gate_never_reaches_the_tracker_and_the_run_stops_with_the_number(tmp_path):
    calls = []
    out = AP.run_pipeline({"character": "Warrior", "motion": "walk"}, _executors(calls, fail_clip=True), confirm=True, out_dir=str(tmp_path))
    assert "track" not in calls and out["state"] == "stopped" and out["stopped_at"] == "anim_clip"
    assert "duplicate frames 38 of 120" in out["message"] and "not retried" in out["message"]


def test_a_stock_animation_for_the_move_stops_the_plan_and_says_retarget():
    with pytest.raises(AP.PlanError, match="stock animation exists for this move"):
        AP.stock_check("walk", ["MF_Unarmed_Walk_Fwd", "MM_Idle"], stock_first=True)
    AP.stock_check("walk", ["MF_Unarmed_Walk_Fwd"], stock_first=False)
    AP.stock_check("flip", ["MF_Unarmed_Walk_Fwd"], stock_first=True)


def test_the_composite_plan_lists_the_five_steps_with_one_spend_card_and_the_open_provider_decision():
    plan = AP.plan_steps({"character": "Warrior", "motion": "walk", "views": ["front", "side"], "route": "higgsfield", "out_package": "/Game/Titan/Anim/Warrior", "stock_inventory": ["MM_Idle"]})
    assert [s["tool"] for s in plan["steps"]] == ["anim_reference_render", "anim_clip", "anim_track", "anim_check", "anim_loop_export"]
    assert plan["spend_card"]["credits"] == 45.0 and plan["spend"] is False and plan["total_cost"] == 0
    assert plan["steps"][1]["status"] == "needs_confirm" and plan["steps"][0]["status"] == "planned" and plan["steps"][0]["cost"] == 0
    assert plan["steps"][2]["status"] == "needs_decision" and plan["steps"][2]["tool"] == "anim_track"
    assert plan["decisions"].endswith("decisions.jsonl")
    with pytest.raises(AP.PlanError, match="stock animation exists for this move"):
        AP.plan_steps({"character": "Warrior", "motion": "idle", "stock_inventory": ["MM_Idle"]})
    assert AP.plan_steps({"character": "Warrior", "motion": "idle", "stock_inventory": ["MM_Idle"], "stock_first": False})["ok"]
