"""The compute AXI CLI (specs/cloud + the shelf's AXI principles): argparse, a live no-args view, TOON summaries, explicit empties, help[] next steps, structured errors with exit codes, no interactive
prompts, loud failure on unknown flags. One provider-agnostic CLI over the Lampway library: the user picks the provider, nothing is hard-wired."""
import io
import json

import pytest

from lampway_server import egress as E
from lampway_server.compute import cli as CLI
from lampway_server.compute import fake as FK
from lampway_server.compute import toon_out as T


def run(argv, tmp_path, backends=None, env=None):
    out, err = io.StringIO(), io.StringIO()
    clock = FK.FakeClock(1_700_000_000.0)
    fake = FK.FakeBackend(clock)
    ctx = CLI.Context(root=tmp_path / "proj", state=tmp_path / "state", backends_factory=lambda prefs: {"fake": fake}, clock=clock.now, sleep=clock.sleep)
    (tmp_path / "proj").mkdir(exist_ok=True)
    (tmp_path / "proj" / "in.png").write_bytes(b"\x89PNG" + b"\x00" * 8)
    rc = CLI.main(argv, ctx=ctx, out=out, err=err)
    return rc, out.getvalue(), err.getvalue(), fake


def test_toon_encodes_scalars_tables_scalar_lists_and_explicit_empties():
    s = T.dumps({"ok": True, "n": 3, "name": "a, b", "jobs": [{"key": "k1", "state": "done"}, {"key": "k2", "state": "x"}], "none": [], "tags": ["x", "y"], "nested": {"a": 1}})
    assert 'name: "a, b"' in s and "jobs[2]{key,state}:\n  k1,done\n  k2,x" in s and "none[0]:" in s and "tags[2]: x,y" in s and "nested:\n  a: 1" in s and "ok: true" in s


def test_no_arguments_shows_live_state_not_help_with_every_empty_stated(tmp_path):
    rc, out, err, _ = run([], tmp_path)
    assert rc == 0 and "usage:" not in out
    assert "backends[0]:" in out or "backends[" in out
    assert "jobs[0]:" in out and "billing_now: nothing" in out and "spent_today_usd: 0" in out and "job_cap_usd: 1" in out and "day_cap_usd: 5" in out
    assert "help[" in out and "compute backends" in out


def test_the_user_picks_the_provider_no_default_is_hardwired(tmp_path):
    rc, out, err, _ = run(["plan", "probe", "--input", "in.png:synthetic", "--max-seconds", "30"], tmp_path)
    assert rc == 1 and "pick a provider" in out and "help[" in out
    rc, out, _e, _f = run(["prefs", "--set", "backends=fake"], tmp_path)
    assert rc == 0


def test_plan_submit_status_list_and_the_price_card(tmp_path):
    run(["prefs", "--set", "backends=fake"], tmp_path)
    run(["prefs", "--set", "private_backends=fake"], tmp_path)
    rc, out, err, _ = run(["plan", "probe", "--backend", "fake", "--input", "in.png:synthetic", "--max-seconds", "30"], tmp_path)
    assert rc == 0 and "plan_id:" in out and "upper_bound_usd:" in out and "needs_click: false" in out and "uploads_files: 1" in out and "help[" in out
    rc, out, err, _ = run(["submit", "probe", "--backend", "fake", "--input", "in.png:synthetic", "--max-seconds", "30", "--origin", "user"], tmp_path)
    assert rc == 0 and "state: downloaded" in out and "teardown: verified" in out
    rc, out, _e, _f = run(["list"], tmp_path)
    assert rc == 0 and "jobs[1]{key,backend,recipe,state}" in out and ",fake,probe,downloaded" in out


def test_an_agent_origin_submit_is_refused_with_a_structured_error_and_exit_1(tmp_path):
    run(["prefs", "--set", "backends=fake"], tmp_path)
    rc, out, err, _ = run(["submit", "probe", "--backend", "fake", "--input", "in.png:synthetic", "--origin", "agent"], tmp_path)
    assert rc == 1 and "error: an agent can plan; the captain confirms in the Client" in out and "help[" in out


def test_an_unknown_flag_fails_loud_with_exit_2_and_no_prompt(tmp_path):
    rc, out, err, _ = run(["plan", "probe", "--bogus"], tmp_path)
    assert rc == 2 and "error:" in out and "--bogus" in out


def test_egress_view_and_the_users_switch_are_the_same_prefs_the_server_uses(tmp_path):
    rc, out, _e, _f = run(["egress"], tmp_path)
    assert rc == 0 and "routes[" in out and "compute:boat" in out and ",off" in out
    rc, out, _e, _f = run(["egress", "compute:boat", "on"], tmp_path)
    assert rc == 0 and "enabled: true" in out
    assert E.Egress(tmp_path / "state").enabled("compute:boat") is True


def test_reconcile_report_states_explicitly_when_nothing_bills(tmp_path):
    run(["prefs", "--set", "backends=fake"], tmp_path)
    rc, out, _e, _f = run(["reconcile"], tmp_path)
    assert rc == 0 and "billing_now: nothing" in out and "orphans[0]:" in out


def test_a_recipe_parameter_travels_with_the_job_and_selects_the_ops_outputs(tmp_path):
    run(["prefs", "--set", "backends=fake"], tmp_path)
    rc, out, err, fake = run(["plan", "blender_offload", "--backend", "fake", "--input", "in.png:synthetic", "--param", "op=silhouette", "--param", "size=64", "--max-seconds", "300"], tmp_path)
    assert rc == 0 and "upper_bound_usd:" in out
    rc, out, err, fake = run(["submit", "blender_offload", "--backend", "fake", "--input", "in.png:synthetic", "--param", "op=silhouette", "--param", "size=64", "--max-seconds", "300"], tmp_path)
    assert any(c[0] == "upload" and c[2] == "params.json" for c in fake.calls)
    assert "silhouette.png" in out and "state: provider_error" in out                      # the op named the extra output; the fake does not produce it, and the job says so
