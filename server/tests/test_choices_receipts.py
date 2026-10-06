# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_store.md test 10 and choices_migration.md tests 3-4 (HC6, HC7, HC10): what the Client is shown, what runs and what the receipt
says agree. The image_gen job resolves its purpose (the Client's purpose param, else AI Render, which follows Plates), runs the resolved
model on OpenRouter, labels the catalogue with that model, and its receipt carries the ``choice`` - never ``"default"``."""

import asyncio
import base64
import json

import httpx
import pytest

from lampway_server import imagegen as IG
from lampway_server import jobreceipts as JR

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
KEY = "sk-" "or-v1-" + "ab12" * 16


def test_a_receipt_keeps_the_choice_and_export_keeps_it(tmp_path):
    rec = {"purpose": "image.plates", "option": "openrouter:openai/gpt-image-2.5-flare", "reason": "fallback", "why": "fallback: x"}
    r, _ = JR.JobReceipts(tmp_path).create("openrouter", "openai/gpt-image-2.5-flare", {"prompt": "p"}, None, "user", choice=rec)
    assert r["choice"] == rec and JR.export_safe(r)["choice"] == rec


@pytest.fixture
def orouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    for k in ("LAMPWAY_IMAGE_BACKEND", "LAMPWAY_OPENROUTER_IMAGE_MODEL"):
        monkeypatch.delenv(k, raising=False)
    seen = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404, json={})
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}],
                                         "usage": {"cost": 0.04}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    return seen


def _run(http, auth, body):
    r = http.post("/api/v1/job-queue/jobs", json=body, headers=auth)
    assert r.status_code == 200, r.text
    jid = r.json()["data"]["job_id"] if "job_id" in r.json()["data"] else r.json()["data"]["id"]
    for _ in range(100):
        snap = http.get(f"/api/v1/job-queue/jobs/{jid}", headers=auth).json()["data"]
        if snap.get("status") in ("DONE", "FAILED"):
            return snap
        asyncio.run(asyncio.sleep(0.05))
    return snap


@pytest.fixture
def auth(fake):
    fake.login()
    return fake.rest_headers()


def test_receipt_carries_the_choice(orouter, http, auth, settings):
    snap = _run(http, auth, {"service": "image_gen", "model": "default", "payload": {"prompt": "a bronze helmet"}})
    assert snap["status"] == "DONE", snap
    asked = orouter[0]["model"]
    [r] = [json.loads(p.read_text()) for p in (settings.state_dir.parent / "project" / "jobs").rglob("receipt.json")]
    assert r["model"] == asked != "default"
    assert r["choice"]["option"] == f"openrouter:{asked}" and r["choice"]["purpose"] == "image.ai_render" and r["choice"]["followed"] == "image.plates"
    assert r["choice"]["reason"] == "fallback" and "studio:tripo.image cannot run here" in r["choice"]["why"]


def test_image_gen_label_matches_the_model(orouter, http, auth):
    cat = http.get("/api/v1/generation-catalog", headers=auth).json()["data"]
    [svc] = [s for c in cat["capabilities"] if c["key"] == "image_gen" for s in c["services"]]
    label = svc["models"][0]["label"]
    _run(http, auth, {"service": "image_gen", "model": "default", "payload": {"prompt": "a bronze helmet"}})
    assert label == orouter[0]["model"], "the Client is shown the model that runs (HC7)"


def test_the_clients_purpose_is_the_purpose_resolved(orouter, http, auth):
    _run(http, auth, {"service": "image_gen", "model": "default", "payload": {"prompt": "a mood", "params": {"purpose": "concept"}}})
    assert orouter[0]["model"] == "black-forest-labs/flux-3-image"


def test_the_clients_model_is_a_job_override(orouter, http, auth, settings):
    _run(http, auth, {"service": "image_gen", "model": "google/gemini-3.1-flash-image", "payload": {"prompt": "x"}})
    assert orouter[0]["model"] == "google/gemini-3.1-flash-image"
    [r] = [json.loads(p.read_text()) for p in (settings.state_dir.parent / "project" / "jobs").rglob("receipt.json")]
    assert r["choice"]["reason"] == "override"
