"""The generation job-service registry (specs/mixar_docs/job_services.md): the Client has 21 job types, this server backs the ones that register. A catalog row,
a files result, a spend gate that only the user's click opens, a refusal for a key the Client does not send, and a read-only tool that lists what is
backed and what is not."""

import time

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.jobqueue import FilesOutput
from lampway_server.services import WIRE_KEYS, ServiceRegistry

from .fake_client import FakeMixarClient

GLB = b"glTF" + b"\x00" * 16


class Backend:
    def __init__(self):
        self.calls = []

    def __call__(self, model, payload):
        self.calls.append((model, payload))
        return FilesOutput(files=[(GLB, "model/gltf-binary", "mesh.glb")], kind="GLB", extra={"provider": "fake"})


ROW = {"label": "Retopology", "surface": "moodboard", "models": [{"slug": "quad", "label": "Quad remesh", "is_default": True, "max_reference_images": 0, "parameters": {}}]}


@pytest.fixture
def stack(settings, provider, monkeypatch, tmp_path):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "root"))
    reg, backend = ServiceRegistry(), Backend()
    reg.register("retopology", backend, ROW)
    spent = Backend()
    reg.register("tripo_rig", spent, dict(ROW, label="Rig"), spend=True, confirm_price=lambda payload: 25)
    app = create_app(settings, provider=provider, job_backends={}, job_services=reg)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, reg, backend, spent, app


def wait(fake, jid, states=("succeeded", "failed", "cancelled"), timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        snap = fake.get(f"/api/v1/job-queue/jobs/{jid}").json()["data"]
        if snap["state"] in states:
            return snap
        time.sleep(0.05)
    raise AssertionError(f"job {jid} never reached {states}: {snap}")


def submit(fake, service, payload=None):
    r = fake.post("/api/v1/job-queue/jobs", json={"service": service, "model": "quad", "payload": payload or {}})
    assert r.status_code == 200, r.text
    return r.json()["data"]["job_id"]


def test_the_catalog_lists_every_registered_service_and_drops_one_that_is_unregistered(stack):
    fake, reg, *_ = stack
    caps = {c["key"]: c for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"]}
    assert {"retopology", "tripo_rig"} <= set(caps)
    svc = caps["retopology"]["services"][0]
    assert svc["key"] == "retopology" and svc["surface"] == "moodboard" and svc["models"][0]["slug"] == "quad" and caps["retopology"]["label"] == "Retopology"
    reg.unregister("retopology")
    assert "retopology" not in {c["key"] for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"]}


def test_a_files_result_serialises_result_files_with_their_type_and_a_url_that_resolves(stack):
    fake, reg, backend, *_ = stack
    snap = wait(fake, submit(fake, "retopology", {"object": "x"}))
    assert snap["state"] == "succeeded", snap
    f = snap["result"]["result_files"][0]
    assert f["type"] == "GLB" and snap["result"]["provider"] == "fake" and backend.calls
    got = fake.http.get(f["url"].replace("http://127.0.0.1:8787", ""))
    assert got.status_code == 200 and got.content == GLB, "the downloader sends no bearer: the URL itself is the capability"


def test_a_spend_service_waits_for_the_captains_confirm_and_runs_once(stack):
    fake, reg, backend, spent, app = stack
    jid = submit(fake, "tripo_rig")
    snap = wait(fake, jid, states=("pending",))
    time.sleep(0.2)
    snap = fake.get(f"/api/v1/job-queue/jobs/{jid}").json()["data"]
    assert snap["state"] == "pending" and "25" in snap["user_message"] and "Studios" in snap["user_message"] and spent.calls == [], "the backend is not called before the click"
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert ap["price"] == 25 and ap["studio"] == "tripo_rig"
    assert fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 1}).status_code == 409 and spent.calls == []
    assert fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 25}).status_code == 200
    assert wait(fake, jid)["state"] == "succeeded" and len(spent.calls) == 1
    assert fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 25}).status_code == 409, "one shot"
    assert len(spent.calls) == 1


def test_rejecting_a_spend_cancels_the_job_without_calling_the_backend(stack):
    fake, reg, backend, spent, app = stack
    jid = submit(fake, "tripo_rig")
    time.sleep(0.3)
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert fake.post(f"/app/studio/approvals/{ap['id']}/reject").status_code == 200
    assert wait(fake, jid)["state"] == "cancelled" and spent.calls == []


def test_registration_refuses_a_key_the_client_never_sends_and_a_spend_without_a_price():
    reg = ServiceRegistry()
    with pytest.raises(ValueError, match="not a Lampway client job type") as e:
        reg.register("my_service", Backend(), ROW)
    assert "retopology" in str(e.value) and len(WIRE_KEYS) == 21
    with pytest.raises(ValueError, match="confirm_price"):
        reg.register("tripo_rig", Backend(), ROW, spend=True)


def test_an_unbacked_service_is_refused_with_the_next_step(stack):
    fake, *_ = stack
    r = fake.post("/api/v1/job-queue/jobs", json={"service": "model_3d", "model": "x", "payload": {}})
    assert r.status_code == 422 and "register a backend" in r.text


def test_the_job_services_tool_lists_what_is_backed_and_what_is_not_and_is_read_only(stack):
    fake, reg, backend, spent, app = stack
    rep = app.state.jobs.service_report()
    by = {s["key"]: s for s in rep["services"]}
    assert by["retopology"]["available"] is True and by["retopology"]["spend"] is False and by["tripo_rig"]["spend"] is True
    assert "model_3d" in rep["unbacked"] and "retopology" not in rep["unbacked"] and set(by) | set(rep["unbacked"]) == set(WIRE_KEYS)
    assert "tok" not in str(rep).lower() and "secret" not in str(rep).lower()
    from lampway_server.agent import tools as T
    assert "lampway_job_services" in {t.name for t in T.TOOLS}


def test_the_agent_tool_returns_the_report_as_json(stack):
    import json
    from lampway_server.agent import ledger_tools as LGT
    fake, reg, backend, spent, app = stack
    out = json.loads(LGT.job_services(app.state.jobs))
    assert {s["key"] for s in out["services"]} == {"retopology", "tripo_rig"} and "model_3d" in out["unbacked"]
    assert json.loads(LGT.job_services(None)) == {"services": [], "unbacked": []}
    assert app.state.agent.jobs is app.state.jobs, "the agent hub reads the same queue the Client submits to"
