"""Sign in with ChatGPT (plan usage), from the DOCUMENTED open-source flow only (developers.openai.com/siwc/
token-sharing-open-source): OAuth authorization code + PKCE (S256) with a loopback redirect, first registration as
dynamic_agent_client, the issued client_id kept, the ID token validated against OpenAI's JWKS, the granted scope checked for
chatgpt.tokens.use.direct, tokens stored locally (0600), rotating refresh serialized. A fake OpenAI stands in; nothing here
reaches openai.com, and the one human step - the consent click - is the user's."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import stat
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from lampway_server import chatgpt_auth as CA

ISSUER = "https://auth.openai.com"
ISSUED = "oaiapp_ISSUEDCLIENT"
SCOPES = "chatgpt.tokens.use.direct email offline_access openid profile resource.invoke"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWKS = {"keys": [{**json.loads(RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "alg": "RS256", "use": "sig"}]}


def id_token(nonce, *, aud=ISSUED, exp_in=600, iss=ISSUER, sub="user-1", email="u@example.com", key=KEY):
    now = int(time.time())
    return jwt.encode({"iss": iss, "aud": aud, "sub": sub, "email": email, "nonce": nonce, "iat": now, "exp": now + exp_in},
                      key, algorithm="RS256", headers={"kid": "k1"})


class FakeOpenAI:
    """The token endpoint, recording every request."""

    def __init__(self):
        self.requests = []
        self.next_scope = SCOPES
        self.nonce = None
        self.refresh_fail = None
        self.refresh_delay = 0.0
        self.count = 0

    def handler(self, request: httpx.Request):
        body = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append((str(request.url), body, dict(request.headers)))
        if str(request.url).endswith("/oauth/revoke"):
            return httpx.Response(200, json={})
        if body.get("grant_type") == "authorization_code":
            self.count += 1
            return httpx.Response(200, json={"access_token": f"access-{self.count}", "refresh_token": f"refresh-{self.count}",
                                             "id_token": id_token(self.nonce), "token_type": "Bearer", "expires_in": 3600,
                                             "scope": self.next_scope, "earliest_refresh_at": int(time.time())})
        if body.get("grant_type") == "refresh_token":
            if self.refresh_fail:
                return httpx.Response(400, json={"error": self.refresh_fail})
            self.count += 1
            return httpx.Response(200, json={"access_token": f"access-{self.count}", "refresh_token": f"refresh-{self.count}",
                                             "token_type": "Bearer", "expires_in": 3600, "scope": self.next_scope})
        return httpx.Response(400, json={"error": "unsupported_grant_type"})


@pytest.fixture
def fake():
    return FakeOpenAI()


@pytest.fixture
def auth(tmp_path, fake):
    client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return CA.ChatGPTAuth(tmp_path / "state", http=client, app_name="Lampway", redirect_port=8787, jwks=lambda: JWKS)


def start(auth, fake):
    attempt = auth.start_login()
    fake.nonce = parse_qs(urlparse(attempt.url).query)["nonce"][0]
    return attempt


def callback(attempt, **over):
    q = {"code": "CODE", "state": attempt.state, "client_id": ISSUED, "scope": SCOPES}
    q.update(over)
    return q


# ---- host id and the authorization request

def test_the_host_id_is_a_persisted_urn_uuid_in_a_0600_file(auth, tmp_path):
    hid = auth.host_id()
    assert hid.startswith("urn:uuid:") and auth.host_id() == hid
    path = tmp_path / "state" / "chatgpt_auth.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_first_registration_sends_exactly_the_documented_parameters(auth):
    a = auth.start_login()
    u = urlparse(a.url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert f"{u.scheme}://{u.netloc}{u.path}" == "https://auth.openai.com/api/accounts/authorize"
    assert q["client_id"] == "dynamic_agent_client" and q["agent_name_hint"] == "Lampway"
    assert q["ext_agent_host_id"] == auth.host_id() and q["response_type"] == "code"
    assert q["redirect_uri"] == "http://127.0.0.1:8787/auth/callback"                     # 127.0.0.1, never localhost
    assert q["scope"] == "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
    assert q["resource"] == "https://api.openai.com/v1" and q["code_challenge_method"] == "S256"
    assert q["state"] == a.state and q["nonce"] and "client_secret" not in q
    assert q["code_challenge"] == base64.urlsafe_b64encode(hashlib.sha256(a.verifier.encode()).digest()).rstrip(b"=").decode()
    assert len({a.state, q["nonce"], a.verifier}) == 3


def test_every_attempt_has_fresh_random_values(auth):
    a, b = auth.start_login(), auth.start_login()
    assert a.state != b.state and a.verifier != b.verifier


def test_a_reauthorization_uses_the_saved_client_id_and_no_name_hint(auth, fake):
    a = start(auth, fake)
    auth.complete_login(callback(a))
    b = auth.start_login()
    q = {k: v[0] for k, v in parse_qs(urlparse(b.url).query).items()}
    assert q["client_id"] == ISSUED and "agent_name_hint" not in q
    assert q["login_hint"] == "u@example.com" and q["id_token_hint"]
    assert q["ext_agent_host_id"] == auth.host_id()


# ---- the callback

def test_a_good_callback_exchanges_the_code_and_stores_the_credentials(auth, fake, tmp_path):
    a = start(auth, fake)
    st = auth.complete_login(callback(a))
    url, body, headers = fake.requests[0]
    assert url == "https://auth.openai.com/api/accounts/oauth/token"
    assert body == {"grant_type": "authorization_code", "client_id": ISSUED, "code": "CODE", "code_verifier": a.verifier,
                    "redirect_uri": "http://127.0.0.1:8787/auth/callback", "resource": "https://api.openai.com/v1"}
    assert "client_secret" not in body and "authorization" not in {k.lower() for k in headers}
    assert st["signed_in"] is True and st["plan_usage_enabled"] is True and st["email"] == "u@example.com"
    path = tmp_path / "state" / "chatgpt_auth.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    rec = json.loads(path.read_text())
    assert rec["accounts"][ISSUED]["access_token"] == "access-1" and rec["accounts"][ISSUED]["scopes"] == sorted(SCOPES.split())
    assert rec["accounts"][ISSUED]["issuer"] == ISSUER and rec["accounts"][ISSUED]["subject"] == "user-1"
    assert "dynamic_agent_client" not in json.dumps(rec["accounts"])


def test_a_state_mismatch_is_rejected_before_any_exchange(auth, fake):
    a = start(auth, fake)
    with pytest.raises(CA.LoginError, match="state"):
        auth.complete_login(callback(a, state="forged"))
    assert fake.requests == []


def test_access_denied_stops_the_attempt_with_no_exchange(auth, fake):
    a = start(auth, fake)
    with pytest.raises(CA.LoginDeclined):
        auth.complete_login({"error": "access_denied", "state": a.state})
    assert fake.requests == [] and auth.status()["signed_in"] is False


def test_a_new_registration_without_an_issued_client_id_is_incomplete(auth, fake):
    a = start(auth, fake)
    q = callback(a)
    del q["client_id"]
    with pytest.raises(CA.LoginError, match="registration is incomplete"):
        auth.complete_login(q)
    assert fake.requests == []


def test_the_dynamic_client_id_is_never_accepted_as_the_issued_one(auth, fake):
    a = start(auth, fake)
    with pytest.raises(CA.LoginError, match="registration is incomplete"):
        auth.complete_login(callback(a, client_id="dynamic_agent_client"))


def test_a_reauthorization_callback_with_a_different_client_id_is_rejected(auth, fake):
    auth.complete_login(callback(start(auth, fake)))
    b = start(auth, fake)
    with pytest.raises(CA.LoginError, match="different client"):
        auth.complete_login(callback(b, client_id="oaiapp_SOMEONEELSE"))


def test_an_attempt_can_only_be_completed_once(auth, fake):
    a = start(auth, fake)
    auth.complete_login(callback(a))
    with pytest.raises(CA.LoginError, match="state"):
        auth.complete_login(callback(a))


# ---- the ID token

@pytest.mark.parametrize("make,why", [
    (lambda n: id_token(n, aud="oaiapp_OTHER"), "audience"),
    (lambda n: id_token(n, iss="https://evil.example"), "issuer"),
    (lambda n: id_token(n, exp_in=-10), "expired"),
    (lambda n: id_token("not-the-nonce"), "nonce"),
    (lambda n: id_token(n, key=rsa.generate_private_key(public_exponent=65537, key_size=2048)), "signature"),
])
def test_an_id_token_that_fails_validation_stores_nothing(auth, fake, tmp_path, monkeypatch, make, why):
    a = start(auth, fake)
    monkeypatch.setattr(fake, "nonce", fake.nonce)
    real = fake.handler

    def handler(request):
        r = real(request)
        if b"authorization_code" in request.content:
            data = json.loads(r.content)
            data["id_token"] = make(parse_qs(urlparse(a.url).query)["nonce"][0])
            return httpx.Response(200, json=data)
        return r

    auth.http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CA.LoginError, match="ID token"):
        auth.complete_login(callback(a))
    assert auth.status()["signed_in"] is False


# ---- the plan permission

def test_a_token_without_the_direct_scope_keeps_the_sign_in_but_disables_plan_usage(auth, fake):
    fake.next_scope = "email offline_access openid profile resource.invoke"
    st = auth.complete_login(callback(start(auth, fake)))
    assert st["signed_in"] is True and st["plan_usage_enabled"] is False
    with pytest.raises(CA.PlanUsageDisabled, match="chatgpt.tokens.use.direct"):
        asyncio.run(auth.access_token())


# ---- the access token, refresh, sign-out

def test_a_fresh_access_token_is_returned_without_a_request(auth, fake):
    auth.complete_login(callback(start(auth, fake)))
    n = len(fake.requests)
    assert asyncio.run(auth.access_token()) == "access-1"
    assert len(fake.requests) == n


def test_near_expiry_it_refreshes_with_the_issued_client_id_and_replaces_everything_together(auth, fake, tmp_path):
    auth.complete_login(callback(start(auth, fake)))
    rec = json.loads((tmp_path / "state" / "chatgpt_auth.json").read_text())
    rec["accounts"][ISSUED]["expires_at"] = time.time() + 30
    (tmp_path / "state" / "chatgpt_auth.json").write_text(json.dumps(rec))
    assert asyncio.run(auth.access_token()) == "access-2"
    _, body, _ = fake.requests[-1]
    assert body == {"grant_type": "refresh_token", "client_id": ISSUED, "refresh_token": "refresh-1", "resource": "https://api.openai.com/v1"}
    assert "scope" not in body                                                      # omitted: the grant is retained
    saved = json.loads((tmp_path / "state" / "chatgpt_auth.json").read_text())["accounts"][ISSUED]
    assert (saved["access_token"], saved["refresh_token"]) == ("access-2", "refresh-2") and saved["expires_at"] > time.time() + 3000


def test_two_concurrent_refreshes_make_one_request(auth, fake, tmp_path):
    auth.complete_login(callback(start(auth, fake)))
    path = tmp_path / "state" / "chatgpt_auth.json"
    rec = json.loads(path.read_text())
    rec["accounts"][ISSUED]["expires_at"] = time.time() + 10
    path.write_text(json.dumps(rec))

    async def both():
        return await asyncio.gather(auth.access_token(), auth.access_token())

    assert asyncio.run(both()) == ["access-2", "access-2"]
    assert sum(1 for _, b, _ in fake.requests if b.get("grant_type") == "refresh_token") == 1


@pytest.mark.parametrize("code", ["invalid_grant", "invalid_refresh_token", "refresh_token_expired", "refresh_token_reused"])
def test_an_unusable_refresh_token_clears_the_tokens_and_asks_to_sign_in_again_keeping_the_client_id(auth, fake, tmp_path, code):
    auth.complete_login(callback(start(auth, fake)))
    path = tmp_path / "state" / "chatgpt_auth.json"
    rec = json.loads(path.read_text())
    rec["accounts"][ISSUED]["expires_at"] = time.time() - 5
    path.write_text(json.dumps(rec))
    fake.refresh_fail = code
    with pytest.raises(CA.NotSignedIn):
        asyncio.run(auth.access_token())
    kept = json.loads(path.read_text())["accounts"][ISSUED]
    assert "refresh_token" not in kept and "access_token" not in kept and kept["client_id"] == ISSUED


def test_a_network_failure_during_refresh_keeps_the_credentials(auth, fake, tmp_path):
    auth.complete_login(callback(start(auth, fake)))
    path = tmp_path / "state" / "chatgpt_auth.json"
    rec = json.loads(path.read_text())
    rec["accounts"][ISSUED]["expires_at"] = time.time() - 5
    path.write_text(json.dumps(rec))

    def boom(request):
        raise httpx.ConnectError("offline")

    auth.http = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(CA.TemporaryAuthError):
        asyncio.run(auth.access_token())
    assert json.loads(path.read_text())["accounts"][ISSUED]["refresh_token"] == "refresh-1"


def test_sign_out_revokes_and_removes_the_tokens(auth, fake, tmp_path):
    auth.complete_login(callback(start(auth, fake)))
    auth.sign_out()
    assert any(u.endswith("/api/accounts/oauth/revoke") for u, _, _ in fake.requests)
    assert auth.status()["signed_in"] is False
    with pytest.raises(CA.NotSignedIn):
        asyncio.run(auth.access_token())


def test_no_token_is_ever_logged(auth, fake, caplog):
    caplog.set_level(logging.DEBUG)
    auth.complete_login(callback(start(auth, fake)))
    asyncio.run(auth.access_token())
    text = caplog.text
    for secret in ("access-1", "refresh-1", "CODE"):
        assert secret not in text


def test_status_never_contains_a_token(auth, fake):
    auth.complete_login(callback(start(auth, fake)))
    s = json.dumps(auth.status())
    assert "access-1" not in s and "refresh-1" not in s
    assert "access_token" not in auth.status()
