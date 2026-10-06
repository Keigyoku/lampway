"""The captain's moodboard prompts as built-in templates (O35 addition; O24's chain uses them). "They can be spruced up though nothing can be lost": every
clause of every original (tests/fixtures/moodboard, byte copies of specs/prompts/moodboard) must be found in its template, verbatim or through an alias
recorded in the parity map (prompts/moodboard_parity.json: original clause -> the reworded text and the template field it lives in). The check is
prompts/parity.py; this file proves it can fail."""

import copy
import json
from pathlib import Path

import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import parity as PA
from lampway_server.prompts import render as R

FIX = Path(__file__).parent / "fixtures" / "moodboard"
LIB = L.Library(user_dir=None, project_dir=None)
MAP = PA.load_map()
PROMPTS = [f"Prompt{i}.txt" for i in range(1, 9)]


def test_every_original_has_a_template_and_the_map_covers_all_eight():
    assert sorted(MAP) == sorted(PROMPTS)
    assert sorted(p.name for p in FIX.glob("Prompt*.txt")) == sorted(PROMPTS)


@pytest.mark.parametrize("name", PROMPTS)
def test_nothing_of_the_original_is_lost(name):
    entry = MAP[name]
    templates = [LIB.get(t) for t in entry["templates"]]
    rows = PA.check((FIX / name).read_text(encoding="utf-8"), templates, entry.get("aliases") or {})
    lost = [r["clause"] for r in rows if not r["location"]]
    assert not lost, f"{name}: clauses with no place in {entry['templates']}: {lost}"
    assert len(rows) >= 8, "the splitter found the clauses"
    unused = set(entry.get("aliases") or {}) - {r["clause"] for r in rows if r["via"] == "alias"}
    assert not unused, f"{name}: aliases for clauses the original does not have: {unused}"


def test_a_deleted_clause_is_caught():
    t = copy.deepcopy(LIB.get(MAP["Prompt1.txt"]["templates"][0]))
    planted = "no props"
    for part, text in t["body"].items():
        t["body"][part] = text.replace("no props; ", "").replace("; no props", "")
    assert all(planted not in v for v in t["body"].values()), "the plant removed the clause"
    rows = PA.check((FIX / "Prompt1.txt").read_text(encoding="utf-8"), [t], MAP["Prompt1.txt"].get("aliases") or {})
    assert planted in [r["clause"] for r in rows if not r["location"]]


def test_an_alias_whose_text_is_not_where_it_says_is_caught():
    name = next(n for n in PROMPTS if MAP[n].get("aliases"))
    entry = copy.deepcopy(MAP[name])
    clause, alias = next(iter(entry["aliases"].items()))
    part = (alias.get("parts") or [alias])[-1]                                       # one part of a split clause failing is enough
    part["as"] = part["as"] + " (this sentence is nowhere)"
    rows = PA.check((FIX / name).read_text(encoding="utf-8"), [LIB.get(t) for t in entry["templates"]], entry["aliases"])
    assert clause in [r["clause"] for r in rows if not r["location"]]


@pytest.mark.parametrize("name", PROMPTS)
def test_each_template_renders_carries_no_model_pin_and_names_image_a_and_b(name):
    for tid in MAP[name]["templates"]:
        t = LIB.get(tid)
        assert "model" not in (t.get("defaults") or {}), f"{tid}: no model pin (CH5: the purpose's choice wins)"
        out = R.render(LIB, tid)
        assert out["prompt"] and out["inputs_required"][0]["required"], tid
        roles = [i["role"] for i in out["inputs_required"]]
        if "Image A" in (FIX / name).read_text():
            assert roles[:2] == ["character_body", "design_plate"] and "Image A" in out["prompt"] and "Image B" in out["prompt"], (tid, roles)


def test_asset_name_and_the_wearer_axis_view_are_typed_variables():
    multi = LIB.get(MAP["Prompt5.txt"]["templates"][0])
    assert multi["variables"]["asset_name"]["type"] == "string"
    one = LIB.get(MAP["Prompt6.txt"]["templates"][0])
    views = one["variables"]["view"]["enum"]
    assert one["variables"]["view"]["type"] == "enum" and [v.split()[0] for v in views] == ["FRONT", "LEFT", "BACK", "RIGHT", "TOP", "BOTTOM"]
    p = R.render(LIB, one["id"], {"asset_name": "left greave", "view": views[3]})["prompt"]
    assert "left greave" in p and "from the wearer's own right side" in p and "[ASSET NAME]" not in p, p
