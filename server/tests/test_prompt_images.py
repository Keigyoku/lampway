"""Image parity with video (PROMPT_LIBRARY.md section 5): the ported wording is VERBATIM (compared with the shelf files), the reference roles are ORDERED and
enforced (clay, then painted view, then design plate), size or resolution is validated per model family (GPT Image takes size within the budget; FLUX, Seedream,
Gemini and Riverflow take resolution + aspect_ratio), and the image gates are declared."""

import re
from pathlib import Path

import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import render as R

FIX = Path(__file__).parent / "fixtures" / "prompts_verbatim"
LIB = L.Library()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("template, variables, fixture", [
    ("mesh-paint-albedo-front", {}, "mesh_paint_front.txt"), ("mesh-paint-albedo-side", {}, "mesh_paint_side.txt"),
    ("plate-4k-crisper", {"view": "front"}, "plate_front.txt"), ("plate-4k-crisper", {"view": "back"}, "plate_Back.txt"),
    ("plate-4k-crisper", {"view": "left side"}, "plate_Left.txt"), ("plate-4k-crisper", {"view": "right side"}, "plate_Right.txt"),
    ("seamless-tile", {}, "seamless_tile.txt"), ("character-reference-fullbody", {}, "character_reference.txt")])
def test_the_ported_wording_is_verbatim(template, variables, fixture):
    assert norm(R.render(LIB, template, variables)["prompt"]) == norm((FIX / fixture).read_text())


def test_the_mesh_paint_references_are_ordered_and_the_order_is_enforced():
    t = LIB.get("mesh-paint-albedo-front")
    order = [r["role"] for r in R.render(LIB, "mesh-paint-albedo-front", {})["inputs_required"]]
    assert order == ["clay_render", "painted_view", "design_plate"]
    files = {"design_plate": "plate.png", "clay_render": "clay.png", "painted_view": "painted.png"}      # given in the WRONG order
    assert [item for _, item in R.order_references(t, files)] == ["clay.png", "painted.png", "plate.png"]
    with pytest.raises(R.RenderError, match="painted_view"):
        R.order_references(t, {"clay_render": "c.png", "design_plate": "p.png"})
    with pytest.raises(R.RenderError, match="selfie"):
        R.order_references(t, {**files, "selfie": "s.png"})
    cr = LIB.get("character-reference-fullbody")
    got = R.order_references(cr, {"piece_images": ["a", "b", "c", "d", "e"], "character_body": "body"})
    assert [i for _, i in got] == ["body", "a", "b", "c", "d", "e"]
    with pytest.raises(R.RenderError, match="character_body"):
        R.order_references(t.__class__(cr, inputs={"character_body": {"required": True, "order": 1, "description": "x"}}), {"character_body": ["two", "bodies"]})


def test_a_positional_list_is_checked_against_the_roles_by_count():
    t = LIB.get("mesh-paint-albedo-front")
    assert [r for r, _ in R.order_references(t, ["c.png", "p.png", "d.png"])] == ["clay_render", "painted_view", "design_plate"]
    with pytest.raises(R.RenderError, match="3"):
        R.order_references(t, ["c.png", "p.png"])


@pytest.mark.parametrize("model, params, ok", [
    ("openai/gpt-image-2.5-flare", {"size": "2880x2880"}, True), ("openai/gpt-image-2.5-sunburst", {"size": "2160x3840"}, True),
    ("openai/gpt-image-2.5-flare", {"size": "3840x3840"}, False), ("openai/gpt-image-2.5-flare", {"size": "4096x2048"}, False),
    ("openai/gpt-image-2.5-flare", {"resolution": "2K"}, False), ("black-forest-labs/flux-3-image", {"resolution": "2K", "aspect_ratio": "3:2"}, True),
    ("black-forest-labs/flux-3-image", {"size": "2048x2048"}, False), ("google/gemini-3.1-flash-image", {"resolution": "2K", "aspect_ratio": "1:1"}, True),
    ("sourceful/riverflow-v2.5-pro", {"resolution": "1K"}, True), ("bytedance-seed/seedream-5-0-lite", {"size": "1024x1024"}, False)])
def test_size_or_resolution_is_validated_per_model_family(model, params, ok):
    if ok:
        assert R.validate_image_params(model, params) == params
    else:
        with pytest.raises(R.RenderError):
            R.validate_image_params(model, params)


def test_render_translates_the_templates_size_into_what_the_chosen_models_family_takes():
    gpt = R.render(LIB, "mesh-paint-albedo-front", {}, model="openai/gpt-image-2.5-flare")
    assert gpt["params"]["size"] == "2880x2880" and "resolution" not in gpt["params"]
    flux = R.render(LIB, "mesh-paint-albedo-front", {}, model="black-forest-labs/flux-3-image")
    assert "size" not in flux["params"] and flux["params"]["resolution"] and flux["params"]["aspect_ratio"] == "1:1"
    tall = R.render(LIB, "character-reference-fullbody", {}, model="google/gemini-3.1-flash-image")
    assert tall["params"]["aspect_ratio"] == "9:16" and "size" not in tall["params"]


def test_the_image_gates_are_declared_per_template():
    gate_ids = {t["id"]: {g["id"] for g in t["gates"]} for t in LIB.list(media="image")}
    assert {"silhouette_iou"} <= gate_ids["mesh-paint-albedo-front"] and {"seam_step", "tone_seam"} <= gate_ids["seamless-tile"]
    assert {"region_count"} <= gate_ids["material-id-draft"] and "pieces_present" in gate_ids["character-reference-fullbody"]
    assert len(LIB.list(media="image")) == 9
