"""POST /app/generate/estimate: what the island's Image and Video tabs show before anything is sent (facelift contract 08). The price is
marked as the kind of number it is (an estimate from the model listing or a measured per-image figure, never read back), the policy the
Providers dialog set decides whether it needs a click (an unknown price always does unless the policy is off), a cap refuses it before it
is sent, and nothing leaves: an estimate is computed from what the server already holds."""

from lampway_server import videogen as VG

from .test_video_jobs import MODELS, stack  # noqa: F401  (the shared stack fixture)


def _estimate(fake, service, model, params, references=0):
    r = fake.post("/app/generate/estimate", json={"service": service, "model": model, "params": params, "references": references})
    assert r.status_code == 200, r.text
    return r.json()


def test_an_image_estimate_is_an_estimate_per_image_and_waits_only_above_the_line(stack):
    fake, orv, *_rest, app = stack
    app.state.settings.spend_policy["openrouter"] = {"click": "above", "above": 0.25}
    three = _estimate(fake, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 3})
    assert three["provider"] == "openrouter" and three["route"] == "openrouter"
    assert three["price"]["kind"] == "estimate" and three["price"]["unit"] == "USD" and three["price"]["amount"] == 0.21
    assert "per image" in three["price"]["source"]
    assert three["needs_click"] is False and three["refused"] is None
    four = _estimate(fake, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 4})
    assert four["price"]["amount"] == 0.28 and four["needs_click"] is True
    assert four["policy"] == {"click": "above", "above": 0.25, "job_cap": None, "session_cap": None, "spent": 0.0}
    assert orv.posts == [], "an estimate sends nothing"


def test_a_video_estimate_is_the_model_listings_price(stack):
    fake, orv, *_rest, app = stack
    row = next(m for m in MODELS if m["id"] == "heygen/heygen-video-1")
    params = {"duration": 5, "resolution": "480p"}
    out = _estimate(fake, "video_gen", "heygen/heygen-video-1", params)
    want = VG.estimate(row, VG.validate(row, dict(params, frame_images=[], reference_videos=[])) | {"frames": 0, "references": 0})
    assert out["price"]["kind"] == "estimate" and out["price"]["amount"] == round(want["usd"], 4)
    assert out["price"]["source"].startswith("OpenRouter model listing, read ") and out["price"]["basis"] == want["basis"]
    assert orv.posts == []


def test_an_unknown_price_needs_a_click_even_under_click_above(stack):
    fake, *_rest, app = stack
    app.state.settings.spend_policy["openrouter"] = {"click": "above", "above": 0.25}
    out = _estimate(fake, "video_gen", "heygen/heygen-video-1", {"resolution": "480p"})       # no duration: no price family fits
    assert out["price"] is None and out["basis"] and out["needs_click"] is True
    app.state.settings.spend_policy["openrouter"] = {"click": "off"}
    assert _estimate(fake, "video_gen", "heygen/heygen-video-1", {"resolution": "480p"})["needs_click"] is False


def test_a_higgsfield_price_is_unknown_until_it_is_read_back(stack):
    fake, *_rest = stack
    out = _estimate(fake, "video_gen", "higgsfield/kling-3", {"duration": 5})
    assert out["provider"] == "higgsfield" and out["route"] == "higgsfield" and out["price"] is None
    assert "read back" in out["basis"] and out["needs_click"] is True


def test_a_cap_refuses_before_anything_is_sent(stack):
    fake, orv, *_rest, app = stack
    app.state.settings.spend_policy["openrouter"] = {"click": "off", "job_cap": 0.1}
    out = _estimate(fake, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 2})
    assert "per-job cap" in out["refused"] and orv.posts == []


def test_the_estimate_needs_a_signed_in_client(stack):
    fake, *_rest = stack
    r = fake.post("/app/generate/estimate", json={"service": "image_gen", "model": "x"}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
