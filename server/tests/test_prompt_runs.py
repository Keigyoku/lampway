"""The run log and its use: every image or video job stores the rendered prompt; a template + variables on a job payload is rendered into the prompt; the
captain's 1-5 rating, gate measurements, per-version stats and A/B (variant_of) are recorded; the REST routes and the agent tools expose it all."""

import json
import time

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.prompts.runlog import RunLog

from .fake_client import FakeMixarClient
from .test_job_queue import FakeImages


def test_the_run_log_records_rates_and_aggregates_by_template_version(tmp_path):
    log = RunLog(tmp_path / "runs.jsonl")
    log.record("j1", prompt="p1", model="m", template="anim-walk-side-track@1.0.0", variables={"cadence_spm": 110}, cost=0.30, output="a.mp4", service="video_gen")
    log.record("j2", prompt="p2", model="m", template="anim-walk-side-track@1.0.0", cost=0.10, service="video_gen")
    log.record("j3", prompt="p3", model="m", template="anim-walk-side-track@1.1.0", cost=0.20, service="video_gen", variant_of="anim-walk-side-track@1.0.0")
    log.record("j4", prompt="a raw prompt", model="m", service="image_gen")
    log.rate("j1", 4, "good stride")
    log.rate("j2", 2)
    log.rate("j1", 5, "better on second look")
    log.gates("j1", {"tracking": True, "root_speed_error": 0.03})
    log.gates("j2", {"tracking": False, "root_speed_error": 0.2})
    stats = {s["template"]: s for s in log.stats()}
    s10 = stats["anim-walk-side-track@1.0.0"]
    assert s10["runs"] == 2 and s10["rated"] == 2 and s10["mean_rating"] == 3.5 and s10["mean_cost"] == pytest.approx(0.2)
    assert s10["gates"]["tracking"] == {"n": 2, "pass_rate": 0.5} and s10["gates"]["root_speed_error"]["mean"] == pytest.approx(0.115)
    assert stats["anim-walk-side-track@1.1.0"]["variant_of"] == "anim-walk-side-track@1.0.0" and stats["anim-walk-side-track@1.1.0"]["mean_rating"] is None
    assert "image_gen" not in str(stats), "a raw-prompt job has no template and is not aggregated, but it is recorded"
    assert [r["prompt"] for r in log.runs() if r["job_id"] == "j4"] == ["a raw prompt"]
    assert log.runs("anim-walk-side-track")[0]["rating"] == 5, "the latest rating wins"


def test_a_rating_must_be_1_to_5_for_a_recorded_run(tmp_path):
    log = RunLog(tmp_path / "r.jsonl")
    log.record("j1", prompt="p")
    for bad in (0, 6, 3.5, True, "5"):
        with pytest.raises(ValueError, match="1 to 5"):
            log.rate("j1", bad)
    with pytest.raises(ValueError, match="no recorded run"):
        log.rate("nope", 3)


@pytest.fixture
def stack(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "root"))
    backend = FakeImages()
    app = create_app(settings, provider=provider, job_backends={"image_gen": backend})
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, backend, app


def wait(fake, jid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        snap = fake.get(f"/api/v1/job-queue/jobs/{jid}").json()["data"]
        if snap["state"] in ("succeeded", "failed", "cancelled"):
            return snap
        time.sleep(0.02)
    raise AssertionError("job never finished")


def test_a_template_and_variables_on_a_job_are_rendered_stored_and_logged(stack):
    fake, backend, app = stack
    r = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default", "payload": {
        "template": {"id": "seamless-tile", "variables": {"material": "blue linen"}}, "params": {"number_of_images": 1}}})
    jid = r.json()["data"]["job_id"]
    snap = wait(fake, jid)
    assert snap["state"] == "succeeded"
    sent = backend.calls[0][1]["prompt"]
    assert "blue linen" in sent and sent.startswith("A seamless tileable texture")
    assert snap["result"]["prompt"] == sent and snap["result"]["template"] == "seamless-tile@1.0.0"
    rows = app.state.prompts.runlog.runs()
    assert rows[-1]["job_id"] == jid and rows[-1]["prompt"] == sent and rows[-1]["template"] == "seamless-tile@1.0.0" and rows[-1]["variables"]["material"] == "blue linen"


def test_a_raw_prompt_job_stores_its_prompt_too(stack):
    fake, backend, app = stack
    jid = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default", "payload": {"prompt": "a brass lamp", "params": {"number_of_images": 1}}}).json()["data"]["job_id"]
    snap = wait(fake, jid)
    assert snap["result"]["prompt"] == "a brass lamp"
    assert app.state.prompts.runlog.runs()[-1]["prompt"] == "a brass lamp" and app.state.prompts.runlog.runs()[-1]["template"] is None


def test_a_bad_template_or_variable_is_refused_at_submit_with_the_reason(stack):
    fake, *_ = stack
    for payload in ({"template": {"id": "nope"}}, {"template": {"id": "seamless-tile", "variables": {"nonsense": 1}}}):
        r = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default", "payload": payload})
        assert r.status_code == 422, r.text


def test_the_routes_list_get_render_save_rate_and_stats(stack):
    fake, backend, app = stack
    listing = fake.get("/app/prompts").json()
    assert len(listing["templates"]) >= 16 and {"id", "version", "title", "media", "scope"} <= set(listing["templates"][0])
    got = fake.get("/app/prompts/anim-walk-side-track").json()
    assert got["version"] == "1.0.0" and "subject" in got["body"] and got["versions"] == ["1.0.0"]
    assert fake.get("/app/prompts/nope").status_code == 404
    out = fake.post("/app/prompts/render", json={"id": "anim-walk-side-track", "variables": {"cadence_spm": 120, "direction": "left"}, "model": "bytedance/seedance-1-5-pro"}).json()
    assert "120 steps per minute" in out["prompt"] and "trucks left" in out["prompt"] and "the start image" in out["prompt"] and out["params"]["model"] == "bytedance/seedance-1-5-pro"
    assert fake.post("/app/prompts/render", json={"id": "anim-walk-side-track", "variables": {"cadence_spm": 999}}).status_code == 400
    mine = dict(got, version="1.0.1", title="My walk")
    for k in ("scope", "file", "versions"):
        mine.pop(k, None)
    saved = fake.put("/app/prompts", json={"template": mine})
    assert saved.status_code == 200, saved.text
    assert fake.get("/app/prompts/anim-walk-side-track").json()["title"] == "My walk" and fake.get("/app/prompts/anim-walk-side-track").json()["scope"] == "user"
    assert fake.put("/app/prompts", json={"template": mine}).status_code == 400, "a version is never overwritten"
    old = fake.get("/app/prompts/anim-walk-side-track", params={"version": "1.0.0"}).json()
    assert old["title"] != "My walk"
    jid = fake.post("/api/v1/job-queue/jobs", json={"service": "image_gen", "model": "default", "payload": {"prompt": "x", "params": {"number_of_images": 1}}}).json()["data"]["job_id"]
    wait(fake, jid)
    assert fake.post("/app/prompts/rate", json={"job_id": jid, "rating": 4, "note": "ok"}).status_code == 200
    assert fake.post("/app/prompts/rate", json={"job_id": jid, "rating": 9}).status_code == 400
    assert fake.post(f"/app/prompts/runs/{jid}/gates", json={"gates": {"silhouette_iou": 0.97}}).status_code == 200
    assert fake.get("/app/prompts/runs").json()["runs"][-1]["rating"] == 4
    assert isinstance(fake.get("/app/prompts/stats").json()["stats"], list)


def test_the_prompt_routes_need_a_token(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        for method, path in (("get", "/app/prompts"), ("get", "/app/prompts/x"), ("post", "/app/prompts/render"), ("put", "/app/prompts"), ("post", "/app/prompts/rate"), ("get", "/app/prompts/stats")):
            assert getattr(http, method)(path).status_code == 401, path
