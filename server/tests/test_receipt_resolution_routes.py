"""A submission_unknown job has a way out (fix request 4): the user acknowledges it (it did not run) or links it to the provider's job id, through REST routes the
Client's spend surface calls. The user only: there is no agent or MCP tool for it, and a request that says it comes from an agent is refused."""
import pytest
from starlette.testclient import TestClient

from lampway_server import jobreceipts as JR
from lampway_server.agent.tools import TOOLS
from lampway_server.app import create_app
from lampway_server.mcp import offered_tools

from .fake_client import FakeMixarClient


@pytest.fixture
def world(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "proj"))
    receipts = JR.JobReceipts(tmp_path / "proj")
    unknown = []
    for i in range(3):
        r, _ = receipts.create("openrouter", "m", {"prompt": f"p{i}"}, f"k{i}", "user", job_id=f"job-{i}")
        receipts.mark_pending(r)
        unknown.append(r["key"])
    receipts.reconcile({})                                                     # a restart: pending -> submission_unknown
    done, _ = receipts.create("openrouter", "m", {"prompt": "fine"}, "k-done", "user", job_id="job-done")
    app = create_app(settings, provider=provider, job_receipts=receipts)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake.rest_headers(), receipts, unknown, done["key"]


def test_the_routes_need_the_users_bearer(world):
    http, h, receipts, unknown, _ = world
    assert http.get("/app/receipts").status_code == 401
    assert http.post(f"/app/receipts/{unknown[0]}/acknowledge").status_code == 401
    assert http.post(f"/app/receipts/{unknown[0]}/link", json={"provider_job_id": "x"}).status_code == 401


def test_the_list_shows_the_unknown_jobs_without_secrets(world):
    http, h, receipts, unknown, _ = world
    rows = http.get("/app/receipts?state=submission_unknown", headers=h).json()["receipts"]
    assert sorted(r["key"] for r in rows) == sorted(unknown) and all(r["state"] == "submission_unknown" for r in rows)
    assert all("actions" in r and set(r["actions"]) == {"acknowledge", "link"} for r in rows)


def test_acknowledge_closes_it_as_did_not_run_and_the_queue_shows_it(world):
    http, h, receipts, unknown, _ = world
    r = http.post(f"/app/receipts/{unknown[0]}/acknowledge", headers=h, json={})
    assert r.status_code == 200 and r.json()["receipt"]["state"] == "abandoned"
    assert receipts.get(unknown[0])["state"] == "abandoned" and receipts.get(unknown[0])["history"][-1]["note"].startswith("acknowledged by the user")
    snap = http.get("/api/v1/job-queue/jobs/job-0", headers=h)
    assert snap.status_code == 200 and snap.json()["data"]["status"] in ("cancelled", "CANCELLED")


def test_link_records_the_providers_id_and_needs_one(world):
    http, h, receipts, unknown, _ = world
    assert http.post(f"/app/receipts/{unknown[1]}/link", headers=h, json={}).status_code == 422
    r = http.post(f"/app/receipts/{unknown[1]}/link", headers=h, json={"provider_job_id": "gen-123"})
    assert r.status_code == 200 and receipts.get(unknown[1])["state"] == "submitted" and receipts.get(unknown[1])["provider_job_id"] == "gen-123"


def test_only_a_submission_unknown_job_can_be_resolved_and_a_missing_key_is_404(world):
    http, h, receipts, unknown, done = world
    assert http.post(f"/app/receipts/{done}/acknowledge", headers=h, json={}).status_code == 409
    assert http.post("/app/receipts/nope/acknowledge", headers=h, json={}).status_code == 404


def test_a_request_that_says_it_is_an_agent_is_refused(world):
    http, h, receipts, unknown, _ = world
    for kw in ({"json": {"by": "agent"}}, {"json": {}, "headers": {**h, "X-Lampway-Origin": "agent"}}):
        r = http.post(f"/app/receipts/{unknown[2]}/acknowledge", **({"headers": h} | kw))
        assert r.status_code == 403 and "the user" in r.json()["detail"]
    assert receipts.get(unknown[2])["state"] == "submission_unknown"


def test_no_agent_or_mcp_tool_can_resolve_a_receipt():
    names = {t.name for t in TOOLS} | {t.name for t in offered_tools()}
    assert not [n for n in names if "acknowledge" in n or "receipt" in n and ("link" in n or "resolve" in n)]
