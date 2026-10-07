# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The captain's ruling 5 (2026-10-07): spend caps are a SAVED per-day total - the local day, surviving a restart, written atomically.
Defaults on every profile: $1 per job, $5 per day, a click above $0.25 (OpenRouter, the provider spending dollars; the credit providers
keep their click on every job). The Providers prefs override them key by key. The status route says "spent today $x of $y"."""

import json
import os
import time

import pytest
from starlette.testclient import TestClient

from lampway_server import provider_prefs as PP
from lampway_server.spendpolicy import DEFAULT_SPEND_POLICY, SpendPolicy, SpendRefused

NOON = time.mktime((2026, 10, 7, 12, 0, 0, 0, 0, -1))            # local noon: no test straddles a midnight
NEXT_DAY = NOON + 86400


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_the_defaults():
    assert DEFAULT_SPEND_POLICY["openrouter"] == {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 5.0}
    pol = SpendPolicy(lambda: {})
    assert pol.needs_click("openrouter", 0.25) is False and pol.needs_click("openrouter", 0.26) is True
    with pytest.raises(SpendRefused, match="per-job cap of 1"):
        pol.check("openrouter", 1.01)
    assert all(pol._cfg(p)["click"] == "always" for p in ("higgsfield", "studios", "hyper3d"))


def test_a_fresh_profile_carries_the_defaults(settings):
    assert settings.spend_policy["openrouter"] == {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 5.0}


def test_prefs_override_the_defaults_key_by_key(tmp_path):
    pol = SpendPolicy(lambda: {"openrouter": {"click": "off"}}, path=tmp_path / "day.json", clock=Clock(NOON))
    cfg = pol._cfg("openrouter")
    assert cfg["click"] == "off" and cfg["job_cap"] == 1.0 and cfg["day_cap"] == 5.0
    pol = SpendPolicy(lambda: {"openrouter": {"job_cap": 3.0, "day_cap": None}}, path=tmp_path / "day.json", clock=Clock(NOON))
    pol.check("openrouter", 2.5)                                                       # raised per-job cap, no day cap
    assert pol._cfg("openrouter")["above"] == 0.25


def test_the_legacy_session_cap_is_saved_as_the_day_cap():
    assert PP.validate({"spend_policy": {"openrouter": {"session_cap": 3}}})["spend_policy"]["openrouter"] == {"day_cap": 3.0}


def test_the_day_total_survives_a_restart_and_is_written_atomically(tmp_path):
    path = tmp_path / "spend" / "day.json"
    first = SpendPolicy(lambda: {}, path=path, clock=Clock(NOON))
    first.record("openrouter", 0.9)
    first.record("openrouter", 0.9)
    first.record("openrouter", 0.9)
    first.record("openrouter", 0.9)
    first.record("openrouter", 0.9)
    second = SpendPolicy(lambda: {}, path=path, clock=Clock(NOON + 60))            # the server restarted
    assert second.spent_today("openrouter") == pytest.approx(4.5)
    second.check("openrouter", 0.4)
    with pytest.raises(SpendRefused, match="today's cap of 5"):                     # 0.9 is under the $1 job cap: the day total refuses it
        second.check("openrouter", 0.9)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600" and sorted(p.name for p in path.parent.iterdir()) == ["day.json"]
    assert json.loads(path.read_text())["day"] == time.strftime("%Y-%m-%d", time.localtime(NOON))


def test_the_day_rolls_over_at_local_midnight(tmp_path):
    path = tmp_path / "day.json"
    clock = Clock(NOON)
    pol = SpendPolicy(lambda: {}, path=path, clock=clock)
    pol.record("openrouter", 0.9)
    pol.record("openrouter", 0.9)
    pol.record("openrouter", 0.9)
    pol.record("openrouter", 0.9)
    pol.record("openrouter", 0.9)
    with pytest.raises(SpendRefused):
        pol.check("openrouter", 0.9)
    clock.t = NEXT_DAY
    assert pol.spent_today("openrouter") == 0.0
    pol.check("openrouter", 0.9)
    pol.record("openrouter", 0.5)
    assert SpendPolicy(lambda: {}, path=path, clock=Clock(NEXT_DAY)).spent_today("openrouter") == pytest.approx(0.5)


def test_an_unreadable_day_file_refuses_rather_than_resetting_the_total(tmp_path):
    path = tmp_path / "day.json"
    path.write_text("{not json")
    with pytest.raises(SpendRefused, match="unreadable"):
        SpendPolicy(lambda: {}, path=path, clock=Clock(NOON)).check("openrouter", 0.1)


def test_the_status_route_says_spent_today_x_of_y(settings, provider, tmp_path):
    from lampway_server.app import create_app
    from tests.fake_client import FakeMixarClient
    day = time.strftime("%Y-%m-%d", time.localtime())
    (settings.state_dir / "spend").mkdir(parents=True, exist_ok=True)
    (settings.state_dir / "spend" / "day.json").write_text(json.dumps({"day": day, "spent": {"openrouter": 0.3}}))
    with TestClient(create_app(settings, provider=provider), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        body = http.get("/app/spend", headers=fake.rest_headers()).json()
    assert body["scope"] == "day"
    row = next(r for r in body["providers"] if r["provider"] == "openrouter")
    assert row["text"] == "spent today $0.30 of $5.00" and row["spent_today"] == pytest.approx(0.3) and row["day_cap"] == 5.0 and row["job_cap"] == 1.0
