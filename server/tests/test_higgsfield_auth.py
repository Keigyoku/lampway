"""Higgsfield sign-in: a standard MCP OAuth flow through Clerk - metadata discovery, dynamic client registration ("Lampway"), authorization
code + S256 PKCE on the server's loopback port, tokens 0600 in the state dir, ONE auth instance per server with serialized refresh (refresh
tokens rotate), and no OAuth secret in any log line."""

import json
import logging
import os
import stat
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from lampway_server import higgsfield_auth as HA

from .fake_higgsfield import MCP, FakeHiggsfield


@pytest.fixture
def hf():
    return FakeHiggsfield()


@pytest.fixture
def auth(tmp_path, hf):
    return HA.HiggsfieldAuth(tmp_path / "state", http=httpx.Client(transport=hf.transport()), redirect_port=8787)


def sign_in(auth, hf):
    attempt = auth.start_login()
    return attempt, auth.complete_login(hf.authorize(attempt.url))


def test_start_login_discovers_registers_lampway_and_builds_a_pkce_authorize_url(auth, hf):
    attempt = auth.start_login()
    assert len(hf.registered) == 1 and hf.registered[0]["client_name"] == "Lampway"
    assert hf.registered[0]["redirect_uris"] == ["http://127.0.0.1:8787/auth/higgsfield/callback"] and hf.registered[0]["token_endpoint_auth_method"] == "none"
    u = urlparse(attempt.url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert u.netloc == "clerk.higgsfield.ai" and u.path == "/oauth/authorize"
    assert q["response_type"] == "code" and q["code_challenge_method"] == "S256" and q["scope"] == "openid email offline_access"
    assert q["resource"] == MCP and q["redirect_uri"] == "http://127.0.0.1:8787/auth/higgsfield/callback" and q["state"] and q["code_challenge"]
    auth.start_login()
    assert len(hf.registered) == 1, "the registration is kept: Lampway registers once per redirect URI"


def test_the_callback_exchanges_the_code_with_the_verifier_and_stores_tokens_0600(auth, hf, tmp_path):
    attempt, status = sign_in(auth, hf)
    assert status["signed_in"] is True
    path = tmp_path / "state" / "higgsfield_auth.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    exchange = hf.token_requests[0]
    assert exchange["grant_type"] == "authorization_code" and exchange["code_verifier"] and exchange["resource"] == MCP
    assert json.loads(path.read_text())["access_token"].startswith("hf-access-")


def test_a_forged_state_a_declined_consent_and_a_missing_code_are_refused(auth, hf):
    auth.start_login()
    with pytest.raises(HA.LoginError, match="state"):
        auth.complete_login({"code": "x", "state": "forged"})
    a = auth.start_login()
    with pytest.raises(HA.LoginDeclined):
        auth.complete_login({"error": "access_denied", "state": a.state})
    b = auth.start_login()
    with pytest.raises(HA.LoginError, match="code"):
        auth.complete_login({"state": b.state})
    assert hf.token_requests == [] and auth.status()["signed_in"] is False


def test_a_wrong_verifier_fails_the_exchange_and_nothing_is_stored(auth, hf):
    a = auth.start_login()
    cb = hf.authorize(a.url)
    a.verifier = "tampered"
    with pytest.raises(HA.LoginError, match="exchange"):
        auth.complete_login(cb)
    assert auth.status()["signed_in"] is False


@pytest.mark.anyio
async def test_the_access_token_refreshes_once_when_it_expires_and_the_rotated_token_is_saved(tmp_path, hf):
    clock = [1000.0]
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()), clock=lambda: clock[0])
    sign_in(auth, hf)
    first = await auth.access_token()
    assert await auth.access_token() == first and len(hf.token_requests) == 1
    clock[0] += 4000
    second = await auth.access_token()
    assert second != first and hf.token_requests[-1]["grant_type"] == "refresh_token"
    clock[0] += 4000
    third = await auth.access_token()
    assert third != second, "the rotated refresh token was saved and used"


def test_concurrent_callers_share_one_refresh_because_the_refresh_token_rotates(tmp_path, hf):
    clock = [1000.0]
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()), clock=lambda: clock[0])
    sign_in(auth, hf)
    clock[0] += 4000
    results = []
    threads = [threading.Thread(target=lambda: results.append(auth._access_token_sync())) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(results)) == 1 and sum(r["grant_type"] == "refresh_token" for r in hf.token_requests) == 1


@pytest.mark.anyio
async def test_not_signed_in_and_a_revoked_session_say_so_and_never_fall_back(tmp_path, hf):
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()))
    with pytest.raises(HA.NotSignedIn, match="/app/higgsfield"):
        await auth.access_token()
    clock = [1000.0]
    auth2 = HA.HiggsfieldAuth(tmp_path / "s2", http=httpx.Client(transport=hf.transport()), clock=lambda: clock[0])
    sign_in(auth2, hf)
    hf.refresh_tokens.clear()
    clock[0] += 4000
    with pytest.raises(HA.NotSignedIn, match="sign in again"):
        await auth2.access_token()
    assert auth2.status()["signed_in"] is False


def test_sign_out_removes_the_tokens_but_keeps_the_registration(auth, hf, tmp_path):
    sign_in(auth, hf)
    auth.sign_out()
    data = json.loads((tmp_path / "state" / "higgsfield_auth.json").read_text())
    assert "access_token" not in data and "refresh_token" not in data and data["registration"]["client_id"]
    assert auth.status()["signed_in"] is False


def test_no_oauth_secret_reaches_a_log_line(auth, hf, caplog):
    from lampway_server import logredact
    logredact.install()
    caplog.set_level(logging.DEBUG)
    a, status = sign_in(auth, hf)
    secrets_ = [json.loads(open(auth.path).read())["access_token"], json.loads(open(auth.path).read())["refresh_token"], a.verifier, a.state]
    logging.getLogger("lampway.test").info(f"callback /auth/higgsfield/callback?code=abc123&state={a.state}")
    logging.getLogger("uvicorn.access").info('%s - "GET %s"', "127.0.0.1", f"/auth/higgsfield/callback?code=zzz999&state={a.state}")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "abc123" not in text and "zzz999" not in text and a.state not in text and all(s not in text for s in secrets_)
