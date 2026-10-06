"""compute_backend (specs/cloud/compute_backend.md): one provider-agnostic seam to rent compute, with receipts BEFORE any paid call, caps, a privacy gate, egress consent and a crash-safe reconcile.
Every test runs against the in-process FakeBackend (fault knobs, fake clock): no network, no spend."""
import json
import os
import threading

import pytest

from lampway_server import egress as E
from lampway_server import jobreceipts as JR
from lampway_server.compute import backend as BK
from lampway_server.compute import fake as FK
from lampway_server.compute import prefs as PF
from lampway_server.compute import runner as R
from lampway_server.ledger import Ledger

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class Env:
    def __init__(self, tmp_path, **fake_kw):
        self.root = tmp_path / "proj"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "in.png").write_bytes(PNG)
        self.clock = FK.FakeClock(start=1_700_000_000.0)
        self.fake = FK.FakeBackend(self.clock, **fake_kw)
        self.ledger = Ledger(self.root / "ledger" / "runs.jsonl")
        self.receipts = JR.JobReceipts(self.root, ledger=self.ledger)
        self.prefs = PF.Prefs(tmp_path / "state" / "compute_prefs.json")
        self.prefs.update({"backends": ["fake"], "private_backends": ["fake"], "spend": {"job_cap": 1.0, "day_cap": 5.0, "click": "above", "above": 0.25}})
        self.build()

    def build(self):
        self.runner = R.ComputeRunner(self.root, self.receipts, self.ledger, self.prefs, {"fake": self.fake}, clock=self.clock.now, sleep=self.clock.sleep, poll_s=5.0, watchdog_s=15.0)

    def restart(self):
        """A new process over the same folders: the receipts and prefs survive, the runner's memory does not."""
        self.receipts = JR.JobReceipts(self.root, ledger=self.ledger)
        self.build()

    def job(self, **kw):
        j = {"recipe": "probe", "inputs": [{"path": "in.png", "content_class": "synthetic"}], "params": {}, "backend": "fake", "max_seconds": 60, "max_usd": 0.5, "origin": "user"}
        j.update(kw)
        return j


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def approve(env, job):
    p = env.runner.plan(job)["plan"]
    return env.runner.approve(p["plan_id"], by="user")["approval_id"] if p["needs_click"] else None


def calls(env, verb):
    return [c for c in env.fake.calls if c[0] == verb]


def test_the_receipt_is_on_disk_before_the_first_byte_goes_to_the_provider(env):
    seen = {}
    def hook():
        seen["receipts"] = [r["state"] for r in env.receipts.list()]
    env.fake.provision_hook = hook
    out = env.runner.submit(env.job(), approval_id=approve(env, env.job()))
    assert seen["receipts"] == ["submission_pending"] and out["state"] == "downloaded"


def test_a_crash_between_pending_and_submitted_becomes_unknown_and_never_reprovisions(env):
    def die():
        raise SystemExit("killed")
    env.fake.provision_hook = die
    with pytest.raises(SystemExit):
        env.runner.submit(env.job(), approval_id=approve(env, env.job()))
    assert [r["state"] for r in env.receipts.list()] == ["submission_pending"]
    env.fake.provision_hook = None
    env.restart()
    rep = env.runner.reconcile()
    [r] = env.receipts.list()
    assert r["state"] == "submission_unknown" and rep["unknown"] == [r["key"]]
    again = env.runner.submit(env.job(), approval_id=approve(env, env.job()))
    assert again["already_exists"] is True and len(calls(env, "provision")) == 1


def test_exclusive_create_under_race_provisions_once(env):
    j = env.job(idempotency_key="race-1")
    ap = approve(env, j)
    outs = []
    def go():
        outs.append(env.runner.submit(dict(j), approval_id=ap))
    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(calls(env, "provision")) == 1 and sum(1 for o in outs if not o.get("already_exists")) == 1


def test_a_lost_response_is_found_by_reconcile_via_the_key_in_the_resource_name(tmp_path):
    e = Env(tmp_path, drop_response_after_create=True)
    with pytest.raises(BK.Unknown):
        e.runner.submit(e.job(), approval_id=approve(e, e.job()))
    [r] = e.receipts.list()
    assert r["state"] == "submission_unknown"
    e.fake.drop_response_after_create = False
    rep = e.runner.reconcile()
    assert rep["resumed"] or rep["torn_down"] or rep["completed"], rep
    [r] = e.receipts.list()
    assert r["state"] == "downloaded" and len(calls(e, "provision")) == 1
    assert e.runner.billing_now() == []


def test_two_matching_resources_leave_the_receipt_unknown(tmp_path):
    e = Env(tmp_path, drop_response_after_create=True)
    with pytest.raises(BK.Unknown):
        e.runner.submit(e.job(), approval_id=approve(e, e.job()))
    key = e.receipts.list()[0]["key"]
    e.fake.add_resource(name=e.fake.prefix + key[:8] + "-dup", key=key)
    e.fake.drop_response_after_create = False
    rep = e.runner.reconcile()
    assert e.receipts.list()[0]["state"] == "submission_unknown" and len(calls(e, "run")) == 0 and len(calls(e, "teardown")) == 0 and rep["waiting"]


def test_an_orphan_is_reported_and_left_alone_by_default_and_stop_never_deletes(env):
    ref = env.fake.add_resource(name=env.fake.prefix + "orphan0001", key="f" * 16)
    rep = env.runner.reconcile()
    assert [o["ref_suffix"] for o in rep["orphans"]] == [ref[-6:]] and calls(env, "teardown") == []
    env.prefs.update({"orphan_action": "stop"})
    env.runner.reconcile()
    assert [c for c in calls(env, "teardown") if c[2] == "stop"] and not [c for c in calls(env, "teardown") if c[2] == "delete"]


def test_foreign_resources_are_never_touched(env):
    for n in ("captain-box", "other-install-x1", "lampway-OTHER-abcd1234"):
        env.fake.add_resource(name=n, key=None, foreign=True)
    env.prefs.update({"orphan_action": "stop"})
    rep = env.runner.reconcile()
    assert rep["orphans"] == [] and [c for c in env.fake.calls if c[0] in ("teardown", "run", "provision")] == []


def test_a_failed_teardown_stays_in_billing_now_and_is_retried_until_verified(tmp_path):
    e = Env(tmp_path, teardown_fails=True)
    out = e.runner.submit(e.job(), approval_id=approve(e, e.job()))
    assert out["teardown"] == "failed"
    bn = e.runner.billing_now()
    assert len(bn) == 1 and bn[0]["rate_usd_per_s"] > 0 and bn[0]["accrued_usd"] >= 0
    e.fake.teardown_fails = False
    e.clock.advance(120)
    rep = e.runner.reconcile()
    assert e.runner.billing_now() == [] and rep["torn_down"]
    assert e.runner.reconcile()["billing_now"] == []


def test_job_cap_refuses_before_any_provider_call_with_the_boundary_exact(env):
    j = env.job(max_seconds=60)
    q = env.runner.plan(j)["plan"]["quote"]["upper_bound_usd"]
    env.prefs.update({"spend": {"job_cap": q, "day_cap": 5.0, "click": "above", "above": 100.0}})
    assert env.runner.submit(j)["state"] == "downloaded"                                       # upper_bound == cap is allowed
    env.restart()
    env.prefs.update({"spend": {"job_cap": q - 1e-9, "day_cap": 5.0, "click": "above", "above": 100.0}})
    n = len(env.fake.calls)
    with pytest.raises(R.Refused, match="over the cap"):
        env.runner.submit(env.job(max_seconds=60, idempotency_key="other"))
    assert len(env.fake.calls) == n


def test_the_watchdog_tears_down_at_the_cap_and_accrual_never_passes_it_by_more_than_an_interval(tmp_path):
    e = Env(tmp_path, never_finish=True, rate=0.001, actual_factor=3.0)                          # the box bills 3x what the quote assumed: only the meter-aware watchdog can stop it in time
    e.prefs.update({"spend": {"job_cap": 1.0, "day_cap": 50.0, "click": "above", "above": 100.0}})
    out = e.runner.submit(e.job(max_seconds=300, max_usd=0.5))
    assert out["state"] == "provider_error" and "cap" in out["error"]
    accrued = e.fake.accrued_usd(out["ref"])
    assert 0.5 <= accrued <= 0.5 + 0.001 * 3 * 15 + 1e-9 and calls(e, "teardown")


def test_the_day_cap_sums_jobs_and_rolls_over_at_local_midnight(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    import time as T
    T.tzset()
    e = Env(tmp_path, rate=0.01, run_seconds=30)
    e.prefs.update({"spend": {"job_cap": 1.0, "day_cap": 0.5, "click": "above", "above": 100.0}})
    e.clock.set(1_700_000_000.0)                                                                # 22:13 UTC
    e.runner.submit(e.job(max_seconds=30, idempotency_key="a"))
    with pytest.raises(R.Refused, match="would pass today's cap"):
        e.runner.submit(e.job(max_seconds=40, idempotency_key="b"))
    e.clock.set(1_700_000_000.0 + 3 * 3600)                                                     # past local midnight
    assert e.runner.submit(e.job(max_seconds=40, idempotency_key="b"))["state"] == "downloaded"


def test_an_unknown_rate_always_needs_a_click_and_defaults_are_the_captains(env):
    d = PF.Prefs(env.prefs.path.parent / "fresh.json")
    s = d.data["spend"]
    assert (s["job_cap"], s["day_cap"], s["click"], s["above"]) == (1.0, 5.0, "above", 0.25) and d.data["orphan_action"] == "report" and d.data["backends"] == []
    env.prefs.update({"spend": {"job_cap": 1.0, "day_cap": 5.0, "click": "off"}})
    env.fake.rate_basis = "assumed"
    p = env.runner.plan(env.job())["plan"]
    assert p["quote"]["basis"] == "assumed" and p["needs_click"] is True


def test_an_agent_can_only_plan_and_an_approval_for_a_different_price_is_void(env):
    with pytest.raises(R.Refused, match="an agent can plan; the captain confirms in the Client"):
        env.runner.submit(env.job(origin="agent"))
    assert env.fake.calls == [] and env.receipts.list() == []
    p = env.runner.plan(env.job(max_usd=0.5, max_seconds=3000))["plan"]                            # above the $0.25 click threshold
    assert p["needs_click"] is True
    ap = env.runner.approve(p["plan_id"], by="user")["approval_id"]
    with pytest.raises(R.Refused, match="approval"):
        env.runner.submit(env.job(max_usd=0.5, max_seconds=3600), approval_id=ap)                  # a different job, a different price
    with pytest.raises(R.Refused, match="only the user"):
        env.runner.approve(p["plan_id"], by="agent")


def test_private_input_is_refused_on_unknown_retains_and_unmet_conditions_and_unclassified_is_private(tmp_path):
    for cls in ("unknown", "retains"):
        e = Env(tmp_path / cls, privacy_class=cls)
        with pytest.raises(R.Refused, match="this input is private"):
            e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "private"}]), approval_id=None)
        with pytest.raises(R.Refused, match="this input is private"):
            e.runner.submit(e.job(inputs=[{"path": "in.png"}]), approval_id=None)                 # no class = private
        assert e.fake.calls == []
        assert e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "synthetic"}]))["state"] == "downloaded"
    e = Env(tmp_path / "cond", privacy_class="conditional", conditions_met=False)
    with pytest.raises(R.Refused, match="this input is private"):
        e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "private"}]))
    e = Env(tmp_path / "ok", privacy_class="ephemeral_verified")
    e.prefs.update({"private_backends": []})
    with pytest.raises(R.Refused, match="private_backends"):
        e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "private"}]))
    e.prefs.update({"private_backends": ["fake"]})
    assert e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "private"}]))["state"] == "downloaded"


def test_a_provider_timeout_on_provision_is_not_retried_and_a_run_timeout_polls_instead_of_rerunning(tmp_path):
    e = Env(tmp_path, provision_timeout=True)
    with pytest.raises(BK.Unknown):
        e.runner.submit(e.job())
    assert len(calls(e, "provision")) == 1 and e.receipts.list()[0]["state"] == "submission_unknown"
    e2 = Env(tmp_path / "run", run_timeout=True)
    assert e2.runner.submit(e2.job())["state"] == "downloaded" and len(calls(e2, "run")) == 1


def test_outputs_are_fetched_and_verified_before_a_destructive_teardown(tmp_path):
    e = Env(tmp_path, stop_erases=True)
    e.runner.submit(e.job(inputs=[{"path": "in.png", "content_class": "private"}]))
    order = [c[0] for c in e.fake.calls if c[0] in ("fetch", "teardown")]
    assert order.index("fetch") < order.index("teardown")
    e2 = Env(tmp_path / "missing", missing_output=True)
    out = e2.runner.submit(e2.job())
    assert out["state"] == "provider_error" and "result.json" in out["error"] and calls(e2, "teardown")          # a missing output fails the job BEFORE teardown, and teardown still happens


def test_restart_mid_run_resumes_polls_fetches_once_and_tears_down_once(tmp_path):
    e = Env(tmp_path, run_seconds=30)
    class Boom(BaseException):
        pass
    n = {"i": 0}
    def sleeper(s):
        n["i"] += 1
        if n["i"] == 2:
            raise Boom()
        e.clock.sleep(s)
    e.runner = R.ComputeRunner(e.root, e.receipts, e.ledger, e.prefs, {"fake": e.fake}, clock=e.clock.now, sleep=sleeper, poll_s=5.0, watchdog_s=15.0)
    with pytest.raises(Boom):
        e.runner.submit(e.job())
    assert e.receipts.list()[0]["state"] in ("submitted", "running")
    e.restart()
    e.clock.advance(60)
    e.runner.reconcile()
    [r] = e.receipts.list()
    assert r["state"] == "downloaded" and len(calls(e, "fetch")) == 1 and len([c for c in calls(e, "teardown")]) == 1
    assert len(e.ledger.rows("job")) == 1 and len(list((e.receipts._dir(r["provider"], r["key"]) / "assets").iterdir())) == 1


def test_secrets_never_reach_receipts_ledger_or_logs(tmp_path, caplog):
    e = Env(tmp_path, error_text="upstream said sk-ABCDEFGH12345678 and https://u:pw@h/x and Bearer abcdefghijklmnop", provision_error=True)
    with caplog.at_level("DEBUG"):
        with pytest.raises(Exception):
            e.runner.submit(e.job())
    blob = caplog.text + "\n".join(p.read_text(errors="replace") for p in e.root.rglob("*") if p.is_file())
    assert "sk-ABCDEFGH12345678" not in blob and "u:pw@" not in blob and "abcdefghijklmnop" not in blob


def test_the_ttl_is_always_set_from_max_seconds_and_the_meter_drift_is_recorded(tmp_path):
    e = Env(tmp_path, meter_factor=1.4, run_seconds=20)
    e.runner.submit(e.job(max_seconds=100))
    assert e.fake.last_ttl == 100 + e.fake.setup_seconds + 60
    row = e.ledger.rows("job")[0]
    assert row["price"]["accrued_usd_estimate"] > 0 and row["price"]["accrued_usd_meter"] > row["price"]["accrued_usd_estimate"] * 1.3 and row["price"]["meter_drift"] is True


def test_reconcile_is_idempotent(tmp_path):
    e = Env(tmp_path, teardown_fails=True)
    e.runner.submit(e.job())
    e.fake.add_resource(name=e.fake.prefix + "orphan0002", key="e" * 16)
    first = e.runner.reconcile()
    n = len(e.fake.calls)
    second = e.runner.reconcile()
    changing = [c for c in e.fake.calls[n:] if c[0] in ("provision", "run", "fetch", "upload")]
    assert changing == [] and second["orphans"] == first["orphans"]


def test_the_wrapper_is_gated_by_egress_consent_and_the_indicator_lights_during_a_call(tmp_path):
    m = E.Egress(tmp_path / "eg")
    E.install()
    E.set_active(m)
    e = Env(tmp_path, egress_route="compute:boat")
    seen = []
    e.fake.provision_hook = lambda: seen.append(m.indicator()["active"])
    with pytest.raises(E.EgressRefused, match="compute:boat is off"):
        e.runner.submit(e.job())
    assert e.fake.calls == [] and e.receipts.list()[0]["state"] == "cancelled"                          # nothing was sent: cancelled, not 'unknown'
    m.set_route("compute:boat", True)
    e.restart()
    e.runner.submit(e.job(idempotency_key="after-optin"))
    assert seen and seen[0] == ["compute:boat"]
    assert [r for r in m.log() if r["event"] == "send" and r["route"] == "compute:boat"]
