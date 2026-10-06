# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The client's door to the server's image slot: submit, poll, download, and the refusals (no login, failed job, no image, timeout)."""

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.features import jobs_client as J  # noqa: E402


def test_the_prompt_and_the_reference_go_up_and_the_downloaded_bytes_come_back(monkeypatch):
    sent, gets = [], []

    def request(method, path, body=None, timeout=120):
        if method == "POST":
            sent.append(body)
            return {"data": {"job_id": "j1", "status": "PENDING"}}
        gets.append(path)
        return {"data": {"job_id": "j1", "status": "DONE" if len(gets) >= 2 else "POLLING",
                         "result": {"images": [{"url": "http://127.0.0.1:1/f/1.png"}, {"url": "http://127.0.0.1:1/f/2.png"}]}}}
    monkeypatch.setattr(J, "_request", request)
    monkeypatch.setattr(J, "_download", lambda url, timeout=120: url.encode())
    out = J.generate_image("a lamp", b"REFPNG", 2, poll=0.0)
    assert out == [b"http://127.0.0.1:1/f/1.png", b"http://127.0.0.1:1/f/2.png"] and len(gets) == 2
    body = sent[0]
    assert body["service"] == "image_gen" and body["payload"]["prompt"] == "a lamp" and body["payload"]["params"]["number_of_images"] == 2
    assert base64.b64decode(body["payload"]["reference_images_b64"][0]) == b"REFPNG" and body["idempotency_key"]


def test_a_failed_job_a_missing_image_and_a_timeout_are_errors_with_the_reason(monkeypatch):
    monkeypatch.setattr(J, "_request", lambda *a, **k: {"data": {"job_id": "j", "status": "FAILED", "error": "the image model is down"}})
    with pytest.raises(J.ImageSlotError, match="the image model is down"):
        J.generate_image("x", None, poll=0.0)
    monkeypatch.setattr(J, "_request", lambda *a, **k: {"data": {"job_id": "j", "status": "DONE", "result": {"images": []}}})
    with pytest.raises(J.ImageSlotError, match="no image"):
        J.generate_image("x", None, poll=0.0)
    monkeypatch.setattr(J, "_request", lambda *a, **k: {"data": {"job_id": "j", "status": "POLLING"}})
    with pytest.raises(J.ImageSlotError, match="did not finish"):
        J.generate_image("x", None, timeout=0.05, poll=0.01)


def test_not_signed_in_is_refused_before_any_request(monkeypatch):
    monkeypatch.setattr(J, "_access_token", lambda: "")
    with pytest.raises(J.ImageSlotError, match="not signed in"):
        J._request("GET", "/x")


def test_extra_references_follow_the_first_in_order_and_a_ledger_row_posts_to_the_ledger(monkeypatch):
    sent = []

    def request(method, path, body=None, timeout=120):
        sent.append((method, path, body))
        if path == "/app/ledger":
            return {"id": "row1", **body}
        return {"data": {"job_id": "j1", "status": "DONE", "result": {"images": ["http://127.0.0.1:1/f/1.png"]}}}
    monkeypatch.setattr(J, "_request", request)
    monkeypatch.setattr(J, "_download", lambda url, timeout=120: b"IMG")
    J.generate_image("brass", b"CLAY", 1, poll=0.0, extra_references=[b"BRASS"])
    refs = [base64.b64decode(r) for r in sent[0][2]["payload"]["reference_images_b64"]]
    assert refs == [b"CLAY", b"BRASS"]
    assert J.record_ledger({"piece": "P", "stage": "texture"})["id"] == "row1" and sent[-1][:2] == ("POST", "/app/ledger")
