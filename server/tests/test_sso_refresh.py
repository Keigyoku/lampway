"""PKCE desktop SSO (sso.py:146-215) and refresh rotation (auth.py:610-709)."""

import uuid

from .fake_client import pkce_pair


def test_desktop_login_redirects_to_the_loopback_with_code_and_the_same_state(fake):
    response = fake.login_pkce()
    assert response.status_code == 200, response.text
    # sso.py:96-98 — the callback must echo the exact state.
    assert fake.callback_state is not None
    body = response.json()
    tokens = body.get("data", body)  # sso.py:203: top level or under data
    assert tokens["access_token"].strip() and tokens["refresh_token"].strip()
    fake.access_token = tokens["access_token"]
    assert fake.get("/api/v1/auth/me").status_code == 200


def test_desktop_login_page_refuses_the_wrong_password(fake):
    response = fake.login_pkce(password="nope")
    # No redirect to the loopback happened: the client's callback server would still be waiting.
    assert response.status_code in (401, 403)
    assert "location" not in {k.lower() for k in response.headers}


def test_desktop_login_without_a_code_challenge_is_a_400(fake):
    response = fake.http.get("/app/desktop-login", params={"port": 51731, "state": "x"},
                             follow_redirects=False)
    assert response.status_code == 400


def test_token_exchange_rejects_a_wrong_verifier_and_a_reused_code(fake):
    verifier, challenge = pkce_pair()
    page = fake.http.post("/app/desktop-login", data={
        "port": 51731, "code_challenge": challenge, "code_challenge_method": "S256",
        "state": "s", "source": "desktop", "password": fake.password}, follow_redirects=False)
    assert page.status_code in (302, 303)
    code = page.headers["location"].split("code=")[1].split("&")[0]

    wrong = fake.exchange_code(code, "not-the-verifier")
    assert wrong.status_code == 400
    assert isinstance(wrong.json()["detail"], (str, dict))  # sso.py:207-211
    # The code is single-use: it was consumed by the failed attempt.
    again = fake.exchange_code(code, verifier)
    assert again.status_code == 400


def test_refresh_rotates_the_pair_and_the_old_refresh_token_is_dead(fake):
    fake.login()
    old_refresh = fake.refresh_token
    response = fake.refresh()
    assert response.status_code == 200
    pair = response.json()
    assert pair["access_token"].strip() and pair["refresh_token"].strip()
    assert pair["refresh_token"] != old_refresh
    # Second use of the consumed token: 401 makes the client relogin (auth.py:672-679).
    assert fake.refresh(refresh_token=old_refresh).status_code == 401


def test_refresh_replayed_with_the_same_idempotency_key_returns_the_same_pair(fake):
    fake.login()
    key = str(uuid.uuid4())
    first = fake.refresh(idempotency_key=key)
    assert first.status_code == 200
    # The client replays key + the SAME (now consumed) refresh token after a timeout (auth.py:401-409).
    replay = fake.refresh(idempotency_key=key)
    assert replay.status_code == 200
    assert replay.json()["access_token"] == first.json()["access_token"]
    assert replay.json()["refresh_token"] == first.json()["refresh_token"]


def test_refresh_with_an_unknown_token_is_401(fake):
    assert fake.refresh(refresh_token="garbage").status_code == 401
