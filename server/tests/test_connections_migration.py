# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_migration.md tests 1, 2, 3, 5 and 7: every existing way of supplying a credential keeps working with no action from the
user, and the one store that held a key nobody used (BYOK, finding F3) moves that key into Connections (C5: BYOK only writes there),
removing it from the plain JSON only after the store gives it back."""

import json
import os

import pytest

from lampway_server import connections as C
from lampway_server.connections import store as CS

OR_KEY = "sk-" "or-v1-FAKE-MIGRATION-1234567890abcdef"
ANT_KEY = "sk-" "ant-FAKE-MIGRATION-0123456789abcdefWXYZ"


@pytest.fixture
def clean_env(monkeypatch):
    for k in list(os.environ):
        if any(t in k for t in ("API_KEY", "TOKEN", "SECRET")) or k.startswith("LAMPWAY_OPENROUTER") or k.startswith("FAL_"):
            monkeypatch.delenv(k, raising=False)


def test_env_only_setup_unchanged(clean_env, monkeypatch, tmp_path):
    from lampway_server.agent.providers import make_provider
    from lampway_server.agent.providers.openrouter import OpenRouterProvider
    from lampway_server.app import default_job_backends
    from lampway_server.config import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", OR_KEY)
    settings = Settings.from_env({"LAMPWAY_PROVIDER": "openrouter", "LAMPWAY_STATE_DIR": str(tmp_path / "state")})
    provider = make_provider(settings)
    assert isinstance(provider, OpenRouterProvider) and C.secret_of(C.credential("openrouter")) == OR_KEY
    assert "image_gen" in default_job_backends(settings)


@pytest.mark.parametrize("text", [f"OPENROUTER_API_KEY={OR_KEY}\n", OR_KEY + "\n"])
def test_key_file_flag_unchanged(clean_env, monkeypatch, tmp_path, text):
    from lampway_server.agent.providers.openrouter import resolve_api_key
    f = tmp_path / "or.env"
    f.write_text(text)
    f.chmod(0o600)
    monkeypatch.setenv("LAMPWAY_OPENROUTER_KEY_FILE", str(f))                 # what the launcher's --openrouter-key-file exports
    assert resolve_api_key() == OR_KEY
    v = C.active().view(["openrouter"])[0]
    assert v["active_source"]["mode"] == "pointer" and "LAMPWAY_OPENROUTER_KEY_FILE" in v["active_source"]["label"]


def test_chatgpt_file_read_compatible(tmp_path):
    """A chatgpt_auth.json written by the code before Connections reads as signed in, and a refresh writes the same keys plus
    refresh_started_at."""
    import httpx
    from lampway_server import chatgpt_auth as CA
    old = {"host_id": "urn:uuid:1", "selected": "oaiapp_X", "accounts": {"oaiapp_X": {
        "email": "u@example.com", "issuer": CA.ISSUER, "subject": "s", "client_id": "oaiapp_X", "ext_agent_host_id": "urn:uuid:1",
        "id_token": "a.b.c", "access_token": "at-old", "refresh_token": "rt-old", "token_type": "Bearer", "expires_in": 3600,
        "expires_at": 10.0, "scopes": sorted(CA.SCOPES.split()), "saved_at": 5}}}
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "chatgpt_auth.json").write_text(json.dumps(old))
    answer = httpx.Response(200, json={"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 3600, "scope": CA.SCOPES})
    auth = CA.ChatGPTAuth(tmp_path / "state", http=httpx.Client(transport=httpx.MockTransport(lambda r: answer)), clock=lambda: 100.0)
    assert auth.status()["signed_in"] is True
    assert auth._access_token_sync() == "at-new"
    acct = json.loads((tmp_path / "state" / "chatgpt_auth.json").read_text())["accounts"]["oaiapp_X"]
    assert set(old["accounts"]["oaiapp_X"]) | {"refresh_started_at"} == set(acct)


# ------------------------------------------------------------------------------------------------ BYOK (F3, C5)
def test_byok_route_contract_kept(fake, settings):
    fake.login()
    saved = fake.put("/api/v1/agent/byok", json={"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": ANT_KEY})
    assert saved.status_code == 200
    item = saved.json()["data"]["items"][0]
    assert item["provider"] == "anthropic" and item["key_preview"].endswith("WXYZ") and ANT_KEY not in saved.text
    stored = json.loads((settings.state_dir / "agent_settings.json").read_text())
    assert "api_key" not in json.dumps(stored) and ANT_KEY not in json.dumps(stored)
    assert stored["byok"]["stored_in"] == "connections"
    assert C.secret_of(C.credential("anthropic")) == ANT_KEY                  # the key is Connections' manual source for anthropic
    got = fake.get("/api/v1/agent/credentials").json()["data"]
    assert got["byok_active"] is True and got["items"][0]["key_preview"].endswith("WXYZ")
    assert fake.delete("/api/v1/agent/credentials/all").json()["data"]["removed"] == 1
    with pytest.raises(C.NotConnected):
        C.credential("anthropic")


def test_an_old_plain_byok_key_moves_into_connections_on_start(tmp_path, settings, provider):
    from lampway_server.app import create_app
    settings.state_dir.mkdir(parents=True)
    (settings.state_dir / "agent_settings.json").write_text(json.dumps({"byok": {"provider": "anthropic", "model": "claude-sonnet-5-5",
                                                                                 "api_key": ANT_KEY, "base_url": None, "supports_vision": True},
                                                                        "preferences": {}}))
    create_app(settings, provider=provider)
    stored = (settings.state_dir / "agent_settings.json").read_text()
    assert ANT_KEY not in stored and json.loads(stored)["byok"]["stored_in"] == "connections"
    assert C.secret_of(C.credential("anthropic")) == ANT_KEY
    assert not list(settings.state_dir.glob("agent_settings.json*.bak")), "no plaintext backup is kept"


def test_byok_move_is_verified_before_delete(tmp_path, settings, provider, monkeypatch):
    from lampway_server.app import create_app

    class Refusing(CS.MemoryStore):
        kind = "file"

        def put(self, cid, fields):
            raise CS.StoreError("the disk is full (fake)")
    monkeypatch.setattr("lampway_server.connections.hub.choose_store", lambda d, b=None: (Refusing(), "a refusing store"))
    settings.state_dir.mkdir(parents=True)
    (settings.state_dir / "agent_settings.json").write_text(json.dumps({"byok": {"provider": "anthropic", "model": "m", "api_key": ANT_KEY,
                                                                                 "base_url": None, "supports_vision": True}, "preferences": {}}))
    create_app(settings, provider=provider)
    assert ANT_KEY in (settings.state_dir / "agent_settings.json").read_text(), "the key stays where it was until the store has it"
    row = C.active().view(["byok_legacy"])[0]
    assert row["state"] == "error" and "could not be moved into Connections" in row["next_step"]


def test_the_anthropic_provider_gets_the_connections_key(clean_env, monkeypatch, tmp_path):
    from lampway_server.agent.providers import make_provider
    from lampway_server.config import Settings
    C.set_active(C.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", store=CS.MemoryStore()))
    C.active().put_secret("anthropic", {"key": ANT_KEY}, by="user")
    p = make_provider(Settings(state_dir=tmp_path / "state", provider="anthropic"))
    assert p.client.api_key == ANT_KEY


@pytest.mark.parametrize("shape,cid,fields,header", [
    ("runpod", "compute:runpod", {"key": "rp-FAKE-MIGRATION-000000000000"}, {"Authorization": "Bear" "er rp-FAKE-MIGRATION-000000000000"}),
    ("modal", "compute:modal", {"token_id": "ak-FAKE", "token_secret": "as-FAKE"}, {"Modal-Key": "ak-FAKE", "Modal-Secret": "as-FAKE"}),
    ("fal", "fal", {"key": "fal-FAKE-MIGRATION-0000000000"}, {"Authorization": "Key fal-FAKE-MIGRATION-0000000000"})])
def test_compute_endpoints_take_their_key_from_connections(clean_env, tmp_path, shape, cid, fields, header):
    from lampway_server.compute.endpoint import EndpointBackend
    C.set_active(C.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", store=CS.MemoryStore(), env={}))
    C.active().put_secret(cid, fields, by="user")
    assert EndpointBackend(shape, {})._headers() == header


def test_a_real_call_that_answers_401_turns_the_row_expired_and_a_good_one_marks_the_use(clean_env, tmp_path):
    import asyncio
    import httpx
    from lampway_server.agent.providers.base import Message, ModelRequest
    from lampway_server.agent.providers.openrouter import OpenRouterProvider, SpendLedger
    clock = [1_000_000.0]
    C.set_active(C.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", store=CS.MemoryStore(), env={"OPENROUTER_API_KEY": OR_KEY},
                       route_on=lambda r: True, clock=lambda: clock[0]))
    status = [401]

    def answer(request):
        if status[0] != 200:
            return httpx.Response(status[0], json={"error": "no"})
        return httpx.Response(200, text='data: {"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]}\n\ndata: [DONE]\n')
    p = OpenRouterProvider("m", OR_KEY, SpendLedger(10.0), transport=httpx.MockTransport(answer))
    req = ModelRequest(system="s", messages=[Message.user_text("x")], tools=[])

    async def run():
        return [e async for e in p.stream(req)]
    with pytest.raises(RuntimeError):
        asyncio.run(run())
    assert C.active().view(["openrouter"])[0]["state"] == "expired"
    status[0] = 200
    asyncio.run(run())
    rec = json.loads((tmp_path / "state" / "connections.json").read_text())["connections"]["openrouter"]
    assert rec["last_used"] == clock[0] and C.active().view(["openrouter"])[0]["state"] == "connected"
    before = (tmp_path / "state" / "connections.json").read_text()
    clock[0] += 60
    asyncio.run(run())
    assert (tmp_path / "state" / "connections.json").read_text() == before, "a good use is recorded at most once an hour"
