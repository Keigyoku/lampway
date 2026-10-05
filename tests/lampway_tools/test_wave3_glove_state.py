# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_glove (the typed plate-label decision) and fit_state (a needs_decision stub): shelf/fit_glove.md and shelf/fit_state.md."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import fit_glove as FG  # noqa: E402

PLATES = ["cap_index", "cap_thumb", "bracer", "back_of_hand", "cuff_leather", "upper_arm"]
ROLES = {"cap_index": "metal", "cap_thumb": "metal", "bracer": "metal", "back_of_hand": "metal", "cuff_leather": "leather", "upper_arm": "cloth"}
LABELS = {"cap_index": "index_01_r", "cap_thumb": "thumb_01_r", "bracer": "lowerarm_r", "back_of_hand": "hand_r", "cuff_leather": "lowerarm_r", "upper_arm": "upperarm_r"}


def test_a_full_labelling_writes_the_labels_a_bind_fragment_and_one_decision_row_each(tmp_path):
    out = FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, LABELS, ROLES, by="agent")
    assert out["ok"] is True and len(out["labels"]) == 6
    assert out["bind_fragment"]["cap_index"] == {"mode": "rigid", "bones": ["index_01_r"]}
    assert out["bind_fragment"]["cuff_leather"]["mode"] == "restrict" and out["bind_fragment"]["upper_arm"]["mode"] == "restrict"
    rows = [json.loads(l) for l in (tmp_path / "Gauntlets1/fit/decisions.jsonl").read_text().splitlines()]
    assert len(rows) == 6 and {r["question"] for r in rows} == {"glove_plate_label"} and all(r["decider"] == "agent" for r in rows)
    assert json.loads((tmp_path / "Gauntlets1/fit/glove_labels.json").read_text())["labels"]["bracer"]["bone"] == "lowerarm_r"


def test_unlabelled_plates_are_named_and_never_guessed(tmp_path):
    partial = {k: v for k, v in LABELS.items() if k not in ("cap_thumb", "bracer")}
    with pytest.raises(FG.GloveError, match=r"never guess: ask.*\['bracer', 'cap_thumb'\]"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, partial, ROLES)


def test_a_finger_bone_of_the_other_hand_names_the_side(tmp_path):
    bad = dict(LABELS, cap_index="index_01_l")
    with pytest.raises(FG.GloveError, match="index_01_l is a left-hand bone but this is the right glove"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, bad, ROLES)


def test_the_upper_arm_is_cloth_and_a_cloth_plate_cannot_be_bound_rigid(tmp_path):
    with pytest.raises(FG.GloveError, match="upper arm is cloth"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, LABELS, ROLES, overrides={"upper_arm": {"mode": "rigid"}})
    with pytest.raises(FG.GloveError, match="finger caps and the bracer are metal: one bone each"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, dict(LABELS, cap_index=["index_01_r", "index_02_r"]), ROLES)


def test_an_unknown_bone_and_a_missing_role_are_refused(tmp_path):
    with pytest.raises(FG.GloveError, match="not a hand or arm bone"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, dict(LABELS, bracer="pelvis"), ROLES)
    with pytest.raises(FG.GloveError, match="no material role"):
        FG.labels(str(tmp_path), "Gauntlets1", "r", PLATES, LABELS, {k: v for k, v in ROLES.items() if k != "bracer"})


def test_pose_bind_and_report_name_the_open_decisions_and_fit_state_is_the_users_to_rule():
    out = FG.not_built("pose")
    assert out["ok"] is False and out["needs_decision"]["questions"][0].startswith("hand keypoints") and "left glove" in out["needs_decision"]["questions"][1]
    st = FG.fit_state("describe")
    assert st["ok"] is False and "Laya" in st["needs_decision"]["question"] and st["needs_decision"]["why"]
