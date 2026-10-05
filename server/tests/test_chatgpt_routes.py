"""The local pages of the ChatGPT sign-in: /app/chatgpt (status + "Continue with ChatGPT"), /app/chatgpt/start (to OpenAI's
authorization page), /auth/callback (the loopback redirect), sign-out. And the guard rails of the terms: no endpoint that
forwards requests to the ChatGPT-plan route, the provider is only the agent loop's."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server import chatgpt_auth as CA
from lampway_server.agent.providers import make_provider
from lampway_server.app import create_app
from lampway_server.config import Settings
from tests.test_chatgpt_auth import FakeOpenAI, ISSUED, JWKS, SCOPES


@pytest.fixture
def stack(tmp_path):
    fake = FakeOpenAI()
    settings = Settings(state_dir=tmp_path / "state", jwt_secret="s", provider="mock", port=8787)
    app = create_app(settings, chatgpt_auth=CA.ChatGPTAuth(
        settings.state_dir, http=httpx.Client(transport=httpx.MockTransport(fake.handler)), redirect_port=8787, jwks=lambda: JWKS))
    with TestClient(app, follow_redirects=False) as client:
        yield client, fake, app


def test_the_page_offers_continue_with_chatgpt_when_signed_out(stack):
    client, _, _ = stack
    r = client.get("/app/chatgpt")
    assert r.status_code == 200 and "Continue with ChatGPT" in r.text and "Using ChatGPT plan" not in r.text


def test_start_redirects_to_openais_authorization_page_with_the_documented_parameters(stack):
    client, _, _ = stack
    r = client.get("/app/chatgpt/start")
    assert r.status_code == 302
    u = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert (u.scheme, u.netloc, u.path) == ("https", "auth.openai.com", "/api/accounts/authorize")
    assert q["client_id"] == "dynamic_agent_client" and q["redirect_uri"] == "http://127.0.0.1:8787/auth/callback"
    assert q["agent_name_hint"] == "Lampway" and q["code_challenge_method"] == "S256"


def test_the_callback_completes_the_sign_in_and_the_page_links_to_manage_usage(stack):
    client, fake, app = stack
    r = client.get("/app/chatgpt/start")
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    fake.nonce = q["nonce"]
    cb = client.get("/auth/callback", params={"code": "CODE", "state": q["state"], "client_id": ISSUED, "scope": SCOPES})
    assert cb.status_code == 200 and "Using ChatGPT plan" in cb.text and "https://chatgpt.com/settings/usage" in cb.text
    assert "u@example.com" in client.get("/app/chatgpt").text
    status = client.get("/app/chatgpt/status").json()
    assert status["signed_in"] is True and status["plan_usage_enabled"] is True and "access_token" not in str(status) and "refresh" not in str(status)


def test_a_forged_callback_is_refused(stack):
    client, _, _ = stack
    r = client.get("/auth/callback", params={"code": "x", "state": "forged"})
    assert r.status_code == 400 and "state" in r.text


def test_declining_consent_shows_how_to_retry_and_stores_nothing(stack):
    client, _, app = stack
    r = client.get("/app/chatgpt/start")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    cb = client.get("/auth/callback", params={"error": "access_denied", "state": state})
    assert cb.status_code == 200 and "not authorized" in cb.text and "Continue with ChatGPT" in cb.text
    assert client.get("/app/chatgpt/status").json()["signed_in"] is False


def test_sign_out_from_a_foreign_origin_is_refused(stack):
    client, _, _ = stack
    assert client.post("/app/chatgpt/signout", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/app/chatgpt/signout", headers={"origin": "http://127.0.0.1:8787"}).status_code == 303


def test_there_is_no_route_that_forwards_requests_to_the_plan_route(stack):
    _, _, app = stack
    paths = [r.path for r in app.routes]
    for p in paths:
        assert "responses" not in p and "completions" not in p and not p.startswith("/v1")
    chatgpt = sorted(p for p in paths if "chatgpt" in p or p == "/auth/callback")
    assert chatgpt == ["/app/chatgpt", "/app/chatgpt/signout", "/app/chatgpt/start", "/app/chatgpt/status", "/auth/callback"]


def test_the_provider_name_selects_it_and_it_needs_no_key(tmp_path):
    settings = Settings(state_dir=tmp_path, provider="chatgpt_plan", chatgpt_model="gpt-6.1-sol")
    p = make_provider(settings, chatgpt_auth=CA.ChatGPTAuth(tmp_path))
    assert p.name == "chatgpt_plan" and p.model == "gpt-6.1-sol"


def test_the_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("LAMPWAY_CHATGPT_MODEL", "gpt-x")
    assert Settings.from_env().chatgpt_model == "gpt-x"
    monkeypatch.delenv("LAMPWAY_CHATGPT_MODEL")
    assert Settings.from_env().chatgpt_model == "gpt-6.1-sol"
