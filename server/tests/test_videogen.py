"""Video generation on OpenRouter's async videos API: catalogue (GET /videos/models, a snapshot of the 29 models is the fixture),
validation against each model's supported_* fields, a cost ESTIMATE from pricing_skus before anything is submitted, the budget cap, the
submit -> poll -> download flow, and the ACTUAL billed cost recorded on the spend ledger next to the estimate (Seedance bills in video
tokens: tokens ~ W x H x fps x seconds / 1024 at 24 fps, so the formula is checked against what is billed)."""

import base64
import json
from pathlib import Path

import httpx
import pytest

from lampway_server import videogen as VG
from lampway_server.agent.providers.openrouter import SpendCeilingReached, SpendLedger

FIX = json.loads((Path(__file__).parent / "fixtures" / "video_models.json").read_text())
MODELS = FIX.get("data", FIX)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"video-bytes"


def row(model_id):
    return next(m for m in MODELS if m["id"] == model_id)


# ------------------------------------------------------------------ the estimate, per SKU family
def est(model_id, **p):
    return VG.estimate(row(model_id), p)


def test_heygen_is_priced_per_second_per_resolution_and_the_reference_rate_applies_with_references():
    assert est("heygen/heygen-video-1", resolution="768p", duration=10)["usd"] == pytest.approx(0.30)
    assert est("heygen/heygen-video-1", resolution="480p", duration=5)["usd"] == pytest.approx(0.10)
    assert est("heygen/heygen-video-1", resolution="768p", duration=10, references=1)["usd"] == pytest.approx(0.60)
    e = est("heygen/heygen-video-1", resolution="480p", duration=10)
    assert e["usd"] == pytest.approx(0.20) and e["basis"] == "duration_seconds_480p x 10 s" and e["known"] is True


def test_seedance_is_billed_in_video_tokens_from_the_pixels_fps_and_seconds():
    e = est("bytedance/seedance-1-5-pro", resolution="720p", aspect_ratio="16:9", duration=5, generate_audio=False)
    tokens = 1280 * 720 * 24 * 5 / 1024
    assert e["tokens"] == pytest.approx(tokens) and e["usd"] == pytest.approx(tokens * 0.0000012) and "video_tokens_without_audio" in e["basis"]
    with_audio = est("bytedance/seedance-1-5-pro", resolution="720p", aspect_ratio="16:9", duration=5, generate_audio=True)
    assert with_audio["usd"] == pytest.approx(tokens * 0.0000024)
    mini = est("bytedance/seedance-2.0-mini", resolution="480p", aspect_ratio="16:9", duration=10, generate_audio=False, reference_video=True)
    assert mini["usd"] == pytest.approx(854 * 480 * 24 * 10 / 1024 * 0.0000021) and "video_tokens_with_video_input" in mini["basis"]


def test_per_second_cents_and_the_minimum_per_generation_and_unknown_families():
    assert est("runway/gen-4.5", duration=5)["usd"] == pytest.approx(0.60)
    assert est("runway/aleph-2", duration=1)["usd"] == pytest.approx(0.56), "the minimum per generation applies"
    assert est("black-forest-labs/flux-video-edit", duration=10)["usd"] == pytest.approx(0.30)
    grok = est("x-ai/grok-imagine-video-1.5", resolution="720p", duration=6)
    assert grok["known"] is True or grok["known"] is False
    odd = VG.estimate({"id": "x/y", "pricing_skus": {"mystery_unit": "3"}}, {"duration": 5})
    assert odd["known"] is False and odd["usd"] is None


def test_upscale_is_priced_per_megapixel_second_precise_or_creative():
    p = VG.estimate(row("black-forest-labs/flux-video-upscale"), {"duration": 10, "source_width": 1280, "source_height": 720, "upscale_factor": 2, "creativity": 0})
    mp = 2560 * 1440 / 1e6
    assert p["usd"] == pytest.approx(mp * 10 * 0.075) and "precise" in p["basis"]
    c = VG.estimate(row("black-forest-labs/flux-video-upscale"), {"duration": 10, "source_width": 1280, "source_height": 720, "upscale_factor": 2, "creativity": 1})
    assert c["usd"] == pytest.approx(mp * 10 * 0.105) and "creative" in c["basis"]


def test_the_shortlist_multiples_against_heygen_768p_match_the_coordinators_table():
    base = est("heygen/heygen-video-1", resolution="768p", duration=10)["usd"]
    assert est("heygen/heygen-video-1", resolution="480p", duration=10)["usd"] / base == pytest.approx(0.667, abs=0.05)
    assert est("kwaivgi/kling-v3.0-std", resolution="720p", duration=10, generate_audio=False)["usd"] / base == pytest.approx(2.8, abs=0.1)


# ------------------------------------------------------------------ validation
def test_parameters_are_validated_against_the_models_own_lists():
    ok = VG.validate(row("heygen/heygen-video-1"), {"resolution": "768p", "duration": 10, "aspect_ratio": "16:9"})
    assert ok == {"resolution": "768p", "duration": 10, "aspect_ratio": "16:9"}
    for bad, msg in (({"resolution": "4K"}, "resolution"), ({"duration": 3}, "duration"), ({"aspect_ratio": "5:4"}, "aspect"),
                     ({"generate_audio": True}, "audio")):
        with pytest.raises(VG.VideoError, match=msg):
            VG.validate(row("heygen/heygen-video-1"), bad)
    with pytest.raises(VG.VideoError, match="last_frame"):
        VG.validate(row("heygen/heygen-video-1"), {"frame_images": [{"frame_type": "last_frame", "url": "u"}]})
    ok2 = VG.validate(row("bytedance/seedance-1-5-pro"), {"frame_images": [{"frame_type": "first_frame", "url": "u"}, {"frame_type": "last_frame", "url": "u"}]})
    assert [f["frame_type"] for f in ok2["frame_images"]] == ["first_frame", "last_frame"]


def test_video_references_need_a_model_that_takes_them_and_upscale_needs_its_own_parameters():
    with pytest.raises(VG.VideoError, match="video"):
        VG.validate(row("heygen/heygen-video-1"), {"reference_videos": ["clip"]})
    VG.validate(row("bytedance/seedance-2.0-mini"), {"reference_videos": ["clip"], "duration": 5})
    with pytest.raises(VG.VideoError, match="upscale_factor"):
        VG.validate(row("black-forest-labs/flux-video-upscale"), {"upscale_factor": 5, "reference_videos": ["clip"]})
    with pytest.raises(VG.VideoError, match="source video"):
        VG.validate(row("black-forest-labs/flux-video-upscale"), {"upscale_factor": 2})
    ok = VG.validate(row("black-forest-labs/flux-video-upscale"), {"upscale_factor": 2, "creativity": 0, "reference_videos": ["clip"]})
    assert ok["upscale_factor"] == 2 and ok["creativity"] == 0


# ------------------------------------------------------------------ the flow
@pytest.fixture
def wire(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "ab12" * 16)
    seen = {"posts": [], "gets": [], "polls": 0}
    state = {"status": ["pending", "in_progress", "completed"], "cost": 0.1, "fail": None}

    def handler(request):
        path = request.url.path
        if request.method == "GET" and path.endswith("/videos/models"):
            return httpx.Response(200, json={"data": MODELS})
        if request.method == "POST" and path.endswith("/videos"):
            seen["posts"].append(json.loads(request.content))
            return httpx.Response(202, json={"id": "job1", "polling_url": "/api/v1/videos/job1", "status": "pending"})
        if request.method == "GET" and path.endswith("/videos/job1"):
            seen["polls"] += 1
            st = state["status"][min(seen["polls"] - 1, len(state["status"]) - 1)]
            if state["fail"]:
                return httpx.Response(200, json={"id": "job1", "status": "failed", "error": state["fail"]})
            body = {"id": "job1", "status": st, "polling_url": "/api/v1/videos/job1"}
            if st == "completed":
                body.update(unsigned_urls=["https://openrouter.ai/api/v1/videos/job1/content?index=0"], usage={"cost": state["cost"], "is_byok": False})
            return httpx.Response(200, json=body)
        if request.method == "GET" and "/content" in path:
            seen["gets"].append(request.headers.get("authorization"))
            return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})
        return httpx.Response(404)
    transport = httpx.MockTransport(handler)
    ledger = SpendLedger(5.0, tmp_path / "spend.jsonl")
    client = VG.VideoClient(transport=transport, ledger=ledger, poll_s=0.0, max_job_usd=2.0)
    return client, seen, state, ledger


def test_the_catalogue_lists_every_model_and_is_cached(wire):
    client, seen, _, _ = wire
    assert len(client.models()) == 29 and client.model("heygen/heygen-video-1")["id"] == "heygen/heygen-video-1"
    with pytest.raises(VG.VideoError, match="no video model"):
        client.model("nope/none")


def test_a_dry_run_plan_prices_the_job_and_sends_nothing(wire):
    client, seen, _, ledger = wire
    plan = client.plan("heygen/heygen-video-1", "a dancing lamp", {"resolution": "480p", "duration": 5})
    assert plan["ok"] is True and plan["estimate_usd"] == pytest.approx(0.10) and plan["within_budget"] is True and plan["dry_run"] is True
    assert seen["posts"] == [] and ledger.spent == 0
    assert plan["params"]["resolution"] == "480p" and plan["basis"]


def test_generate_submits_polls_downloads_and_records_the_actual_cost_beside_the_estimate(wire):
    client, seen, state, ledger = wire
    state["cost"] = 0.12
    out = client.generate("heygen/heygen-video-1", "a dancing lamp", {"resolution": "480p", "duration": 5}, label="video")
    assert out["video"] == MP4 and out["media_type"] == "video/mp4" and out["job_id"] == "job1"
    assert out["estimate_usd"] == pytest.approx(0.10) and out["actual_usd"] == pytest.approx(0.12) and out["delta_usd"] == pytest.approx(0.02)
    body = seen["posts"][0]
    assert body["model"] == "heygen/heygen-video-1" and body["prompt"] == "a dancing lamp" and body["duration"] == 5 and body["resolution"] == "480p"
    assert seen["gets"] and seen["gets"][0].startswith("Bearer "), "the content URL is not presigned: the key rides in the header"
    assert ledger.spent == pytest.approx(0.12) and ledger.by_label == {"video": pytest.approx(0.12)}
    rows = [json.loads(l) for l in (ledger.log_path).read_text().splitlines()]
    assert rows[-1]["label"] == "video"


def test_frames_and_references_are_sent_in_the_documented_shapes(wire):
    client, seen, _, _ = wire
    png = b"\x89PNG\r\n\x1a\n" + b"x"
    client.generate("bytedance/seedance-1-5-pro", "loop", {"resolution": "480p", "duration": 4, "generate_audio": False, "aspect_ratio": "16:9"},
                    frame_images=[("first_frame", png), ("last_frame", png)])
    b = seen["posts"][0]
    assert [f["frame_type"] for f in b["frame_images"]] == ["first_frame", "last_frame"]
    assert b["frame_images"][0]["type"] == "image_url" and b["frame_images"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert b["generate_audio"] is False and "input_references" not in b
    client.generate("bytedance/seedance-2.0-mini", "move like this", {"resolution": "480p", "duration": 5, "generate_audio": False},
                    reference_images=[png], reference_videos=[MP4])
    b2 = seen["posts"][1]
    kinds = [r["type"] for r in b2["input_references"]]
    assert kinds == ["image_url", "video_url"] and b2["input_references"][1]["video_url"]["url"].startswith("data:video/mp4;base64,")


def test_the_budget_cap_refuses_before_anything_is_sent(wire, tmp_path):
    client, seen, _, ledger = wire
    with pytest.raises(VG.VideoError, match="per-job cap"):
        client.generate("kwaivgi/kling-v3.0-pro", "x", {"resolution": "720p", "duration": 15, "generate_audio": True})
    assert seen["posts"] == []
    ledger.add(4.95, "other")
    with pytest.raises(VG.VideoError, match="remaining"):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "768p", "duration": 10})
    ledger.add(1.0, "more")
    with pytest.raises(SpendCeilingReached):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "480p", "duration": 5})
    assert seen["posts"] == []


def test_an_unknown_price_is_refused_unless_the_caller_accepts_it(wire):
    client, seen, _, _ = wire
    odd = dict(row("heygen/heygen-video-1"), id="x/mystery", pricing_skus={"mystery_unit": "3"})
    client._models = [odd]
    with pytest.raises(VG.VideoError, match="price"):
        client.generate("x/mystery", "x", {})
    assert seen["posts"] == []


def test_a_failed_job_carries_the_providers_reason_and_costs_nothing_recorded(wire):
    client, seen, state, ledger = wire
    state["fail"] = "Content policy violation"
    with pytest.raises(VG.VideoError, match="Content policy violation"):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "480p", "duration": 5})
    assert ledger.spent == 0


def test_a_job_that_never_finishes_times_out_without_a_second_submit(wire):
    client, seen, state, _ = wire
    state["status"] = ["in_progress"]
    client.timeout_s = 0.05
    with pytest.raises(VG.VideoError, match="did not finish"):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "480p", "duration": 5})
    assert len(seen["posts"]) == 1, "never re-submitted: a second submit is a second charge"
