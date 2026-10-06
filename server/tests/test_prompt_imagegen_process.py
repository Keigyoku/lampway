"""The image-generation process templates (STATUS O35; authored inputs from the astra-1 shelf's ImageGen workflow): one physical piece per plate in a
WEARER-axis view, left and right as separate pieces never mirrored copies, the six-view turnaround at one physical scale, an isolated held object, and
one view of a game character wearing the equipment with the truthful synthetic-character context stated. Each is data: it loads, validates, renders
for its default model, and pins the words that carry the process."""

import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import render as R

LIB = L.Library(user_dir=None, project_dir=None)
NEW = ("plate-individual-part", "turnaround-six-view", "isolate-held-object", "equip-character-view")


@pytest.mark.parametrize("tid", NEW)
def test_each_process_template_loads_and_renders_for_its_default_model(tid):
    t = LIB.get(tid)
    out = R.render(LIB, tid)
    assert t["media"] == "image" and t["provenance"]["source"] and out["prompt"] and len(out["negatives"]) <= 5, out
    assert out["inputs_required"] and out["inputs_required"][0]["required"], "every process starts from a design authority image"


def test_a_plate_view_is_defined_on_the_wearers_axes_and_one_piece_one_side():
    views = LIB.get("plate-individual-part")["variables"]["view"]["enum"]
    assert len(views) == 6
    front = R.render(LIB, "plate-individual-part", {"piece": "bracer", "side": "left", "view": views[0]})["prompt"]
    assert "wearer's right appears image-left" in front and "left bracer" in front and "#FF00FF" in front, front
    right = R.render(LIB, "plate-individual-part", {"view": next(v for v in views if v.startswith("RIGHT"))})["prompt"]
    assert "from the wearer's own right" in right and "forward points image-right" in right, right
    assert "not a mirrored copy" in front.lower() or "never a mirrored" in front.lower(), front
    with pytest.raises(R.RenderError, match="view"):
        R.render(LIB, "plate-individual-part", {"view": "three-quarter hero"})


def test_the_plate_scale_rule_is_a_choice_the_prompt_states():
    common = R.render(LIB, "plate-individual-part", {"scale": next(s for s in LIB.get("plate-individual-part")["variables"]["scale"]["enum"] if "anchor" in s)})["prompt"]
    assert "anchor" in common and "empty space" in common, common


def test_the_turnaround_is_six_cells_in_a_fixed_order_at_one_scale():
    p = R.render(LIB, "turnaround-six-view")["prompt"]
    for words in ("3 columns by 2 rows", "Top row FRONT, RIGHT, BACK", "Bottom row LEFT, TOP, BOTTOM", "IDENTICAL physical scale", "#FF00FF"):
        assert words in p, (words, p)


def test_the_equipped_character_template_states_the_synthetic_provenance_and_keeps_the_body():
    t = LIB.get("equip-character-view")
    assert t["variables"]["references_are"]["enum"] == [t["variables"]["references_are"]["default"]], "one truthful statement, not a free-text claim"
    p = R.render(LIB, "equip-character-view", {"items": "helmet, cuirass, shield on the LEFT forearm"})["prompt"]
    assert "not photographs of real people" in p and "helmet, cuirass, shield on the LEFT forearm" in p and "same body side" in p, p
    assert "never for photographs of real people" in t["inputs"]["reference_image"]["description"]


def test_isolating_a_held_object_removes_the_hand_and_completes_conservatively():
    p = R.render(LIB, "isolate-held-object", {"item": "spear"})["prompt"]
    assert "ONE spear" in p and "hand" in p and "conservatively" in p, p
