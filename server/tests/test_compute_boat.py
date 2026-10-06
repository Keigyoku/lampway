"""The Boat adapter (specs/cloud/compute_backend_boat.md), CLI mode: wraps the installed `boat` binary through an injectable runner. A FakeBoatCli stands in for the binary (shapes modelled on real
`boat list --json` output with every identifier replaced by a placeholder). The captain's own sandboxes are in the fake too: they must never be touched."""
import json
import subprocess

import pytest

from lampway_server import egress as E
from lampway_server import jobreceipts as JR
from lampway_server.compute import backend as BK
from lampway_server.compute import boat as BT
from lampway_server.compute import fake as FK
from lampway_server.compute import prefs as PF
from lampway_server.compute import runner as R
from lampway_server.ledger import Ledger


class FakeBoatCli:
    def __init__(self, clock):
        self.clock, self.calls, self.sandboxes, self.n = clock, [], {}, 0
        self.new_mode = "ok"                    # ok | no_ready | timeout_after_create
        self.start_remaining = 12
        self.run_seconds = 9
        self.envs = []
        for i, st in enumerate(("stopped", "stopped")):
            self.sandboxes[f"bx_foreign{i}"] = {"id": f"bx_foreign{i}", "state": st, "type": "default", "createdAt": "2026-10-03T14:23:42.968Z", "name": "Box <captain's own>", "files": {}, "exit_at": None}

    def verbs(self, name):
        return [c for c in self.calls if c[0] == name]

    def _sb(self, argv):
        return next(a for a in argv if a.startswith("bx_")).split(":")[0]

    def __call__(self, argv, timeout=60, env=None):
        self.envs.append(env)
        assert argv[2:4] == ["--json", "--no-update"], "the real CLI treats flags after a command string as part of the command"
        a = [x for x in argv[1:] if x not in ("--json", "--no-update")]
        verb = a[0]
        self.calls.append((verb, *a[1:]))
        if verb == "limits":
            return 0, json.dumps({"canStart": True, "blockedReason": None, "starts": {"minute": {"limit": 12, "remaining": self.start_remaining}}}), ""
        if verb == "new":
            if self.new_mode == "no_ready":
                return 1, "", "error: no_ready_machine"
            self.n += 1
            sid = f"bx_mine{self.n:03d}"
            self.sandboxes[sid] = {"id": sid, "state": "ready", "type": a[a.index("--type") + 1] if "--type" in a else "default", "createdAt": time_iso(self.clock.now()), "name": "Box <auto>", "files": {}, "exit_at": None, "created": self.clock.now(), "ended": None}
            if self.new_mode == "timeout_after_create":
                raise subprocess.TimeoutExpired(argv, timeout)
            return 0, json.dumps({"event": "sandbox.created", "sandbox": {"id": sid, "state": "ready"}}), ""
        if verb == "list":
            return 0, json.dumps({"pageInfo": {"hasMore": False}, "sandboxes": [{k: v for k, v in s.items() if k in ("id", "state", "type", "createdAt", "name")} for s in self.sandboxes.values()]}), ""
        sid = self._sb(a)
        sb = self.sandboxes.get(sid)
        if sb is None:
            return 1, "", "not_found"
        if verb == "exec":
            script = a[-1]                                           # the real CLI takes ONE shell string (measured); --detach cannot be combined with --timeout
            assert not ("--detach" in a and "--timeout" in a), "the real boat CLI refuses --detach with --timeout"
            assert not script.startswith("-") and "sh -c" not in script
            ok = lambda out="": (0, json.dumps({"exitCode": 0, "stdout": out, "stderr": "", "success": True}), "")  # noqa: E731
            if "--detach" in a:
                sb["exit_at"] = self.clock.now() + self.run_seconds
                return 0, json.dumps({"processId": 1, "pid": 1, "success": True}), ""
            if "/tmp/lw/exit" in script:
                if sb["exit_at"] is not None and self.clock.now() >= sb["exit_at"]:
                    sb["files"]["/tmp/lw/out/result.json"] = b'{"cpus": 4}'
                    return ok("0\n")
                return ok("running\n")
            return ok()
        if verb == "scp":
            src, dst = a[1], a[2]
            if dst.startswith(sid + ":"):
                open(src, "rb").read()
                sb["files"][dst.split(":", 1)[1]] = open(src, "rb").read()
                return 0, "", ""
            data = sb["files"].get(src.split(":", 1)[1])
            if data is None:
                return 1, "", "no such file"
            open(dst, "wb").write(data)
            return 0, "", ""
        if verb == "stop":
            sb["state"], sb["files"], sb["ended"] = "stopped", {}, self.clock.now()
            return 0, json.dumps({"ok": True}), ""
        if verb == "delete":
            self.sandboxes.pop(sid)
            return 0, json.dumps({"operation": {"id": "del_1", "stage": "waiting_for_uploads"}}), ""
        if verb == "usage":
            end = sb["ended"] or self.clock.now()
            sec = end - sb["created"]
            return 0, json.dumps({"seconds": sec, "dollars": sec * 0.00001}), ""
        return 1, "", "unknown verb"


def time_iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Env:
    def __init__(self, tmp_path):
        self.root = tmp_path / "proj"
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "in.png").write_bytes(b"\x89PNG" + b"\x00" * 12)
        self.clock = FK.FakeClock(1_700_000_000.0)
        self.cli = FakeBoatCli(self.clock)
        self.boat = BT.BoatCliBackend(binary="/fake/boat", runner=self.cli, clock=self.clock.now)
        self.ledger = Ledger(self.root / "ledger" / "runs.jsonl")
        self.receipts = JR.JobReceipts(self.root, ledger=self.ledger)
        self.prefs = PF.Prefs(tmp_path / "state" / "p.json")
        self.prefs.update({"backends": ["boat"], "private_backends": ["boat"]})
        self.runner = R.ComputeRunner(self.root, self.receipts, self.ledger, self.prefs, {"boat": self.boat}, clock=self.clock.now, sleep=self.clock.sleep, poll_s=5.0)

    def job(self, **kw):
        j = {"recipe": "probe", "inputs": [{"path": "in.png", "content_class": "synthetic"}], "backend": "boat", "max_seconds": 120, "max_usd": 0.5, "origin": "user"}
        j.update(kw)
        return j


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_a_job_runs_on_a_box_made_with_no_env_no_snapshots_and_a_ttl_and_the_box_is_verified_gone(env):
    out = env.runner.submit(env.job())
    assert out["state"] == "downloaded" and out["teardown"] == "verified" and json.loads((env.root / "jobs" / "compute_boat" / out["key"] / "assets" / "result.json").read_text()) == {"cpus": 4}
    new = env.cli.verbs("new")[0]
    assert "--no-env" in new and "--no-snapshots" in new and new[new.index("--ttl") + 1] == str(120 + 20 + 60) and "--no-auto-stop" not in new and "--fail-fast" in new
    assert [c for c in env.cli.verbs("delete")] and "bx_mine001" not in env.cli.sandboxes
    assert env.runner.billing_now() == []


def test_a_private_job_is_stopped_not_deleted_and_the_output_is_fetched_first(env):
    env.runner.submit(env.job(inputs=[{"path": "in.png", "content_class": "private"}]))
    order = [c[0] for c in env.cli.calls if c[0] in ("scp", "stop", "delete")]
    assert env.cli.verbs("stop") and not env.cli.verbs("delete") and order.index("stop") > max(i for i, v in enumerate(order) if v == "scp")


def test_a_lost_create_response_stays_unknown_lists_candidates_and_never_stops_anything(env):
    env.cli.new_mode = "timeout_after_create"
    with pytest.raises(BK.Unknown):
        env.runner.submit(env.job())
    [r] = env.receipts.list()
    assert r["state"] == "submission_unknown"
    env.prefs.update({"orphan_action": "stop"})
    rep = env.runner.reconcile()
    assert rep["candidates"][r["key"]][0]["id"] == "bx_mine001" and [c for c in env.cli.calls if c[0] in ("stop", "delete", "new")] == [("new", *env.cli.verbs("new")[0][1:])]
    assert env.receipts.list()[0]["state"] == "submission_unknown" and rep["orphans"] == []         # the Boat CLI cannot name its boxes: ownership is the receipt set, never a guess


def test_no_ready_machine_is_not_sent_and_the_start_rate_guard_waits(env):
    env.cli.new_mode = "no_ready"
    with pytest.raises(JR.NotSent):
        env.runner.submit(env.job())
    assert env.receipts.list()[0]["state"] == "provider_error"
    env.cli.new_mode, env.cli.start_remaining = "ok", 0
    with pytest.raises(JR.NotSent, match="start limit"):
        env.runner.submit(env.job(idempotency_key="again"))
    assert len(env.cli.verbs("new")) == 1


def test_the_captains_own_sandboxes_are_never_touched(env):
    env.prefs.update({"orphan_action": "stop"})
    env.runner.submit(env.job())
    env.runner.reconcile()
    assert not [c for c in env.cli.calls if c[0] in ("stop", "delete", "exec", "scp") and any(str(x).startswith("bx_foreign") for x in c)]
    assert "bx_foreign0" in env.cli.sandboxes and env.cli.sandboxes["bx_foreign0"]["state"] == "stopped"


def test_a_gpu_recipe_and_xlarge_are_refused_with_the_fix(env):
    from lampway_server.compute import recipes as RC
    RC.RECIPES["gpu_probe"] = BK.Recipe("gpu_probe", "1", hardware_gpu="A10", entry="true")
    try:
        with pytest.raises(R.Refused, match="Boat has no GPU"):
            env.runner.plan(env.job(recipe="gpu_probe"))
    finally:
        RC.RECIPES.pop("gpu_probe")
    with pytest.raises(R.Refused, match="xlarge"):
        env.runner.plan(env.job(params={"type": "xlarge"}))


def test_the_binary_never_sees_provider_keys_in_its_environment(env, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRETSECRETSECRET")
    monkeypatch.setenv("FAL_KEY", "FALSECRET")
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("PATH", "/usr/bin")
    e = BT.clean_env()
    assert "OPENROUTER_API_KEY" not in e and "FAL_KEY" not in e and e["HOME"] == "/home/x"


def test_boat_is_gated_by_egress_consent_where_the_cli_is_launched(env, tmp_path):
    m = E.Egress(tmp_path / "eg")
    E.install()
    E.set_active(m)
    with pytest.raises(E.EgressRefused, match="compute:boat is off"):
        env.runner.submit(env.job())
    assert env.cli.verbs("new") == []
    m.set_route("compute:boat", True)
    assert env.runner.submit(env.job(idempotency_key="optin"))["state"] == "downloaded"
    assert [r for r in m.log() if r["event"] == "send" and r["route"] == "compute:boat"]
