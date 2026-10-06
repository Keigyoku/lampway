# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""character_pipeline (specs/wiki/character_pipeline.md): the character route as thirteen gated stages. It plans with spend flags, records gates, refuses rigging
before assembly ("fit before rigging"), stops a run at the first failed gate and at the first spend, and stubs the MetaHuman conform (a UE editor leg) as
needs_decision. Pure python with an injected executor; the last test runs the api door in the real binary."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from mixar.modules.lampway_tools.pipeline import character_pipeline as CP  # noqa: E402

PARTS = [{"name": "body", "budget": 20000, "rigid_bone": None}, {"name": "helmet", "budget": 8000, "rigid_bone": "head"},
         {"name": "sword", "budget": 3000, "rigid_bone": "hand_r"}]
TOOLS = ["view_verify", "mesh_prep", "segment_mesh", "retopo", "uv_unwrap", "bake_maps", "texture_gen", "repair_texture", "auto_rig", "weight_audit",
         "weight_cleanup", "skeleton_export_check", "export_piece", "animation_retarget", "anim_check", "part_budget_plan", "secondary_chain_rig"]


def _plan(tmp_path, **kw):
    return CP.plan(str(tmp_path), "hero", PARTS, tools=TOOLS, **kw)


def test_plan_lists_thirteen_stages_with_spend_flags(tmp_path):
    out = _plan(tmp_path)
    assert [s["n"] for s in out["stages"]] == list(range(1, 14))
    spend = {s["n"]: s for s in out["stages"] if s["spend"]}
    assert set(spend) == {2, 8} and spend[2]["studio_action"] == "tripo.mesh" and spend[2]["credits_planned"] == 300          # 100 per part, three parts
    assert all(s["state"] == "needs_approval" for s in spend.values()) and out["total_credits_planned"] == sum(s["credits_planned"] for s in spend.values())
    assemble = next(s for s in out["stages"] if s["n"] == 4)
    assert assemble["state"] == "no_tool" and set(assemble["missing_tools"]) == {"mirror_pair", "mesh_join_boolean"}           # orphans: not built yet
    assert next(s for s in out["stages"] if s["n"] == 5)["part_budgets"] == {"body": 20000, "helmet": 8000, "sword": 3000}


def test_rig_before_assembly_is_refused_with_fit_before_rigging(tmp_path):
    for n in (1, 2, 3):
        CP.record(str(tmp_path), "hero", n, "pass", evidence="ok", tools=TOOLS)
    with pytest.raises(CP.PipelineError, match="fit before rigging"):
        CP.record(str(tmp_path), "hero", 9, "pass", evidence="rig", tools=TOOLS)


def test_a_stage_after_an_unverified_one_is_refused(tmp_path):
    CP.record(str(tmp_path), "hero", 1, "pass", evidence="refs", tools=TOOLS)
    with pytest.raises(CP.PipelineError, match="stage 2 .* has not passed"):
        CP.record(str(tmp_path), "hero", 3, "pass", evidence="prep", tools=TOOLS)


def test_failed_gate_stops_the_run(tmp_path):
    root = str(tmp_path)
    for n in range(1, 6):
        CP.record(root, "hero", n, "pass", evidence=f"stage {n}", tools=TOOLS)
    calls = []

    def exe(tool, args):
        calls.append(tool)
        return {"ok": True, "pass": tool != "uv_unwrap"} if tool == "uv_unwrap" else {"ok": True}

    out = CP.run(root, "hero", PARTS, from_stage=6, to_stage=10, stage_calls={"6": [{"tool": "uv_unwrap", "args": {"object": "body"}}],
                                                                              "7": [{"tool": "bake_maps", "args": {}}]}, executor=exe, tools=TOOLS)
    assert calls == ["uv_unwrap"] and out["stopped_at"] == 6 and out["state"] == "gate_failed"
    rec = CP.run_record(root, "hero")
    assert rec["gates"][-1] == dict(rec["gates"][-1], stage=6, gate="fail")
    falsified = CP.run(root, "hero", PARTS, from_stage=6, to_stage=7, stage_calls={"6": [{"tool": "uv_unwrap", "args": {}}], "7": [{"tool": "bake_maps", "args": {}}]},
                       executor=lambda t, a: {"ok": True, "pass": True}, tools=TOOLS)
    assert falsified["state"] == "done" and [g["stage"] for g in CP.run_record(root, "hero")["gates"]][-2:] == [6, 7]   # the falsifier: make it pass, the run goes on


def test_a_run_stops_at_a_spend_stage_and_never_calls_it(tmp_path):
    root = str(tmp_path)
    CP.record(root, "hero", 1, "pass", evidence="refs", tools=TOOLS)
    calls = []
    out = CP.run(root, "hero", PARTS, from_stage=2, to_stage=3, stage_calls={"2": [{"tool": "mesh_prep", "args": {}}]},
                 executor=lambda t, a: calls.append(t) or {"ok": True}, tools=TOOLS)
    assert calls == [] and out["stopped_at"] == 2 and out["state"] == "needs_approval" and out["studio_action"] == "tripo.mesh"


def test_a_stage_whose_tool_is_not_built_is_blocked_not_skipped(tmp_path):
    root = str(tmp_path)
    for n in (1, 2, 3):
        CP.record(root, "hero", n, "pass", evidence="x", tools=TOOLS)
    out = CP.run(root, "hero", PARTS, from_stage=4, to_stage=5, stage_calls={}, executor=lambda t, a: {"ok": True}, tools=TOOLS)
    assert out["stopped_at"] == 4 and out["state"] == "no_tool" and "mirror_pair" in out["reason"]


def test_a_call_naming_a_tool_outside_its_stage_is_refused(tmp_path):
    root = str(tmp_path)
    CP.record(root, "hero", 1, "pass", evidence="x", tools=TOOLS)
    CP.record(root, "hero", 2, "pass", evidence="captain's click", tools=TOOLS)
    with pytest.raises(CP.PipelineError, match="stage 3 runs mesh_prep, segment_mesh"):
        CP.run(root, "hero", PARTS, from_stage=3, to_stage=3, stage_calls={"3": [{"tool": "auto_rig", "args": {}}]}, executor=lambda t, a: {"ok": True}, tools=TOOLS)


def test_the_metahuman_conform_is_a_ue_leg_stubbed_needs_decision(tmp_path):
    out = _plan(tmp_path, target="metahuman")
    assert out["ue_leg"]["state"] == "needs_decision" and "parity" in out["ue_leg"]["reason"]
    assert _plan(tmp_path, target="unreal_mannequin")["ue_leg"] is None
    with pytest.raises(CP.PipelineError, match="unreal_mannequin, metahuman, mixamo, vrm"):
        _plan(tmp_path, target="daz")


def test_the_api_tool_plans_in_the_real_binary_with_the_door_s_tool_list(tmp_path):
    from wave6_support import go, one
    d = one(go(tmp_path, '''
res = call("character_pipeline", character_id="hero", parts=%s, mode="plan")
print("RESULT", json.dumps({"res": res, "door": list(api.TOOL_FUNCS)}))
''' % repr(PARTS)))
    res, door = d["res"], set(d["door"])
    assert res["ok"] and len(res["stages"]) == 13
    for s in res["stages"]:
        assert s["missing_tools"] == [t for t in s["tools"] if t not in door], s          # availability is the live door, not a hand list
    assert next(s for s in res["stages"] if s["n"] == 4)["missing_tools"] == []      # integration: lp/orphans brought mirror_pair and mesh_join_boolean (wave6 alone lacked them)
    assert {"mirror_pair", "mesh_join_boolean"} <= door
