"""Login paths the client code actually takes (auth.py, sso.py, socket_reauth.py)."""

import time

from .fake_client import decode_jwt_claims


def test_form_login_returns_a_jwt_pair_and_me_reads_the_top_level_profile(fake, settings):
    response = fake.login_form()
    assert response.status_code == 200
    body = response.json()
    # auth.py:338-345: both tokens, top-level, non-blank.
    assert body["access_token"].strip() and body["refresh_token"].strip()
    # socket_reauth.expires_soon: numeric exp >= 2 minutes out, else a refresh every 30 s.
    claims = decode_jwt_claims(body["access_token"])
    assert isinstance(claims["exp"], (int, float))
    assert claims["exp"] > time.time() + 120

    fake.access_token = body["access_token"]
    me = fake.get("/api/v1/auth/me")
    assert me.status_code == 200
    # auth.py:748-756: read at TOP LEVEL, no envelope.
    assert me.json() == {"email": settings.user_email, "name": settings.user_name, "credits": me.json()["credits"]}
    assert isinstance(me.json()["credits"], int)


def test_form_login_rejects_a_wrong_password_with_a_detail_string(fake):
    fake.password = "wrong"
    response = fake.login_form()
    assert response.status_code == 401
    # auth.py:372-377: detail is a str or {message}.
    assert isinstance(response.json()["detail"], (str, dict))


def test_me_without_a_bearer_is_401(fake):
    assert fake.get("/api/v1/auth/me").status_code == 401


def test_me_with_a_forged_token_is_401(fake):
    fake.login()
    header, payload, _sig = fake.access_token.split(".")
    fake.access_token = f"{header}.{payload}.AAAA"
    assert fake.get("/api/v1/auth/me").status_code == 401
