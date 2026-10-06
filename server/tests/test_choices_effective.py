# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A choice set in Choices takes effect where the settings decide today (choices_migration.md step 3, the direction that matters first):
``provider_prefs.effective()`` and the server's settings read the user's Choices over the Providers dialog's values, and the environment
still wins for the session (CH4). Saving the main agent's choice rebuilds the agent's provider, as the Providers dialog's PUT did."""

import pytest

from lampway_server import provider_prefs as PP
from lampway_server.choices import store as CS

KEY = "sk-" "or-v1-" + "7c6d" * 16


@pytest.fixture
def state(tmp_path, monkeypatch):
    for k in list(PP.ENV_VARS.values()):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def test_a_choice_wins_over_the_dialog_and_the_environment_wins_over_both(state, monkeypatch):
    PP.save(state, {"provider": "chatgpt_plan"})
    CS.FileStore(state).set("agent.main", "global", None, {"preferred": "openrouter:anthropic/claude-sonnet-5.5"}, by="user")
    s = PP.effective()
    assert s.provider == "openrouter" and s.openrouter_model == "anthropic/claude-sonnet-5.5" and s.sources["provider"] == "choices"
    monkeypatch.setenv("LAMPWAY_PROVIDER", "mock")
    assert PP.effective().provider == "mock"


def test_an_image_choice_sets_the_backend_and_the_purpose_model(state):
    CS.FileStore(state).set("image.plates", "global", None, {"preferred": "openrouter:sourceful/riverflow-v2.5-pro", "params": {"quality": "high"}}, by="user")
    CS.FileStore(state).set("video.loop", "global", None, {"preferred": "openrouter:bytedance/seedance-2.0-mini"}, by="user")
    s = PP.effective()
    assert s.image_backend == "openrouter" and s.image_purposes["plates"]["model"] == "sourceful/riverflow-v2.5-pro"
    assert s.image_purposes["plates"]["quality"] == "high" and s.image_purposes["plates"]["size"] == "2880x2880"
    assert s.video_purposes["loop"]["model"] == "bytedance/seedance-2.0-mini"


def test_saving_the_main_agents_choice_rebuilds_its_provider(state, settings, provider, monkeypatch):
    from starlette.testclient import TestClient
    from lampway_server.agent.providers.openrouter import OpenRouterProvider
    from lampway_server.app import create_app
    from tests.fake_client import FakeMixarClient
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    settings.provider = "mock"
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        r = http.put("/app/choices/agent.main", json={"scope": "global", "preferred": "openrouter:anthropic/claude-sonnet-5.5"}, headers=fake.rest_headers())
        assert r.status_code == 200, r.text
        assert isinstance(app.state.agent.provider, OpenRouterProvider) and settings.provider == "openrouter"
