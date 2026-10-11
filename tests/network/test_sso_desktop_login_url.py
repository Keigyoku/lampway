# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Desktop-login URL contract with the website.

A first-time user who signs up instead of logging in must come back to the
app: the website keys that path on ``source=desktop`` and the window must be
long enough for an email OTP plus the onboarding questions.
"""

from urllib.parse import parse_qs, urlparse

from mixar.modules.auth.core import sso


def test_desktop_login_url_carries_pkce_state_and_source(monkeypatch):
    monkeypatch.setattr(sso, "get_frontend_url", lambda: "https://mixar.app")

    url = urlparse(sso.desktop_login_url(51731, "chal-_1", "st-_2"))

    assert (url.scheme, url.netloc, url.path) == ("https", "mixar.app", "/app/desktop-login")
    assert parse_qs(url.query) == {
        "port": ["51731"],
        "code_challenge": ["chal-_1"],
        "code_challenge_method": ["S256"],
        "state": ["st-_2"],
        "source": ["desktop"],
    }


def test_login_window_covers_a_browser_signup():
    assert sso.SSO_LOGIN_TIMEOUT_S >= 600


def test_loopback_signin_stores_pair_without_browser_or_callback_server(monkeypatch):
    from types import SimpleNamespace
    opened = []; stored = []
    monkeypatch.setattr(sso, "get_server_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(sso.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(sso, "start_callback_server", lambda _: (_ for _ in ()).throw(AssertionError("browser callback launched")))
    monkeypatch.setattr(sso.requests, "post", lambda url, **kw: SimpleNamespace(status_code=200, json=lambda: {
        "access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}))
    monkeypatch.setattr(sso, "store_login_token_pair", lambda a, r: (stored.append((a, r)) or True, ""))
    result = sso.sso_login()
    assert result["success"] and stored == [("synthetic-access", "synthetic-refresh")] and opened == []
