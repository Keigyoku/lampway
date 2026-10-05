"""One image model per PURPOSE (the coordinator's bake-off, scratch/subs/bakeoff): plates / mesh-paint, material-ID masks, concepts, seamless
tiles. Each purpose carries its own model and size/resolution; a request is validated against the model's supported_parameters
(GET /images/models/<id>/endpoints) and a parameter the model does not take is refused, never silently dropped."""

import base64
import json
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server import imagegen as IG
from lampway_server import provider_prefs as PP
from lampway_server.app import create_app

from .fake_client import FakeMixarClient

PNG = b"\x89PNG\r\n\x1a\n" + b"x"
ENDPOINTS = {
    "openai/gpt-image-2.5-flare": [],
    "google/gemini-3.1-flash-image": ["resolution", "aspect_ratio", "input_references"],
    "black-forest-labs/flux-3-image": ["resolution", "aspect_ratio", "input_references"],
    "sourceful/riverflow-v2.5-pro": ["resolution", "aspect_ratio", "input_references"],
}


@pytest.fixture
def wire(settings, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "ab12" * 16)
    monkeypatch.setenv("LAMPWAY_OPENROUTER_BUDGET_USD", "5")
    monkeypatch.setattr(IG, "_SUPPORTED", {})
    posts, gets = [], []

    def handler(request):
        if request.method == "GET":
            gets.append(request.url.path)
            model = request.url.path.split("/images/models/")[1].removesuffix("/endpoints")
            if model not in ENDPOINTS:
                return httpx.Response(404, json={"error": "no such model"})
            if model == "openai/gpt-image-2.5-flare":          # the REAL recorded response (GPT Image 2.5): endpoints at the top level, no `size` listed
                real = json.loads((Path(__file__).parent / "fixtures" / "image_endpoints_gpt_image_2_5.json").read_text())
                return httpx.Response(200, json=dict(real, id=model))
            return httpx.Response(200, json={"id": model, "endpoints": [{"supported_parameters": {p: {"type": "enum"} for p in ENDPOINTS[model]}}]})
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}], "usage": {"cost": 0.02}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    return posts, gets


def test_the_defaults_follow_the_bake_off(settings):
    p = PP.view(settings)["values"]["image_purposes"]
    assert p["plates"]["model"] == "openai/gpt-image-2.5-flare" and p["plates"]["size"] == "2880x2880"
    assert p["mask"]["model"] == "google/gemini-3.1-flash-image"
    assert p["concept"]["model"] == "black-forest-labs/flux-3-image" and p["concept"]["resolution"] == "2K"
    assert p["tile"]["model"] == "openai/gpt-image-2.5-flare"
    assert set(PP.view(settings)["choices"]["image_purposes"]) == {"plates", "mask", "concept", "tile"}


def test_the_size_budget_is_8_3_megapixels_with_at_most_3840_per_edge():
    assert PP.check_size("2160x3840") == "2160x3840" and PP.check_size("2880x2880") == "2880x2880"
    for bad in ("3840x3840", "4000x2000", "4K"):
        with pytest.raises(PP.PrefsError):
            PP.check_size(bad)


def test_a_purpose_is_saved_merged_and_validated(settings, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        ok = fake.put("/app/provider-settings", json={"values": {"image_purposes": {"plates": {"size": "2160x3840"}, "concept": {"resolution": "4K"}}}})
        assert ok.status_code == 200, ok.text
        p = ok.json()["values"]["image_purposes"]
        assert p["plates"]["size"] == "2160x3840" and p["plates"]["model"] == "openai/gpt-image-2.5-flare", "a partial update merges"
        assert p["concept"]["resolution"] == "4K" and p["mask"]["model"] == "google/gemini-3.1-flash-image"
        for bad in ({"poster": {"model": "x"}}, {"plates": {"size": "3840x3840"}}, {"concept": {"resolution": "8K"}}, {"plates": {"model": "no spaces!"}},
                    {"plates": {"colour": "red"}}):
            assert fake.put("/app/provider-settings", json={"values": {"image_purposes": bad}}).status_code == 400, bad


def test_each_purpose_sends_its_own_model_and_the_parameter_that_model_takes(wire):
    posts, gets = wire
    IG.openrouter_images("p", [], 1, purpose="plates")
    IG.openrouter_images("p", [], 1, purpose="concept", aspect_ratio="3:2")
    IG.openrouter_images("p", [], 1, purpose="mask")
    plates, concept, mask = posts
    assert plates["model"] == "openai/gpt-image-2.5-flare" and plates["size"] == "2880x2880" and "resolution" not in plates
    assert concept["model"] == "black-forest-labs/flux-3-image" and concept["resolution"] == "2K" and concept["aspect_ratio"] == "3:2" and "size" not in concept
    assert mask["model"] == "google/gemini-3.1-flash-image" and "size" not in mask
    assert len(gets) == 3 and all(g.endswith("/endpoints") for g in gets)


def test_a_parameter_the_model_does_not_list_is_refused_not_dropped(wire, settings, monkeypatch):
    posts, _ = wire
    PP.save(settings.state_dir, {"image_purposes": {"plates": {"model": "google/gemini-3.1-flash-image", "size": "2880x2880"}}})
    with pytest.raises(ValueError, match="size"):
        IG.openrouter_images("p", [], 1, purpose="plates")
    assert posts == []


def test_the_supported_parameters_are_cached_per_model_and_a_lookup_failure_falls_back_to_the_model_family(wire):
    posts, gets = wire
    IG.openrouter_images("p", [], 1, purpose="plates")
    IG.openrouter_images("p", [], 1, purpose="tile")
    assert len(gets) == 1, "the same model is asked once"
    assert IG.supported_parameters_fallback("unknown/vendor-model") is None
    assert "size" in IG.supported_parameters_fallback("openai/gpt-image-2.5-sunburst") and "resolution" in IG.supported_parameters_fallback("sourceful/riverflow-v2.5-pro")


def test_the_job_payload_and_the_tool_choose_the_purpose(wire):
    posts, _ = wire
    IG.openrouter_image_backend("default", {"prompt": "x", "params": {"number_of_images": 1, "purpose": "concept"}})
    assert posts[-1]["model"] == "black-forest-labs/flux-3-image"
    IG.openrouter_image_backend("default", {"prompt": "x", "params": {"number_of_images": 1}})
    assert posts[-1]["model"] == "openai/gpt-image-2.5-flare", "no purpose = plates"
    from lampway_server.agent import server_tools as ST
    assert "purpose" in ST.BY_NAME["studio_image_generate"].spec().parameters["properties"]
    with pytest.raises(ValueError, match="purpose"):
        IG.openrouter_images("p", [], 1, purpose="poster")


def test_the_real_gpt_image_endpoint_record_is_parsed_and_size_is_an_accepted_passthrough_for_the_openai_family(wire):
    posts, gets = wire
    real = json.loads((Path(__file__).parent / "fixtures" / "image_endpoints_gpt_image_2_5.json").read_text())
    assert "endpoints" in real and "size" not in real["endpoints"][0]["supported_parameters"], "the premise: the live record lists no size"
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=real))) as c:
        got = IG.supported_parameters(c, "k", "openai/gpt-image-2.5-sunburst")
    assert {"aspect_ratio", "quality", "input_references"} <= got, "parsed from the top-level endpoints, supported_parameters being a dict"
    IG.openrouter_images("p", [], 1, purpose="plates")
    IG.openrouter_images("p", [], 1, purpose="plates", size="2160x3840")
    assert posts[0]["size"] == "2880x2880" and posts[1]["size"] == "2160x3840"
    for bad in ("3840x3840", "4096x2048"):
        with pytest.raises(ValueError, match="budget"):
            IG.openrouter_images("p", [], 1, purpose="plates", size=bad)
