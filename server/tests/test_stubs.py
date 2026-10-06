"""Endpoints that only have to keep the client quiet. Each assertion is the exact
read the client code performs on the body (file:line in the comments)."""

import pytest

BEARER_GETS = [
    "/api/v1/notifications/sounds",
    "/api/v1/updates/check?platform=linux&current_version=5.2.0&channel=stable&install_id=abc",
    "/api/v1/subscriptions/status",
    "/api/v1/generation-catalog",
    "/api/v1/generation-catalog/chat-options",
    "/api/v1/agent/models",
    "/api/v1/agent/credentials",
    "/api/v1/agent/model-preference",
    "/api/v1/referrals/dashboard",
]


@pytest.mark.parametrize("path", BEARER_GETS)
def test_bearer_endpoints_refuse_without_a_token(fake, path):
    assert fake.get(path).status_code == 401


def test_sounds_catalog_is_an_enveloped_list_with_an_etag_and_revalidates(fake):
    fake.login()
    response = fake.get("/api/v1/notifications/sounds")
    assert response.status_code == 200
    body = response.json()
    # sound_catalog.py:257-260: body.data.sounds
    assert body["status"] == "success"
    assert isinstance(body["data"]["sounds"], list)
    etag = response.headers["etag"]
    again = fake.get("/api/v1/notifications/sounds", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_client_version_put_answers_status_success(fake):
    fake.login()
    response = fake.put("/api/v1/notifications/me/client-version",
                        json={"client_version": "5.2.0", "device_id": fake.device_id})
    assert response.status_code == 200
    assert response.json()["status"] == "success"  # rest_api.py:61


def test_update_check_reports_no_update(fake):
    fake.login()
    response = fake.get("/api/v1/updates/check?platform=linux&current_version=5.2.0&channel=stable&install_id=abc")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["update_available"] is False
    assert body["data"]["current_version"] == "5.2.0"


def test_subscription_status_carries_the_meter_fields(fake):
    fake.login()
    body = fake.get("/api/v1/subscriptions/status").json()
    data = body["data"]
    for key in ("plan_slug", "plan_name", "billing_interval", "credits_per_month", "balance_cents",
                "plan_value_cents", "usage_pct", "cycle_start", "cycle_end", "days_left",
                "subscription_expires_at"):
        assert key in data, key
    assert data["credits_per_month"] > 0


@pytest.mark.parametrize("path,key", [
    ("/api/v1/generation-catalog", "capabilities"),          # generation_catalog_cache.py:339-344
    ("/api/v1/generation-catalog/chat-options", "options"),  # chat_generate_options_cache.py:355-357
])
def test_generation_catalogues_are_empty_lists_with_an_etag(fake, path, key):
    fake.login()
    response = fake.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"][key] == []
    assert "catalog_version" in body["data"]
    etag = response.headers["etag"]
    assert fake.get(path, headers={"If-None-Match": etag}).status_code == 304


def test_generation_catalog_also_carries_styles_and_credit_costs(fake):
    fake.login()
    data = fake.get("/api/v1/generation-catalog").json()["data"]
    assert data["styles"] == {}
    assert data["credit_costs"] == {}


def test_agent_models_lists_our_providers(fake):
    fake.login()
    response = fake.get("/api/v1/agent/models")
    assert response.status_code == 200
    data = response.json()["data"]  # models_cache.py:166-168
    assert isinstance(data["providers"], list) and data["providers"]
    ids = {p["id"] for p in data["providers"]}
    assert {"anthropic", "openai"} <= ids
    anthropic = next(p for p in data["providers"] if p["id"] == "anthropic")
    model = next(m for m in anthropic["models"] if m["id"] == "claude-sonnet-5-5")
    for key in ("label", "platform_available", "byok_available", "supports_vision", "eligible", "thinking_levels"):
        assert key in model, key
    assert response.headers["etag"]
    assert fake.get("/api/v1/agent/models", headers={"If-None-Match": response.headers["etag"]}).status_code == 304


def test_byok_round_trip_stores_in_connections_and_never_echoes_the_key(fake, settings):
    fake.login()
    before = fake.get("/api/v1/agent/credentials").json()["data"]
    assert before == {"byok_active": False, "items": []}  # credential_state.py:152-153

    saved = fake.put("/api/v1/agent/byok", json={"provider": "anthropic", "model": "claude-sonnet-5-5",
                                                  "api_key": "sk-" "ant-secret-FAKE-0000000000001234"})
    assert saved.status_code == 200
    data = saved.json()["data"]
    assert data["byok_active"] is True
    item = data["items"][0]
    assert item["provider"] == "anthropic" and item["model"] == "claude-sonnet-5-5"
    assert "api_key" not in item
    assert "sk-" "ant-secret-FAKE-0000000000001234" not in saved.text
    assert item["key_preview"].endswith("1234")

    assert fake.get("/api/v1/agent/credentials").json()["data"]["byok_active"] is True
    # C5 / finding F3: the key is Connections' (the anthropic row's manual source), never the plain JSON, and never logged.
    stored = (settings.state_dir / "agent_settings.json").read_text()
    assert "sk-" "ant-secret-FAKE-0000000000001234" not in stored and "api_key" not in stored

    removed = fake.delete("/api/v1/agent/credentials/all")
    assert removed.status_code == 200
    assert removed.json()["data"]["removed"] == 1
    assert fake.get("/api/v1/agent/credentials").json()["data"]["byok_active"] is False


def test_model_preference_round_trip(fake, settings):
    """Choices step 8 (coordinator ruling 2026-10-06): the client's model picker is a user surface over Choices. GET answers the user's
    agent.main / agent.worker choices; PUT writes agent.main as the user's click; DELETE clears it (the shipped default runs again)."""
    fake.login()
    empty = fake.get("/api/v1/agent/model-preference").json()["data"]
    assert empty["items"] == []                                      # no choice set yet: the picker shows none (the shipped default runs)
    saved = fake.put("/api/v1/agent/model-preference",
                     json={"provider": "anthropic", "model": "claude-sonnet-5-5", "role": "default"})
    assert saved.status_code == 200
    item = saved.json()["data"]["items"][0]  # preference_state.py:247-261
    assert item["role"] == "default" and item["provider"] == "anthropic" and item["model"] == "claude-sonnet-5-5"
    assert item["eligible"] is True and "label" in item
    import json as _json
    chosen = _json.loads((settings.state_dir / "choices.json").read_text())["purposes"]["agent.main"]
    assert chosen["preferred"] == "anthropic:claude-sonnet-5-5" and chosen["set_by"] == "user"
    assert fake.delete("/api/v1/agent/model-preference/default").status_code == 200
    assert fake.delete("/api/v1/agent/model-preference/default").status_code == 404
    assert fake.get("/api/v1/agent/model-preference").json()["data"]["items"] == []


def test_an_agent_cannot_change_the_model_preference(fake, settings):
    """CH3: an agent proposes; only the user's click changes agent.main."""
    fake.login()
    for header in ({"x-lampway-origin": "agent"}, {"x-mixar-job-origin": "agent"}):
        r = fake.http.put("/api/v1/agent/model-preference", json={"provider": "anthropic", "model": "claude-sonnet-5-5", "role": "default"},
                          headers={**fake.rest_headers(), **header})
        assert r.status_code == 403 and "only your click in Choices can change a choice" in r.text
        assert fake.http.delete("/api/v1/agent/model-preference/default", headers={**fake.rest_headers(), **header}).status_code == 403
    assert not (settings.state_dir / "choices.json").exists()


def test_model_preference_refuses_an_unknown_model_with_the_documented_prefix(fake):
    fake.login()
    response = fake.put("/api/v1/agent/model-preference",
                        json={"provider": "anthropic", "model": "gpt-9", "role": "default"})
    assert response.status_code == 400
    assert str(response.json()["detail"]).startswith("Model not available: ")  # agent_service.py:121-122


def test_referrals_dashboard_shape(fake):
    fake.login()
    data = fake.get("/api/v1/referrals/dashboard").json()["data"]  # flow.py:116-152
    assert set(data) >= {"invite_url", "award_amounts", "qualified_count"}
    assert set(data["award_amounts"]) >= {"invitee", "inviter", "paid_total"}


def test_telemetry_is_accepted_and_discarded(fake):
    fake.login()
    response = fake.post("/api/v1/telemetry/events", json={"events": [{"event": "x", "timestamp": "t",
                                                                         "event_id": "e", "properties": {}}]})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
