"""GET /app/spend: what the status bar's spend gauge reads (facelift contract 03). Read-only: each provider in its own unit, what was spent today
(the saved local-day total of ruling 5, 2026-10-07), the caps and click rule the Providers dialog set, and "spent today $x of $y". ``session_cap``
repeats ``day_cap`` for a client not yet on the day keys."""

from .test_video_jobs import stack  # noqa: F401  (the shared stack fixture)


def test_the_spend_view_reports_each_provider_in_its_unit_and_its_scope(stack):
    fake, _orv, _hf, _auth, _ledger, app = stack
    app.state.settings.spend_policy["openrouter"].update({"click": "above", "above": 0.25, "day_cap": 5.0, "job_cap": 1.0})
    app.state.jobs.policy.record("openrouter", 0.31)
    view = fake.get("/app/spend").json()
    assert view["scope"] == "day"
    by = {p["provider"]: p for p in view["providers"]}
    assert set(by) == {"openrouter", "higgsfield", "studios", "hyper3d"}
    assert by["openrouter"] == {"provider": "openrouter", "unit": "USD", "spent": 0.31, "spent_today": 0.31, "text": "spent today $0.31 of $5.00",
                                "day_cap": 5.0, "session_cap": 5.0, "job_cap": 1.0, "click": "above", "above": 0.25}
    assert by["higgsfield"]["unit"] == "credits" and by["higgsfield"]["spent"] == 0.0 and by["higgsfield"]["day_cap"] is None
    assert by["higgsfield"]["text"] == "spent today 0 credits (no daily cap)"


def test_the_spend_view_needs_a_signed_in_client(stack):
    fake, *_rest, app = stack
    assert fake.get("/app/spend", headers={"Authorization": "Bearer nope"}).status_code == 401
