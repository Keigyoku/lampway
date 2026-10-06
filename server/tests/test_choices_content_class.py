# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md step 6, first release (HC24 with the captain's CH1: observe-only): the image, video, Studio and dictation calls
declare their purpose's content class, so the egress log records what the private rule WOULD refuse - and nothing is refused yet. The
rule itself still refuses when a call does not ask to be observed (the existing gate is unchanged)."""

import asyncio
import base64
import json

import httpx
import pytest

from lampway_server import egress as E

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
KEY = "sk-" "or-v1-" + "cd34" * 16


@pytest.fixture
def strict(tmp_path):
    eg = E.Egress(tmp_path / "eg")
    for r in ("openrouter", "studio:meshy"):
        eg.set_route(r, True)
    E.set_active(eg)
    return eg


def _sends(eg):
    return [r for r in eg.log() if r.get("event") == "send"]


def test_the_observe_flag_records_and_sends_while_the_rule_still_refuses_without_it(strict):
    with E.context(content_class="private", observe_private=True):
        route = strict.begin("api.meshy.ai", "POST", 10)
    strict.end(route)
    assert _sends(strict)[-1]["would_refuse_private"] is True and _sends(strict)[-1]["content_class"] == "private"
    with E.context(content_class="private"):
        with pytest.raises(E.EgressRefused):
            strict.begin("api.meshy.ai", "POST", 10)


def test_an_image_request_declares_private_and_is_observed(strict, monkeypatch):
    from lampway_server import imagegen as IG
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(PNG).decode()}], "usage": {"cost": 0.01}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    out = IG.openrouter_images("a helmet", [], 1, purpose="plates")
    assert out and _sends(strict)[-1]["content_class"] == "private" and _sends(strict)[-1]["would_refuse_private"] is True


def test_a_video_request_declares_private_and_is_observed(strict, monkeypatch, tmp_path):
    from pathlib import Path
    from lampway_server import videogen as VG
    from lampway_server.agent.providers.openrouter import SpendLedger
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    fix = json.loads((Path(__file__).parent / "fixtures" / "video_models.json").read_text())
    models = fix.get("data", fix)

    def handler(request):
        path = request.url.path
        if request.method == "GET" and path.endswith("/videos/models"):
            return httpx.Response(200, json={"data": models})
        if request.method == "POST" and path.endswith("/videos"):
            return httpx.Response(202, json={"id": "job1", "polling_url": "/api/v1/videos/job1", "status": "pending"})
        if request.method == "GET" and path.endswith("/videos/job1"):
            return httpx.Response(200, json={"id": "job1", "status": "completed", "polling_url": "/api/v1/videos/job1",
                                             "unsigned_urls": ["https://openrouter.ai/api/v1/videos/job1/content?index=0"], "usage": {"cost": 0.1}})
        if "/content" in path:
            return httpx.Response(200, content=b"mp4", headers={"content-type": "video/mp4"})
        return httpx.Response(404)
    client = VG.VideoClient(transport=httpx.MockTransport(handler), ledger=SpendLedger(5.0, tmp_path / "spend.jsonl"), poll_s=0.0, max_job_usd=2.0)
    client.generate("heygen/heygen-video-1", "a walk", {"resolution": "480p", "duration": 5}, label="video")
    posts = [r for r in _sends(strict) if r["method"] == "POST"]
    assert posts and posts[-1]["content_class"] == "private" and posts[-1]["would_refuse_private"] is True


def test_dictation_declares_private_and_is_observed(strict):
    from lampway_server import dictation as D
    from lampway_server.agent.providers.openrouter import SpendLedger

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})
    t = D.OpenRouterTranscriber(KEY, "google/gemini-3.8-flash", SpendLedger(1.0), transport=httpx.MockTransport(handler))
    assert asyncio.run(t.transcribe(b"\x00\x00" * 1600)) == "hello"
    assert _sends(strict)[-1]["content_class"] == "private" and _sends(strict)[-1]["would_refuse_private"] is True


def test_a_studio_driver_run_declares_private_and_is_observed(strict, tmp_path):
    from lampway_server.studios.service import StudioService

    def execute(argv, env, timeout):
        return 0, "dry_run: verified\nprice_effective_credits: 20\nbalance_credits: 100\n"
    model = tmp_path / "project" / "piece.glb"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"glb")
    asyncio.run(StudioService(tmp_path / "project", execute).plan("meshy.uv_unwrap", {"model": str(model)}, by="agent"))
    row = [r for r in _sends(strict) if r["route"] == "studio:meshy"][-1]
    assert row["content_class"] == "private" and row["would_refuse_private"] is True
