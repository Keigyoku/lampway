"""Spend policy per provider (the user, 2026-10-05: "both caps and clicks set by prefs"): for OpenRouter, Higgsfield, the Studios and Hyper3D a day cap (a saved local-day total since ruling 5, 2026-10-07), a
per-job cap and require-click (off / above X / always). Higgsfield, the Studios and Hyper3D default to always; OpenRouter to off. The agent and swarm can never click:
only the user's confirm in the Client opens a gate, whatever the policy says."""

import time

import pytest

from lampway_server import provider_prefs as PP
from lampway_server.spendpolicy import SpendPolicy, SpendRefused

from .test_video_jobs import hf_calls, sign_in_higgsfield, stack, submit, wait_for  # noqa: F401  (the shared video/Higgsfield fixtures)


def test_the_defaults_and_the_shape_the_dialog_saves(settings):
    d = settings.spend_policy
    assert {k: d[k]["click"] for k in ("higgsfield", "studios", "hyper3d")} == {"higgsfield": "always", "studios": "always", "hyper3d": "always"} and d["openrouter"] == {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 5.0}
    assert PP.view(settings)["values"]["spend_policy"]["openrouter"] == {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 5.0}
    ok = PP.validate({"spend_policy": {"openrouter": {"click": "above", "above": 0.5, "day_cap": 3, "job_cap": 1}}})
    assert ok["spend_policy"]["openrouter"] == {"click": "above", "above": 0.5, "day_cap": 3.0, "job_cap": 1.0}
    for bad in ({"nobody": {"click": "off"}}, {"openrouter": {"click": "sometimes"}}, {"openrouter": {"click": "above"}}, {"openrouter": {"job_cap": -1}}, {"openrouter": {"colour": 1}}):
        with pytest.raises(PP.PrefsError):
            PP.validate({"spend_policy": bad})
    merged = PP.merge_values({"spend_policy": {"openrouter": {"click": "off", "job_cap": 2.0}}}, {"spend_policy": {"openrouter": {"click": "always"}, "studios": {"click": "above", "above": 10}}})
    assert merged["spend_policy"]["openrouter"] == {"click": "always", "job_cap": 2.0} and merged["spend_policy"]["studios"]["above"] == 10


def test_the_policy_decides_click_and_caps():
    pol = SpendPolicy(lambda: {"openrouter": {"click": "above", "above": 0.5, "job_cap": 1.0, "day_cap": 1.2}, "higgsfield": {"click": "always"}, "studios": {"click": "off"}, "hyper3d": {"click": "always"}})
    assert pol.needs_click("openrouter", 0.2) is False and pol.needs_click("openrouter", 0.8) is True and pol.needs_click("openrouter", None) is True, "an unknown price is never waved through"
    assert pol.needs_click("higgsfield", 0.0) is True and pol.needs_click("studios", 999) is False
    pol.check("openrouter", 0.9)
    with pytest.raises(SpendRefused, match="per-job cap"):
        pol.check("openrouter", 1.5)
    pol.record("openrouter", 0.9)
    with pytest.raises(SpendRefused, match="today's cap"):
        pol.check("openrouter", 0.5)
    pol.check("higgsfield", 5000)                               # no caps set: nothing to refuse


def _policy(settings, **per):
    for k, v in per.items():
        settings.spend_policy[k].update(v)


def test_an_openrouter_job_waits_for_the_captain_when_the_policy_says_so_and_runs_free_when_it_does_not(stack):
    fake, orv, hf, auth, ledger, app = stack
    s = app.state.settings
    body = {"prompt": "x", "params": {"duration": 5, "resolution": "480p"}}
    jid = submit(fake, "video_gen", "heygen/heygen-video-1", body)
    assert wait_for(fake, jid)["state"] == "succeeded" and len(orv.posts) == 1, "default off: no click"
    _policy(s, openrouter={"click": "always"})
    jid = submit(fake, "video_gen", "heygen/heygen-video-1", body)
    time.sleep(0.4)
    snap = fake.get(f"/api/v1/job-queue/jobs/{jid}").json()["data"]
    assert snap["state"] == "pending" and "confirm" in snap["user_message"].lower() and len(orv.posts) == 1, "nothing is sent before the click"
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert ap["studio"] == "openrouter" and ap["settings"]["unit"] == "usd"
    assert fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": ap["price"]}).status_code == 200
    assert wait_for(fake, jid)["state"] == "succeeded" and len(orv.posts) == 2
    _policy(s, openrouter={"click": "above", "above": 100.0})
    jid = submit(fake, "video_gen", "heygen/heygen-video-1", body)
    assert wait_for(fake, jid)["state"] == "succeeded" and len(orv.posts) == 3, "below the threshold: no click"


def test_a_job_cap_refuses_before_anything_is_sent_and_the_day_cap_counts_what_ran(stack):
    fake, orv, hf, auth, ledger, app = stack
    s = app.state.settings
    body = {"prompt": "x", "params": {"duration": 5, "resolution": "480p"}}
    _policy(s, openrouter={"job_cap": 0.0001})
    snap = wait_for(fake, submit(fake, "video_gen", "heygen/heygen-video-1", body))
    assert snap["state"] == "failed" and "per-job cap" in snap["error"] and orv.posts == []
    _policy(s, openrouter={"job_cap": None})
    est = wait_for(fake, submit(fake, "video_gen", "heygen/heygen-video-1", body))["result"]["estimate_usd"]
    _policy(s, openrouter={"day_cap": est * 1.5})
    snap = wait_for(fake, submit(fake, "video_gen", "heygen/heygen-video-1", body))
    assert snap["state"] == "failed" and "today's cap" in snap["error"] and len(orv.posts) == 1


def test_higgsfield_follows_its_policy_off_runs_without_a_click_and_always_waits_and_no_agent_path_confirms(stack):
    fake, orv, hf, auth, ledger, app = stack
    s = app.state.settings
    sign_in_higgsfield(auth, hf)
    body = {"prompt": "x", "params": {"duration": 8, "resolution": "720p"}}
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", body)
    snap = wait_for(fake, jid, states=("pending",))
    assert hf_calls(hf) == [], "always (the default): waits for the user"
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert app.state.jobs.approvals.get(ap["id"]).state == "pending"
    import pytest as _p
    from lampway_server.studios.approvals import ApprovalError
    with _p.raises(ApprovalError, match="only the user"):
        app.state.jobs.approvals.confirm(ap["id"], ap["price"], by="agent")
    fake.post(f"/app/studio/approvals/{ap['id']}/reject")
    _policy(s, higgsfield={"click": "off"})
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", body)
    assert wait_for(fake, jid)["state"] == "succeeded" and len(hf_calls(hf)) == 1, "off: the user chose no click for Higgsfield"
    _policy(s, higgsfield={"click": "always", "job_cap": 5})
    snap = wait_for(fake, submit(fake, "video_gen", "higgsfield/seedance1_5", body))
    assert snap["state"] == "failed" and "per-job cap" in snap["error"] and len(hf_calls(hf)) == 1
