"""material_experiment (specs/wiki/material_experiment.md): the credit-efficient material matrix (T1 baseline, T2 identical repeat, T3 seed only, T4 alignment only,
M1 shared material, L1 one local patch) as planned rows with prices read from the Studio action catalogue, runs that are only ever needs_approval cards (the
user confirms each spend), recorded results on the experiment ledger, a texel RMS comparison and the wiki's stop rule."""

import json

import numpy as np
import pytest
from PIL import Image

from lampway_server import material_experiment as ME
from lampway_server.ledger import Ledger

ACCEPTED = {"accepted": True, "object": "Chest1_uvcopy", "mesh_hash": "ab" * 32}


def img(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((16, 16, 3), value, dtype=np.uint8)).save(path)
    return str(path.name)


def test_plan_lists_prices_and_sums_them(tmp_path):
    out = ME.plan(str(tmp_path), "Chest1", "tripo", ["T1", "T2"])
    assert [(r["row"], r["action"], r["expected_credits"], r["read_back_price"]) for r in out["plan"]] == [("T1", "tripo.texture", 30, None), ("T2", "tripo.texture", 30, None)]
    assert out["total_expected_credits"] == 60 and out["runnable"] is True
    assert "T2" in out["note"] or "repeat" in out["note"]                              # the plan says T2 deliberately repeats a spend


def test_default_rows_skip_what_the_engine_cannot_do_and_say_why(tmp_path):
    out = ME.plan(str(tmp_path), "Chest1", "tripo")
    assert [r["row"] for r in out["plan"]] == ["T1", "T2"] and out["skipped"] == [{"row": "T3", "reason": "tripo exposes no seed control: a seed-only row cannot be run"}]
    with pytest.raises(ME.ExperimentError, match="T4 changes the texture alignment only: tripo has no alignment control"):
        ME.plan(str(tmp_path), "Chest1", "tripo", ["T1", "T4"])


def test_no_driver_engine_returns_plan_only(tmp_path):
    out = ME.plan(str(tmp_path), "Chest1", "3dai_prism", ["T1", "T2", "T3", "T4"])
    assert out["runnable"] is False and [r["expected_credits"] for r in out["plan"]] == [20, 20, 20, 20] and out["total_expected_credits"] == 80
    assert all("UNVERIFIED" in r["price_source"] for r in out["plan"])
    with pytest.raises(ME.ExperimentError, match="no driver for 3dai_prism: only tripo"):
        ME.run(str(tmp_path), "Chest1", "3dai_prism", "T1", ACCEPTED)


def test_t2_refused_when_no_t1_recorded(tmp_path):
    with pytest.raises(ME.ExperimentError, match="T2 repeats T1 exactly: record T1 first"):
        ME.run(str(tmp_path), "Chest1", "tripo", "T2", ACCEPTED)


def test_a_run_needs_a_passing_acceptance_and_is_only_ever_a_needs_approval_card(tmp_path):
    with pytest.raises(ME.ExperimentError, match="asset_acceptance"):
        ME.run(str(tmp_path), "Chest1", "tripo", "T1", {"accepted": False})
    card = ME.run(str(tmp_path), "Chest1", "tripo", "T1", ACCEPTED)
    assert card["state"] == "needs_approval" and card["studio_action"] == "tripo.texture" and card["args"] == {"res": "8K", "remove_lighting": True}
    assert card["expected_credits"] == 30 and "studio_plan" in card["how"]


def test_stop_rule_halts_after_identity_failure(tmp_path):
    root = str(tmp_path)
    t1 = img(tmp_path / "tex" / "t1.png", 100)
    ME.record(root, "Chest1", "tripo", "T1", "tex/" + t1, identity_pass=False, fit_pass=True, read_back_price=30)
    with pytest.raises(ME.ExperimentError, match="stop: T1 failed identity"):
        ME.run(root, "Chest1", "tripo", "T2", ACCEPTED)
    ok_root = tmp_path / "ok"
    img(ok_root / "tex" / "t1.png", 100)
    ME.record(str(ok_root), "Chest1", "tripo", "T1", "tex/t1.png", identity_pass=True, fit_pass=True, read_back_price=30)
    assert ME.run(str(ok_root), "Chest1", "tripo", "T2", ACCEPTED)["state"] == "needs_approval"          # the falsifier: T1 passes, the run continues


def test_records_land_on_the_experiment_ledger_and_the_comparison_is_a_texel_rms(tmp_path):
    root = str(tmp_path)
    img(tmp_path / "tex" / "t1.png", 100)
    img(tmp_path / "tex" / "t2.png", 100)
    r1 = ME.record(root, "Chest1", "tripo", "T1", "tex/t1.png", identity_pass=True, fit_pass=True, read_back_price=30)
    r2 = ME.record(root, "Chest1", "tripo", "T2", "tex/t2.png", identity_pass=True, fit_pass=True, read_back_price=30)
    cmp_ = ME.compare(root, "Chest1", "tripo")
    assert cmp_["comparison"]["t1_vs_t2_rms"] == 0.0 and cmp_["comparison"]["t1_vs_t3_rms"] is None
    assert "repeatable" in cmp_["comparison"]["verdicts"]["T2"]
    rows = Ledger(tmp_path / "ledger" / "runs.jsonl").list(piece="Chest1", stage="texture")
    assert [r["id"] for r in rows] == [r1["ledger_id"], r2["ledger_id"]]
    assert rows[0]["studio"] == "tripo" and rows[0]["seed"] == "not_exposed" and rows[0]["by"] == "agent" and rows[0]["decision"] is None
    assert rows[0]["cost"] == {"generation_credits": 30, "price_source": "the driver's read-back"} and rows[0]["settings"]["row"] == "T1"
    img(tmp_path / "tex" / "t2b.png", 140)
    ME.record(root, "Chest1", "tripo", "T2", "tex/t2b.png", identity_pass=True, fit_pass=True, read_back_price=30)
    assert ME.compare(root, "Chest1", "tripo")["comparison"]["t1_vs_t2_rms"] == pytest.approx(40 / 255, abs=1e-3)


def test_a_texture_outside_the_project_is_refused(tmp_path):
    with pytest.raises(ME.ExperimentError, match="outside the project root"):
        ME.record(str(tmp_path), "Chest1", "tripo", "T1", "../elsewhere.png", identity_pass=True, fit_pass=True, read_back_price=30)


def test_the_agent_tool_plans_and_cards_through_the_agent_loop(tmp_path, monkeypatch):
    import asyncio
    from lampway_server.agent import tools as T
    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.turns import AgentHub
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    assert "lampway_material_experiment" in T.TOOL_NAMES
    hub = AgentHub.__new__(AgentHub)
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c1", "lampway_material_experiment", {"action": "plan", "piece": "Chest1", "engine": "tripo", "rows": ["T1"]})))
    assert not err and json.loads(out)["total_expected_credits"] == 30
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c2", "lampway_material_experiment", {"action": "run", "piece": "Chest1", "engine": "tripo", "row": "T2",
                                                                                                         "acceptance": ACCEPTED})))
    assert err and "record T1 first" in out
