"""The job queue and the generation catalog: what Mixar's Media -> Image Generation, the Moodboard's Image Gen card and
the chat's Generate mode run on (docs: "Generate and edit images", "Follow jobs in Queue").

The client's contract (audit/protocol.json job_queue.*, generation_catalog, job.sync/job.get/job.update):
  * GET /api/v1/generation-catalog -> capabilities[{key, label, sort_order, services[{key, surface, sort_order,
    models[{slug, label, is_default, max_reference_images, parameters{...}}]}]}]; an EMPTY list hides every
    generation tab (the kill switch), so a service is advertised only when a backend exists for it;
  * POST /api/v1/job-queue/jobs {service, model, payload, idempotency_key} -> data{job_id, status};
  * a compact job.update push over the agent socket on every state change; a terminal "succeeded" makes the client
    send job.get, whose snapshot carries result.images[{url}] (+ image_name); the client downloads the URL with
    plain urllib, so the file route is unauthenticated but unguessable;
  * GET/DELETE /api/v1/job-queue/jobs/{id}; job.sync lists the snapshots.
"""

import io
import json

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app

from .fake_client import FakeMixarClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeImages:
    """A job backend: ``(model, payload) -> ImageOutput``; records what it was asked."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, model, payload):
        from lampway_server.jobqueue import ImageOutput
        self.calls.append((model, payload))
        if self.fail:
            raise RuntimeError("the image model is down")
        n = int((payload.get("params") or {}).get("number_of_images") or 1)
        return ImageOutput(images=[(PNG, "image/png")] * n, image_name=payload.get("image_name") or "")


@pytest.fixture
def stack(settings, provider):
    backend = FakeImages()
    app = create_app(settings, provider=provider, job_backends={"image_gen": backend})
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake, backend, app


def terminal_update(ws, job_id):
    """The job.update that ends ``job_id`` (a 'running' push precedes it)."""
    for _ in range(20):
        frame = ws.receive_json()
        if frame.get("method") == "job.update" and frame["params"]["job_id"] == job_id \
                and frame["params"]["state"] in ("succeeded", "failed", "cancelled"):
            return frame["params"]
    raise AssertionError("no terminal job.update")


def reply_to(ws, request_id):
    for _ in range(20):
        frame = ws.receive_json()
        if frame.get("id") == request_id:
            return frame["result"]
    raise AssertionError(f"no reply to {request_id}")


def _catalog(fake):
    r = fake.get("/api/v1/generation-catalog")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_the_catalog_is_empty_without_a_backend_and_advertises_image_gen_with_one(http, fake, stack):
    fake.login()
    assert _catalog(fake)["capabilities"] == []
    _, fake2, _, _ = stack
    caps = _catalog(fake2)["capabilities"]
    assert [c["key"] for c in caps] == ["image_gen"]
    service = caps[0]["services"][0]
    assert service["key"] == "image_gen" and service["surface"] == "moodboard"
    model = next(m for m in service["models"] if m["is_default"])
    assert model["max_reference_images"] >= 1
    n = model["parameters"]["number_of_images"]
    assert n["type"] == "integer" and n["default"] == 1 and n["min"] == 1 and n["max"] == 4


def test_an_image_job_runs_and_the_client_learns_of_it_over_the_socket(stack):
    http, fake, backend, _ = stack
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        r = fake.post("/api/v1/job-queue/jobs", json={
            "service": "image_gen", "model": "default", "idempotency_key": "k1",
            "payload": {"prompt": "a brass lamp", "params": {"number_of_images": 2}, "image_name": "lamp"}})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        job_id = data["job_id"]
        assert data["status"] in ("PENDING", "DONE")
        update = terminal_update(ws, job_id)
        assert update["state"] == "succeeded" and update["service"] == "image_gen"
        snapshot = reply_to(ws, fake.request(ws, "job.get", {"job_id": job_id}))["job"]
    assert snapshot["status"] == "DONE" and snapshot["service"] == "image_gen"
    images = snapshot["result"]["images"]
    assert len(images) == 2 and snapshot["result"]["image_name"] == "lamp"
    assert backend.calls[0][1]["prompt"] == "a brass lamp"
    url = images[0]["url"]
    assert url.startswith("http://127.0.0.1:8787/")
    got = http.get(url)                                  # the client fetches it with plain urllib: no bearer
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert http.get(url.rsplit("/", 2)[0] + "/not-the-token/1.png").status_code == 404


def test_a_failing_backend_fails_the_job_with_its_error(settings, provider):
    app = create_app(settings, provider=provider, job_backends={"image_gen": FakeImages(fail=True)})
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            job_id = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default",
                                                              "payload": {"prompt": "x"}}).json()["data"]["job_id"]
            update = terminal_update(ws, job_id)
            assert update["state"] == "failed" and "down" in update["error"]
        snap = fake.get(f"/api/v1/job-queue/jobs/{job_id}").json()["data"]
        assert snap["status"] == "FAILED" and "the image model is down" in snap["error"]


def test_the_same_idempotency_key_returns_the_same_job(stack):
    _, fake, _, _ = stack
    body = {"service": "image_gen", "model": "default", "idempotency_key": "same", "payload": {"prompt": "x"}}
    a = fake.post("/api/v1/job-queue/jobs", json=body).json()["data"]["job_id"]
    b = fake.post("/api/v1/job-queue/jobs", json=body).json()["data"]["job_id"]
    assert a == b


def test_an_unknown_service_and_a_missing_prompt_are_refused(stack):
    _, fake, _, _ = stack
    assert fake.post("/api/v1/job-queue/jobs", json={"service": "world_labs", "model": "x", "payload": {}}).status_code == 422
    assert fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default", "payload": {}}).status_code == 422
    assert http_status(fake, "/api/v1/job-queue/jobs/nope") == 404


def http_status(fake, path):
    return fake.get(path).status_code


def test_cancel_and_sync(stack):
    _, fake, _, _ = stack
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        job_id = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default",
                                                          "payload": {"prompt": "x"}}).json()["data"]["job_id"]
        terminal_update(ws, job_id)
        assert fake.delete(f"/api/v1/job-queue/jobs/{job_id}").status_code == 200
        jobs = reply_to(ws, fake.request(ws, "job.sync", {}))["jobs"]
    assert [j["job_id"] for j in jobs] == [job_id]
    assert fake.get("/api/v1/job-queue/info/image_gen").status_code == 200


def test_the_queue_requires_a_bearer(stack):
    http, _, _, _ = stack
    assert http.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "d", "payload": {"prompt": "x"}}).status_code == 401
    assert http.get("/api/v1/generation-catalog").status_code == 401


def test_the_openrouter_image_backend_makes_one_request_per_image_with_the_references(tmp_path, monkeypatch):
    """The OpenRouter images API, by the shape the imagegen module already uses: one POST per image, input_references as
    data URLs, usage.cost added to the ledger."""
    import base64
    import httpx
    from lampway_server import imagegen
    from lampway_server.agent.providers import openrouter as OR

    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}],
                                         "usage": {"cost": 0.05}})

    monkeypatch.setattr(imagegen, "openrouter_transport", httpx.MockTransport(handler))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "a" * 40)
    monkeypatch.setenv("LAMPWAY_SPEND_LOG", str(tmp_path / "spend.jsonl"))
    monkeypatch.setenv("LAMPWAY_OPENROUTER_BUDGET_USD", "1")
    out = imagegen.openrouter_image_backend("default", {"prompt": "a lamp", "params": {"number_of_images": 2},
                                                        "reference_images_b64": [base64.b64encode(PNG).decode()]})
    assert len(out.images) == 2 and out.images[0][0] == PNG and out.images[0][1] == "image/png"
    assert len(seen) == 2 and seen[0]["prompt"] == "a lamp" and seen[0]["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Authorization" not in json.dumps(seen)
    assert (tmp_path / "spend.jsonl").exists()
