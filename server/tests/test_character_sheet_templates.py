"""The character-sheet template set (specs/mrmak/07-view-verify.md section 6.5): present, valid, rendered for every declared model, carrying their upstream provenance."""
import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import render as R

IDS = ["sheet-apose-front", "sheet-multiview-16x9", "part-body", "part-paired", "part-accessory", "part-hair", "part-view", "turntable-360-locked"]


@pytest.fixture(scope="module")
def lib():
    return L.Library()


def test_the_set_is_in_the_library_and_loads_without_errors(lib):
    assert lib.errors == []
    have = {t["id"] for t in lib.list()}
    assert set(IDS) <= have


def test_every_template_carries_its_upstream_provenance_and_the_mit_note(lib):
    for t in lib.list():
        if t["id"] in IDS:
            assert t["provenance"]["source"].startswith("mr-mak-workspace:.agents/skills/character-sheet-pipeline/prompts/") and t["provenance"]["source"].endswith("@1e0c7c3")
            assert "MIT" in t["provenance"]["note"]


def test_every_template_renders_for_every_model_it_declares_with_at_most_five_negatives(lib):
    for tid in IDS:
        t = next(x for x in lib.list() if x["id"] == tid)
        models = {t["defaults"]["model"]} | {m.replace("*", "x") for m in t.get("model_adapters", {})}
        for model in sorted(models):
            out = R.render(lib, tid, {}, model=model)
            assert out["prompt"].strip() and "{{" not in out["prompt"] and len(out["negatives"]) <= 5, (tid, model)


def test_the_front_sheet_keeps_the_strict_front_wording_and_the_long_negative_list_is_a_variant(lib):
    out = R.render(lib, "sheet-apose-front", {"character_description": "a bronze-armoured warrior"})
    assert "STRICT FRONT VIEW" in out["prompt"] and "bronze-armoured warrior" in out["prompt"] and "three-quarter" in out["prompt"]
    long = next(t for t in lib.list() if t["id"] == "sheet-apose-front-long")
    assert long["variant_of"] == "sheet-apose-front@1.0.0" and long["negatives"] == [] and "contrapposto" in long["body"]["constraints"]
    assert next(t for t in lib.list() if t["id"] == "sheet-apose-front")["version"] == "1.0.0"          # the short-negative wording stays the default; the long one is the A/B variant


def test_the_variables_select_the_part_and_the_view(lib):
    torso = R.render(lib, "part-body", {"part": "head", "part_extent": "the head and neck"})["prompt"]
    assert "head" in torso and "STRICT FRONT" in torso
    side = R.render(lib, "part-view", {"angle": "back", "subject_part": "head"})["prompt"]
    assert "back" in side and "head" in side
    assert "turntable" in R.render(lib, "turntable-360-locked", {})["prompt"].lower() and "does NOT move" in R.render(lib, "turntable-360-locked", {})["prompt"]
