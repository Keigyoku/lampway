# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md step 9: the Providers dialog's PUT writes the choices Choices models (main agent, workers, image and video
purposes) into choices.json as the user's click, and provider_prefs.json keeps only what has no Choices home (spend, caps, the global
image size and quality); the route answers as before. The helper that listed the enums is options() now (the wire key stays "choices")."""

import json

import pytest

from lampway_server import provider_prefs as PP
from lampway_server.app import create_app
from tests.fake_client import FakeMixarClient
from starlette.testclient import TestClient


@pytest.fixture
def client(settings, monkeypatch):
    for k in PP.ENV_VARS.values():
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-" "or-v1-" + "1f2e" * 16)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, app


def test_the_dialogs_put_writes_choices_and_not_the_old_file(client, settings):
    fake, app = client
    r = fake.put("/app/provider-settings", json={"values": {"swarm_provider": "openrouter", "openrouter_swarm_model": "deepseek/deepseek-v4.1-flash",
                                                            "openrouter_image_quality": "high", "spend_policy": {"openrouter": {"click": "always"}}}})
    assert r.status_code == 200, r.text
    choices = json.loads((settings.state_dir / "choices.json").read_text())["purposes"]
    assert choices["agent.worker"]["preferred"] == "openrouter:deepseek/deepseek-v4.1-flash" and choices["agent.worker"]["set_by"] == "user"
    saved = json.loads((settings.state_dir / "provider_prefs.json").read_text())
    assert "swarm_provider" not in saved and "openrouter_swarm_model" not in saved
    assert saved["openrouter_image_quality"] == "high" and saved["spend_policy"]["openrouter"]["click"] == "always"
    assert r.json()["values"]["swarm_provider"] == "openrouter" and "choices" in r.json()          # the wire contract is unchanged
    assert app.state.settings.swarm_provider == "openrouter"


def test_the_enum_helper_is_options():
    assert "main_providers" in PP.options() and not hasattr(PP, "choices")
