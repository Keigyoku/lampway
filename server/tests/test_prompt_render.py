"""Rendering: typed variables validated before anything is filled (a refusal names the variable), the five-part spine joined in order, negatives capped at 5,
timed beats as 'Timing: ...', per-model adapters (reference naming, length limits, unsupported phrases), the result {prompt, negatives, inputs_required, params}.
And the built-ins: every one loads and renders for every model it declares."""

import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import render as R

from .test_prompt_library import template


_TMP = None


@pytest.fixture(autouse=True)
def _per_test_tmp(tmp_path):
    global _TMP
    _TMP = tmp_path


def lib_with(**kw):
    import json, tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp(dir=_TMP))                                          # under the test's own tmp_path, never the shared /tmp
    (d / "t.json").write_text(json.dumps(template(**kw)))
    return L.Library(builtin_dir=d)


def test_the_spine_renders_in_order_with_defaults_and_the_params_come_from_the_template():
    out = R.render(lib_with(), "demo-walk", {"cadence_spm": 120, "direction": "right"})
    p = out["prompt"]
    assert p.index("This warrior") < p.index("He walks at 120") < p.index("Side-on tracking") < p.index("Even flat light") < p.index("Full body in frame")
    assert "same armour design" in p, "a default fills an unset variable"
    assert out["params"] == {"resolution": "768p", "aspect_ratio": "16:9", "duration": 10}       # CH5: the template's model is a hint, not a param
    assert out["template_model"] == "heygen/heygen-video-1" and out["model"] is None
    assert out["template"] == "demo-walk@1.0.0" and out["variables"]["cadence_spm"] == 120 and out["variables"]["direction"] == "right"
    assert out["inputs_required"] == [{"role": "start_image", "required": True, "description": "full-body side view in the start pose"}]


@pytest.mark.parametrize("variables, name", [({"cadence_spm": 300}, "cadence_spm"), ({"cadence_spm": 10}, "cadence_spm"), ({"cadence_spm": "fast"}, "cadence_spm"),
                                             ({"direction": "up"}, "direction"), ({"nonsense": 1}, "nonsense"), ({"design_lock": 7}, "design_lock")])
def test_bad_variables_are_refused_naming_the_variable(variables, name):
    with pytest.raises(R.RenderError, match=name):
        R.render(lib_with(), "demo-walk", variables)


def test_a_variable_without_a_default_must_be_given():
    t = template()
    t["variables"]["design_lock"].pop("default")
    with pytest.raises(R.RenderError, match="design_lock"):
        R.render(lib_with(variables=t["variables"]), "demo-walk", {})
    assert "STEEL" in R.render(lib_with(variables=t["variables"]), "demo-walk", {"design_lock": "STEEL"})["prompt"]


def test_negatives_render_at_most_five_and_beats_render_as_timing():
    lib = lib_with(negatives=[f"no thing {i}" for i in range(5)], beats=[{"t0": 0, "t1": 2, "action": "{{design_lock}} stands"}, {"t0": 2, "t1": 6.5, "action": "walks"}])
    out = R.render(lib, "demo-walk", {})
    assert len(out["negatives"]) == 5 and all(n in out["prompt"] for n in out["negatives"])
    assert "Timing: 0-2 s: same armour design stands; 2-6.5 s: walks." in out["prompt"]
    assert len(R.cap_negatives([f"n{i}" for i in range(9)])) == 5


def test_adapters_rename_references_cut_phrases_and_report_length_per_model():
    adapters = {"bytedance/seedance*": {"ref_names": {"start_image": "the start image"}, "drop_phrases": ["long lens"], "replace": {"tracking shot": "tracking shot (camera follows)"}},
                "higgsfield/*": {"ref_names": {"start_image": "the first reference image"}, "max_words": 10},
                "heygen/*": {"note": "audio is always on"}}
    lib = lib_with(model_adapters=adapters)
    seed = R.render(lib, "demo-walk", {}, model="bytedance/seedance-1-5-pro")
    assert "the start image" in seed["prompt"] and "[start_image]" not in seed["prompt"] and "long lens" not in seed["prompt"] and "(camera follows)" in seed["prompt"]
    higgs = R.render(lib, "demo-walk", {}, model="higgsfield/seedance1_5")
    assert "the first reference image" in higgs["prompt"] and any("10 words" in w for w in higgs["warnings"])
    hey = R.render(lib, "demo-walk", {}, model="heygen/heygen-video-1")
    assert "the start image" in hey["prompt"] and "audio is always on" in " ".join(hey["warnings"]) and hey["params"]["model"] == "heygen/heygen-video-1"
    assert R.render(lib, "demo-walk", {}, model="unlisted/model")["prompt"], "a model with no adapter still renders with the default naming"


def test_an_unknown_template_or_version_is_a_clear_error():
    with pytest.raises(L.LibraryError, match="nope"):
        R.render(lib_with(), "nope", {})


def test_every_builtin_loads_and_renders_for_every_model_it_declares():
    lib = L.Library()
    assert lib.errors == [], lib.errors
    assert len(lib.list()) >= 16
    for t in lib.list():
        models = {t["defaults"]["model"]} if t.get("defaults", {}).get("model") else set()
        models |= {m.replace("*", "x") for m in t.get("model_adapters", {})}
        assert models, t["id"]
        for model in sorted(models):
            out = R.render(lib, t["id"], {}, model=model)
            assert out["prompt"].strip() and "{{" not in out["prompt"] and "[start_image]" not in out["prompt"] and len(out["negatives"]) <= 5, (t["id"], model)
