"""Endpoint backends (RunPod, Modal, fal) behind the compute wrapper, against FAKE provider transports only. Every path and field is [UNVERIFIED] and frozen here; the live legs are needs_key skips."""
import base64
import json

import httpx
import pytest

from lampway_server import egress as E
from lampway_server import jobreceipts as JR
from lampway_server.compute import backend as BK
from lampway_server.compute import endpoint as EP
from lampway_server.compute import fake as FK
from lampway_server.compute import prefs as PF
from lampway_server.compute import recipes as RC
from lampway_server.compute import runner as R
from lampway_server.ledger import Ledger

RC.RECIPES["gpu_probe"] = BK.Recipe("gpu_probe", "1.0.0", hardware_gpu="A10", setup_seconds_max=30, outputs=("result.json",), no_payload_logging=True, entry="true")
CFG = {"base_url": "https://ep.example", "rate_usd_per_s": 0.0003, "exec_timeout_s": 60, "idle_timeout_s": 5, "max_workers": 1, "kind": "web"}
KEYS = {"runpod": {"RUNPOD_API_KEY": "rp-SECRETKEY0123456789"}, "modal": {"MODAL_TOKEN_ID": "ak-id12345", "MODAL_TOKEN_SECRET": "as-SECRET0123456789"}, "fal": {"FAL_KEY": "Key fal-SECRETKEY0123456789"}}
HOSTS = {"runpod": "https://api.runpod.ai/v2/ep1", "modal": "https://lampway--gemx.modal.run", "fal": "https://queue.fal.run/fal-ai/gemx"}


class FakeProvider:
    def __init__(self, shape, clock):
        self.shape, self.clock, self.requests, self.jobs = shape, clock, [], {}
        self.min_workers, self.max_workers, self.digest = 0, 1, "sha256:abc"
        self.drop_accept = False
        self.status_calls = 0
        self.run_seconds = 7

    def handler(self, request: httpx.Request):
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path.endswith("/config"):
            return httpx.Response(200, json={"min_workers": self.min_workers, "max_workers": self.max_workers, "image_digest": self.digest})
        if request.method == "POST" and path.endswith(("/run", "/jobs")) or (self.shape == "fal" and request.method == "POST" and path.endswith("/gemx")):
            body = json.loads(request.content)
            if self.drop_accept:
                raise httpx.ReadTimeout("no answer")
            jid = f"j{len(self.jobs) + 1}"
            self.jobs[jid] = {"body": body, "start": self.clock.now()}
            return httpx.Response(200, json={("request_id" if self.shape == "fal" else "id" if self.shape == "runpod" else "job_id"): jid})
        if request.method == "GET" and "/status" in path or (request.method == "GET" and "/jobs/" in path):
            jid = path.split("/")[-2] if path.endswith("/status") else path.rsplit("/", 1)[1]
            j = self.jobs[jid]
            done = self.clock.now() - j["start"] >= self.run_seconds
            doc = {"runpod": {"status": "COMPLETED" if done else "IN_PROGRESS"}, "modal": {"status": "done" if done else "running"}, "fal": {"status": "COMPLETED" if done else "IN_PROGRESS"}}[self.shape]
            if done:
                doc["output"] = {"files": {"result.json": base64.b64encode(b'{"ok": true}').decode()}}
            return httpx.Response(200, json=doc)
        if "cancel" in path:
            return httpx.Response(200, json={})
        return httpx.Response(404)


class Env:
    def __init__(self, tmp_path, shape, monkeypatch, cfg=None, recipe="gpu_probe", content="synthetic"):
        for k, v in KEYS[shape].items():
            monkeypatch.setenv(k, v)
        self.root = tmp_path / "proj"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "in.png").write_bytes(b"\x89PNG" + b"\x00" * 12)
        self.clock = FK.FakeClock(1_700_000_000.0)
        self.prov = FakeProvider(shape, self.clock)
        c = dict(CFG, base_url=HOSTS[shape], **(cfg or {}))
        self.be = EP.EndpointBackend(shape, {recipe: c}, transport=httpx.MockTransport(self.prov.handler))
        self.ledger = Ledger(self.root / "ledger" / "runs.jsonl")
        self.receipts = JR.JobReceipts(self.root, ledger=self.ledger)
        self.prefs = PF.Prefs(tmp_path / "state" / "p.json")
        self.prefs.update({"backends": [shape], "private_backends": [shape], "spend": {"job_cap": 1.0, "day_cap": 5.0, "click": "above", "above": 100.0}})
        self.runner = R.ComputeRunner(self.root, self.receipts, self.ledger, self.prefs, {shape: self.be}, clock=self.clock.now, sleep=self.clock.sleep, poll_s=5.0)
        self.shape, self.recipe, self.content = shape, recipe, content

    def job(self, **kw):
        j = {"recipe": self.recipe, "inputs": [{"path": "in.png", "content_class": self.content}], "backend": self.shape, "max_seconds": 120, "max_usd": 0.5, "origin": "user"}
        j.update(kw)
        return j

    def posts(self):
        return [r for r in self.prov.requests if r.method == "POST" and "cancel" not in r.url.path]


@pytest.mark.parametrize("shape", ["runpod", "modal", "fal"])
def test_each_shape_runs_a_request_end_to_end_and_every_request_carries_an_execution_timeout(tmp_path, monkeypatch, shape):
    e = Env(tmp_path, shape, monkeypatch, cfg={"kind": "web"})
    out = e.runner.submit(e.job())
    assert out["state"] == "downloaded" and out["teardown"] == "verified"
    body = json.loads(e.posts()[0].content)
    assert (body["policy"]["executionTimeout"] if shape == "runpod" else body.get("timeout_s", body.get("timeout"))) in (60, 60000)       # min(max_seconds 120, exec_timeout 60)
    assert json.loads(open(e.receipts._dir(f"compute:{shape}", out["key"]) / "assets" / "result.json").read()) == {"ok": True}


@pytest.mark.parametrize("shape", ["runpod", "modal"])
def test_an_endpoint_with_min_workers_above_zero_or_a_wrong_image_is_refused_before_any_request(tmp_path, monkeypatch, shape):
    e = Env(tmp_path, shape, monkeypatch)
    e.prov.min_workers = 1
    with pytest.raises(JR.NotSent, match="bills while idle"):
        e.runner.submit(e.job())
    e.prov.min_workers, e.prov.digest = 0, "sha256:other"
    e.be.endpoints[e.recipe]["image_digest"] = "sha256:abc"
    with pytest.raises(JR.NotSent, match="image digest"):
        e.runner.submit(e.job(idempotency_key="b"))
    assert e.posts() == []


def test_the_upper_bound_includes_setup_exec_and_idle_and_the_cap_refuses_before_the_request(tmp_path, monkeypatch):
    e = Env(tmp_path, "runpod", monkeypatch)
    q = e.runner.plan(e.job())["plan"]["quote"]
    assert q["upper_bound_usd"] == pytest.approx(0.0003 * (30 + 60 + 5)) and q["ttl_seconds"] == 60 + 30 + 5
    e.prefs.update({"spend": {"job_cap": 0.01, "day_cap": 5.0, "click": "above", "above": 100.0}})
    with pytest.raises(R.Refused, match="over the cap"):
        e.runner.submit(e.job())
    assert e.prov.requests == []


def test_a_lost_accept_stays_unknown_and_is_never_resent(tmp_path, monkeypatch):
    e = Env(tmp_path, "runpod", monkeypatch)
    e.prov.drop_accept = True
    out = e.runner.submit(e.job())
    assert out["state"] == "provider_error" and "outcome is unknown" in out["error"] and "not resent" in out["error"]
    assert len(e.posts()) == 1
    e.prov.drop_accept = False
    e.runner.reconcile()
    assert len(e.posts()) == 1                                                                  # reconcile never resends


@pytest.mark.parametrize("shape", ["runpod", "modal", "fal"])
def test_a_cpu_recipe_is_refused_on_a_gpu_backend_and_a_missing_key_is_needs_key(tmp_path, monkeypatch, shape):
    e = Env(tmp_path, shape, monkeypatch, recipe="probe")
    if shape != "fal":
        with pytest.raises(R.Refused, match="CPU recipe: use Boat or run locally"):
            e.runner.plan(e.job())
    for k in KEYS[shape]:
        monkeypatch.delenv(k)
    e2 = Env(tmp_path / "nokey", shape, monkeypatch)
    for k in KEYS[shape]:
        monkeypatch.delenv(k)
    with pytest.raises(JR.NotSent, match="needs_key"):
        e2.runner.submit(e2.job())
    assert e2.prov.requests == [] or all(r.method == "GET" for r in e2.prov.requests)


def test_private_content_runpod_unknown_modal_function_refused_and_modal_web_allowed_unless_payloads_are_logged(tmp_path, monkeypatch):
    e = Env(tmp_path / "rp", "runpod", monkeypatch, content="private")
    with pytest.raises(R.Refused, match="this input is private"):
        e.runner.plan(e.job())
    m = Env(tmp_path / "mf", "modal", monkeypatch, cfg={"kind": "function"}, content="private")
    with pytest.raises(R.Refused, match="this input is private"):
        m.runner.plan(m.job())
    w = Env(tmp_path / "mw", "modal", monkeypatch, cfg={"kind": "web"}, content="private")
    assert w.runner.plan(w.job())["plan"]["privacy"]["conditions_met"] is True
    w.be.endpoints[w.recipe]["payload_logged"] = True
    with pytest.raises(R.Refused, match="this input is private"):
        w.runner.plan(w.job())


def test_the_idle_report_names_an_endpoint_that_bills_while_idle_and_edits_nothing(tmp_path, monkeypatch):
    e = Env(tmp_path, "runpod", monkeypatch)
    e.prov.min_workers = 2
    rep = e.be.idle_report()
    assert rep and "bills while idle" in rep[0]["reason"] and all(r.method == "GET" for r in e.prov.requests)


def test_keys_never_reach_receipts_ledger_or_the_egress_log_and_the_hook_gates_the_hosts(tmp_path, monkeypatch):
    m = E.Egress(tmp_path / "eg")
    E.install()
    E.set_active(m)
    e = Env(tmp_path, "runpod", monkeypatch)
    with pytest.raises(E.EgressRefused, match="compute:runpod is off"):
        e.runner.submit(e.job())
    assert e.prov.requests == []
    m.set_route("compute:runpod", True)
    assert e.runner.submit(e.job(idempotency_key="optin"))["state"] == "downloaded"
    blob = "\n".join(p.read_text(errors="replace") for p in list(e.root.rglob("*")) + list((tmp_path / "eg").rglob("*")) if p.is_file())
    assert "SECRETKEY0123456789" not in blob and [r for r in m.log() if r["event"] == "send" and r["route"] == "compute:runpod" and r["content_class"] == "synthetic"]
