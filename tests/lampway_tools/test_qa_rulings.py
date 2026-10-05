# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decision log and rulings files for mesh QA (pure Python: no Blender).

The decision log is shaped like the project's fit_state tool's: one JSON row per decision, the descriptor beside its
sha256 over canonical JSON (segments dropped), the question and its options, the answer, the decider. The rulings
files are what the rebuild reads: <piece>_deletions.json, <piece>_relabels_orig.json, <piece>_texel_overrides_orig.json,
<piece>_candidates_merged.json (source face ids, stable across rebuilds)."""

import os
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.meshqa import decisions as D  # noqa: E402
from mixar.modules.lampway_tools.meshqa import rulings as R  # noqa: E402

SHELF = Path(os.environ.get("LAMPWAY_SHELF") or "/nonexistent") / "meshqa"   # the owner's recorded runs; unset = skipped


def loop(cid, **kw):
    return {"id": cid, "kind": "open_loop", "perimeter_m": 0.4, "segments_m": [[[0, 0, 0], [1, 0, 0]]], **kw}


def shell(cid, polys):
    return {"id": cid, "kind": "loose_shell", "tris": len(polys), "orig_polys": polys}


# ---- decisions

def test_the_descriptor_hash_is_canonical_and_ignores_the_drawing_segments():
    a = {"id": "L1", "perimeter_m": 0.4, "segments_m": [[[0, 0, 0], [1, 1, 1]]]}
    b = {"perimeter_m": 0.4, "id": "L1"}
    want = hashlib.sha256(json.dumps(b, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert D.descriptor_sha256(a) == D.descriptor_sha256(b) == want


@pytest.mark.skipif(not (SHELF / "decisions.jsonl").exists(), reason="the shelf's decision log is not on this machine")
def test_the_hash_reproduces_every_row_of_his_own_log():
    rows = D.read_rows(SHELF / "decisions.jsonl")
    checked = [r for r in rows if "descriptor_sha256" in r]
    assert len(checked) > 100
    assert all(D.descriptor_sha256(r["descriptor"]) == r["descriptor_sha256"] for r in checked)


def test_rows_append_as_sorted_key_json_lines_and_read_back(tmp_path):
    log = tmp_path / "q" / "decisions.jsonl"
    rows = [D.row("s1", "cands.json", loop("L1"), "open_loop_defect", ["hole", "keep"], "hole", how="named")]
    D.append_rows(log, rows)
    D.append_rows(log, [D.row("s1", "cands.json", loop("L2"), "open_loop_defect", ["hole", "keep"], "keep")])
    lines = log.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0]) == D.read_rows(log)[0]
    assert lines[0] == json.dumps(json.loads(lines[0]), sort_keys=True)
    r = D.read_rows(log)[0]
    assert r["decider"] == "captain" and r["how"] == "named" and "segments_m" not in r["descriptor"]
    assert r["descriptor_sha256"] == D.descriptor_sha256(loop("L1"))


def test_the_latest_answer_per_loop_wins_and_a_session_can_be_selected(tmp_path):
    rows = [D.row("a", "c", loop("L1"), "open_loop_defect", ["hole", "keep"], "hole"),
            D.row("a", "c", loop("L1"), "open_loop_defect", ["hole", "keep"], "keep", how="correction"),
            D.row("b", "c", loop("L2"), "open_loop_defect", ["hole", "keep"], "hole"),
            D.row("a", "c", shell("S1", [1]), "loose_shell_defect", ["delete", "keep"], "delete")]
    assert D.latest_answers(rows) == {"L1": "keep", "L2": "hole"}
    assert D.latest_answers(rows, session="b") == {"L2": "hole"}
    assert D.latest_answers(rows, kind="loose_shell") == {"S1": "delete"}


def test_tags_become_rows_named_loops_hole_orphans_findings_the_rest_keep_when_the_round_closes():
    cands = [loop("L1"), loop("L2"), loop("L3"), shell("S1", [10])]
    tagged = {"delete": [], "mislabel": [],
              "hole": [{"stroke": 0, "layer": "Hole", "loops": {"L1": "circled"}, "orphan": False, "centre_m": [0, 0, 0], "n_points": 30},
                       {"stroke": 1, "layer": "Hole", "loops": {}, "orphan": True, "centre_m": [1, 2, 3], "n_points": 12}]}
    rows = D.rows_from_tags(tagged, cands, session="s", source="c.json")
    by = {(r["descriptor"].get("id") or r["descriptor"]["kind"]): r for r in rows}
    assert set(by) == {"L1", "captain_finding"}
    assert by["L1"]["answer"] == "hole" and "circling" in by["L1"]["how"] and by["L1"]["strokes"] == [0]
    f = by["captain_finding"]
    assert f["answer"] == "hole" and f["descriptor"]["centre_m"] == [1, 2, 3] and f["strokes"] == [1]
    closed = D.rows_from_tags(tagged, cands, session="s", source="c.json", close_round=True)
    answers = {r["descriptor"].get("id"): r["answer"] for r in closed if r["descriptor"].get("id")}
    assert answers == {"L1": "hole", "L2": "keep", "L3": "keep", "S1": "keep"}


def test_a_deleted_shell_is_a_row_and_a_row_per_candidate_never_twice():
    cands = [shell("S1", [10, 11]), shell("S2", [20])]
    tagged = {"delete": [{"stroke": 0, "layer": "Delete", "faces": [3, 4], "orig_faces": [10, 99]}], "mislabel": [], "hole": []}
    rows = D.rows_from_tags(tagged, cands, session="s", source="c")
    assert [(r["descriptor"]["id"], r["answer"], r["question"]) for r in rows] == [("S1", "delete", "loose_shell_defect")]


# ---- rulings

def test_add_deletions_unions_sorts_records_the_decision_and_is_idempotent(tmp_path):
    r = R.Rulings(tmp_path, "chest_x")
    r.add_deletions([5, 3, 5], what="flap", note="get rid of it", date="2026-10-04")
    r.add_deletions([3, 9], what="more", date="2026-10-04")
    r.add_deletions([3, 9], what="more", date="2026-10-04")             # a repeat adds nothing, records nothing new
    d = json.loads((tmp_path / "chest_x_deletions.json").read_text())
    assert d["polys"] == [3, 5, 9]
    assert [x["what"] for x in d["decisions"]] == ["flap", "more"]
    assert d["decisions"][0] == {"what": "flap", "decider": "captain", "date": "2026-10-04", "note": "get rid of it"}


def test_add_deletions_keeps_the_refill_block_he_wrote(tmp_path):
    p = tmp_path / "chest_x_deletions.json"
    p.write_text(json.dumps({"polys": [1], "decisions": [], "refill": [{"polys": [7, 8], "owner": "plate"}]}))
    R.Rulings(tmp_path, "chest_x").add_deletions([2], what="w")
    assert json.loads(p.read_text())["refill"] == [{"polys": [7, 8], "owner": "plate"}]


def test_relabels_and_texel_overrides_have_the_rebuilds_shapes(tmp_path):
    r = R.Rulings(tmp_path, "chest_x", parts=["plate", "cape"])
    r.add_relabel([9, 4, 4], to="plate", why="red X: cape label on the plate")
    r.add_force_class([30, 31], cls="red", why="gold specks on the cowl")
    assert json.loads((tmp_path / "chest_x_relabels_orig.json").read_text()) == {
        "relabels": [{"faces_orig": [4, 9], "to": "plate", "why": "red X: cape label on the plate"}]}
    assert json.loads((tmp_path / "chest_x_texel_overrides_orig.json").read_text()) == {
        "force_class": [{"faces_orig": [30, 31], "class": "red", "why": "gold specks on the cowl"}]}


def test_a_relabel_to_an_unknown_part_is_refused(tmp_path):
    r = R.Rulings(tmp_path, "chest_x", parts=["plate"])
    with pytest.raises(ValueError, match="unknown part"):
        r.add_relabel([1], to="nope", why="x")


def test_merge_candidates_prefixes_every_extra_id_and_keeps_the_base_meta():
    base = {"mesh": "m", "turn": -90.0, "candidates": [loop("L000"), loop("L001")]}
    extra = {"mesh": "m2", "candidates": [loop("L001"), loop("L110")]}
    out = R.merge_candidates(base, extra, prefix="B-")
    assert [c["id"] for c in out["candidates"]] == ["L000", "L001", "B-L001", "B-L110"]
    with pytest.raises(ValueError, match="already merged"):
        R.merge_candidates(out, extra, prefix="B-")
    assert out["mesh"] == "m" and out["turn"] == -90.0


def test_apply_tags_deletes_the_tagged_faces_and_the_whole_small_shell_they_sit_on(tmp_path):
    r = R.Rulings(tmp_path, "chest_x")
    orig_poly = [0, 1, 2, 3, -1, 5]                                    # live face -> source face; -1 = a patch face
    tagged = {"delete": [{"stroke": 0, "layer": "Delete", "faces": [1, 4, 5]}], "mislabel": [], "hole": []}
    cands = [shell("S1", [1, 2])]
    rep = r.apply_tags(tagged, cands, orig_poly, what="red annotation", date="2026-10-04")
    d = json.loads((tmp_path / "chest_x_deletions.json").read_text())
    assert d["polys"] == [1, 2, 5]                                      # face 1's shell (1, 2) + the face 5; patch face 4 skipped
    assert rep["deleted"] == 3 and rep["patch_faces_skipped"] == 1 and rep["shells"] == ["S1"]


def test_apply_tags_without_shell_expansion_deletes_only_the_faces(tmp_path):
    r = R.Rulings(tmp_path, "chest_x")
    tagged = {"delete": [{"stroke": 0, "layer": "Delete", "faces": [1]}], "mislabel": [], "hole": []}
    rep = r.apply_tags(tagged, [shell("S1", [1, 2])], [0, 1, 2], expand_shell=False)
    assert json.loads((tmp_path / "chest_x_deletions.json").read_text())["polys"] == [1]
    assert rep["shells"] == []


def test_apply_tags_returns_the_mislabel_strokes_that_still_need_a_target_part(tmp_path):
    r = R.Rulings(tmp_path, "chest_x", parts=["plate", "cape"])
    tagged = {"delete": [], "hole": [], "mislabel": [{"stroke": 0, "layer": "Mislabel", "faces": [0, 2], "islands": [7]}]}
    rep = r.apply_tags(tagged, [], [10, 11, 12], mislabel_to={})
    assert rep["relabels_needing_a_target"] == [{"stroke": 0, "faces_orig": [10, 12], "islands": [7]}]
    rep = r.apply_tags(tagged, [], [10, 11, 12], mislabel_to={0: "plate"}, why="green")
    assert json.loads((tmp_path / "chest_x_relabels_orig.json").read_text())["relabels"][0]["faces_orig"] == [10, 12]
    assert rep["relabelled"] == 2
