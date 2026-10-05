# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""armor_piece_pipeline (wiki/armor_piece_pipeline.md section 10): the sequencer over the existing tools, keeping the user's order laws. It plans and records; it never confirms a spend."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import armor_piece as AP  # noqa: E402


def test_plan_boots1_from_step_8_lists_unwrap_texture_pbr_with_20_30_5_credits(tmp_path):
    out = AP.plan(str(tmp_path), "Boots1", from_step=8, to_step=15, paired=True)
    spend = [(s["tool"], s["credits_planned"]) for s in out["steps"] if s["credits_planned"]]
    assert spend == [("tripo.uv.unwrap", 20), ("tripo.texture", 30), ("tripo.pbr", 5)]
    assert out["total_credits_planned"] == 55 and out["steps"][0]["n"] == 8 and out["steps"][-1]["n"] == 15
    assert all(s["state"] in ("needs_approval", "waiting", "ready") for s in out["steps"])
    assert [s["state"] for s in out["steps"] if s["credits_planned"]] == ["needs_approval"] * 3


def test_the_whole_piece_costs_about_155_credits(tmp_path):
    out = AP.plan(str(tmp_path), "Helmet1")
    assert out["total_credits_planned"] == 155 and out["steps"][0]["n"] == 1


def test_a_paired_piece_sends_front_and_back_views_only_in_the_mesh_step(tmp_path):
    paired = AP.plan(str(tmp_path), "Boots1", paired=True)["steps"]
    plain = AP.plan(str(tmp_path), "Helmet1")["steps"]
    mesh = lambda steps: next(s for s in steps if s["tool"] == "tripo.mesh")
    assert mesh(paired)["args"]["views"] == ["Front", "Back"] and mesh(plain)["args"]["views"] == ["Front", "Left", "Right", "Back"]


def test_unknown_piece_and_a_bad_range_are_refused(tmp_path):
    with pytest.raises(AP.PipelineError, match="unknown piece 'Cuisse1'; the pieces are"):
        AP.plan(str(tmp_path), "Cuisse1")
    with pytest.raises(AP.PipelineError, match="to_step 3 is below from_step 5"):
        AP.plan(str(tmp_path), "Helmet1", from_step=5, to_step=3)


def test_starting_after_step_1_needs_a_run_record_naming_the_input(tmp_path):
    with pytest.raises(AP.PipelineError, match="no run record for Boots1: start at step 1, or record the earlier steps first"):
        AP.start(str(tmp_path), "Boots1", from_step=8)
    AP.record(str(tmp_path), "Boots1", 7, artefacts=[], mesh_hash="h0")
    assert AP.start(str(tmp_path), "Boots1", from_step=8)["steps"][0]["n"] == 8


def test_texture_before_unwrap_is_refused_naming_tripo_uv_unwrap(tmp_path):
    with pytest.raises(AP.PipelineError, match="texturing-last guard: no Smart UV step.*run step 8 .tripo.uv.unwrap. first"):
        AP.check_step(str(tmp_path), "Boots1", 13)
    AP.record(str(tmp_path), "Boots1", 8, artefacts=[], mesh_hash="h1")           # the unwrap is recorded: the same call passes
    assert AP.check_step(str(tmp_path), "Boots1", 13)["ok"] is True


def test_a_studio_step_on_an_original_names_the_clone_action(tmp_path):
    with pytest.raises(AP.PipelineError, match="saved COPY.*tripo.uv.clone"):
        AP.check_step(str(tmp_path), "Boots1", 8, studio_is_original=True)


def test_a_geometry_edit_after_texture_marks_the_texture_stale(tmp_path):
    AP.record(str(tmp_path), "Boots1", 8, artefacts=[], mesh_hash="h1")
    AP.record(str(tmp_path), "Boots1", 13, artefacts=[], mesh_hash="h1")
    assert AP.run_record(str(tmp_path), "Boots1")["texture"] == "fresh"
    AP.record(str(tmp_path), "Boots1", 11, artefacts=[], mesh_hash="h2")           # an opening gasket changed the mesh
    rec = AP.run_record(str(tmp_path), "Boots1")
    assert rec["texture"] == "stale" and "re-run step 13" in AP.start(str(tmp_path), "Boots1", from_step=13)["notes"][0]


def test_without_the_hash_write_staleness_would_be_missed(tmp_path):                   # the falsifier of the previous test
    AP.record(str(tmp_path), "Boots1", 13, artefacts=[], mesh_hash="h1")
    AP.record(str(tmp_path), "Boots1", 11, artefacts=[], mesh_hash="h1")           # same hash: not a geometry change
    assert AP.run_record(str(tmp_path), "Boots1")["texture"] == "fresh"


def test_rig_before_place_and_pose_is_refused_naming_both_tools(tmp_path):
    with pytest.raises(AP.PipelineError, match="fit_place.*pose_clearance"):
        AP.check_tool(str(tmp_path), "Boots1", "rig_armor")
    AP.record(str(tmp_path), "Boots1", 6, artefacts=[], mesh_hash="h")
    assert AP.check_tool(str(tmp_path), "Boots1", "rig_armor")["ok"] is True


def test_no_step_confirms_a_spend_and_the_run_never_arms_the_studio(tmp_path, monkeypatch):
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    out = AP.start(str(tmp_path), "Helmet1")
    assert all(s["state"] != "done" for s in out["steps"] if s["credits_planned"])
    import os
    assert "LAMPWAY_STUDIO_ARMED" not in os.environ
    assert "ARMED" not in Path(AP.__file__).read_text().replace("LAMPWAY_STUDIO_ARMED", "")


def test_the_run_record_is_append_only_and_lists_each_artefact_with_its_hash(tmp_path):
    a = tmp_path / "x.fbx"; a.write_bytes(b"abc")
    AP.record(str(tmp_path), "Boots1", 2, artefacts=[str(a)], mesh_hash="h")
    AP.record(str(tmp_path), "Boots1", 2, artefacts=[str(a)], mesh_hash="h")
    rec = AP.run_record(str(tmp_path), "Boots1")
    assert len(rec["events"]) == 2 and rec["events"][0]["artefacts"][0]["sha256"].startswith("ba7816bf")
    path = tmp_path / "Boots1/pipeline/run.json"
    assert json.loads(path.read_text())["events"][0]["step"] == 2
