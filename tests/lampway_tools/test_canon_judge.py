# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The typed judge slot of the normalizer (the captain, 2026-10-06: "System One models aren't stochastic judgement so much as they
are typed judgement, and fast inference of it").

A judge PROPOSES one value of a schema enum for a judgment field (facing, side, texture role, bone mapping, piece kind); anything
outside the enum is a schema error, never accepted. A deterministic cross-check, where one exists, decides: disagreement refuses and
both are recorded. Without a cross-check the value is accepted only above the named confidence threshold. Computable facts (units,
axes, transforms, welds, colour space from role, bone direction) are never a judge's. The slot is OFF by default; the golden harness
measures a judge's accuracy, repeatability and latency against plain refusal."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import canon_judge as J  # noqa: E402


class Fake:
    model_id, model_version = "fake-judge", "1"

    def __init__(self, answers, confidence=0.9):
        self.answers, self.confidence = answers, confidence

    def propose(self, field, inputs, allowed):
        return self.answers[inputs["case"]], self.confidence


def test_the_fields_are_the_schemas_enums_and_computable_facts_are_not_fields():
    assert J.allowed("facing") == ("+X", "-X", "+Y", "-Y")
    assert J.allowed("side") == ("L", "R", "centre")
    assert "normal" in J.allowed("texture_role") and "mesh" in J.allowed("piece_kind")
    assert J.allowed("bone_map", reference=("pelvis", "spine_01")) == ("pelvis", "spine_01", "none")
    for fact in ("units", "axes", "transform", "weld", "colour_space", "bone_direction", "scale"):
        with pytest.raises(J.NotAJudgment):
            J.allowed(fact)


def test_an_answer_outside_the_enum_is_a_schema_error_never_accepted():
    with pytest.raises(J.SchemaError):
        J.ask(Fake({"a": "front"}), "facing", {"case": "a"})


def test_the_cross_check_decides_and_a_disagreement_refuses_with_both_recorded():
    ok = J.decide(J.ask(Fake({"a": "+X"}), "facing", {"case": "a"}), cross_check="+X")
    assert ok["value"] == "+X" and ok["accepted"] and ok["cross_check"] == "+X"
    no = J.decide(J.ask(Fake({"a": "+X"}), "facing", {"case": "a"}), cross_check="-Y")
    assert not no["accepted"] and no["proposal"] == "+X" and no["cross_check"] == "-Y" and "disagree" in no["why"]


def test_without_a_cross_check_the_threshold_decides_and_an_unset_threshold_refuses():
    j = J.ask(Fake({"a": "R"}, confidence=0.95), "side", {"case": "a"})
    assert J.decide(j, threshold=0.9)["accepted"] and not J.decide(j, threshold=0.99)["accepted"]
    unset = J.decide(j)
    assert not unset["accepted"] and "threshold" in unset["why"]


def test_the_receipt_pins_the_model_and_the_slot_is_off_by_default():
    j = J.ask(Fake({"a": "-Y"}), "facing", {"case": "a"})
    assert j["model_id"] == "fake-judge" and j["model_version"] == "1" and j["latency_ms"] >= 0
    assert not any(J.SETTINGS["enabled"]["value"].values()) and J.active() is None


def test_the_golden_harness_measures_accuracy_repeatability_and_latency_against_refusal():
    cases = [{"case": "a", "want": "+X"}, {"case": "b", "want": "-Y"}, {"case": "c", "want": "+Y"}]
    r = J.golden(Fake({"a": "+X", "b": "-Y", "c": "-X"}), "facing", cases, repeats=3)
    assert r["accuracy"] == pytest.approx(2 / 3) and r["refusal_accuracy"] == 0.0 and r["repeatable"] is True
    assert r["beats_refusal"] is False and r["wrong"] == 1 and r["latency_ms"]["max"] >= 0      # refusal is never wrong: one wrong answer loses


def test_the_judge_is_off_on_a_fresh_profile_and_stays_off_after_its_goldens_pass(monkeypatch):
    """The captain's ruling 2 (2026-10-07): the typed judge is OFF by default; the USER turns it on per field after seeing its
    measured accuracy; it never turns on automatically - not even when its goldens beat refusal."""
    monkeypatch.setattr(J, "SETTINGS", J.fresh_settings())
    assert all(v is False for v in J.SETTINGS["enabled"]["value"].values()) and set(J.SETTINGS["enabled"]["value"]) == set(J.FIELDS)
    assert all(J.active(f) is None for f in J.FIELDS)
    report = J.golden(Fake({"a": "+X", "b": "-Y"}), "facing", [{"case": "a", "want": "+X"}, {"case": "b", "want": "-Y"}], repeats=2)
    assert report["beats_refusal"] is True
    assert J.SETTINGS["enabled"]["value"]["facing"] is False and J.active("facing") is None
    with pytest.raises(PermissionError):
        J.enable("facing", report, by="agent")                    # only the user turns a field on
    with pytest.raises(ValueError):
        J.enable("side", report, by="user")                       # a field is turned on with ITS OWN measured report
    J.enable("facing", report, by="user")
    assert J.SETTINGS["enabled"]["value"] == {f: f == "facing" for f in J.FIELDS}
