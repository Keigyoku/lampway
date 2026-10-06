"""GET /app/spend: what the status bar's spend gauge reads (facelift contract 03). Read-only: each provider in its own unit, what this server session
has spent, and the caps and click rule the Providers dialog set. The server keeps no day ledger, so the answer says its scope is the session."""

from .test_video_jobs import stack  # noqa: F401  (the shared stack fixture)


def test_the_spend_view_reports_each_provider_in_its_unit_and_its_scope(stack):
    fake, _orv, _hf, _auth, _ledger, app = stack
    app.state.settings.spend_policy["openrouter"].update({"click": "above", "above": 0.25, "session_cap": 5.0, "job_cap": 1.0})
    app.state.jobs.policy.record("openrouter", 0.31)
    view = fake.get("/app/spend").json()
    assert view["scope"] == "session"
    by = {p["provider"]: p for p in view["providers"]}
    assert set(by) == {"openrouter", "higgsfield", "studios", "hyper3d"}
    assert by["openrouter"] == {"provider": "openrouter", "unit": "USD", "spent": 0.31, "session_cap": 5.0, "job_cap": 1.0,
                                "click": "above", "above": 0.25}
    assert by["higgsfield"]["unit"] == "credits" and by["higgsfield"]["spent"] == 0.0 and by["higgsfield"]["session_cap"] is None


def test_the_spend_view_needs_a_signed_in_client(stack):
    fake, *_rest, app = stack
    assert fake.get("/app/spend", headers={"Authorization": "Bearer nope"}).status_code == 401
