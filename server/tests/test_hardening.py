"""Hardening of the server's surface.

* The server listens on loopback for one person. A request whose Host header names anything but a loopback host (or
  the configured bind host) is refused with 421: a web page that rebinds its DNS name to 127.0.0.1 then gets nothing.
* ``/app/chatgpt/start`` begins a sign-in attempt and so is a POST with a loopback Origin (a sandboxed script's GET,
  or a cross-site navigation, cannot start one), and the attempts kept in memory are capped.
* The refresh replay cache is capped too, so a client cannot grow the process without bound.
"""

from starlette.testclient import TestClient

from lampway_server.app import create_app


def test_a_request_with_a_foreign_host_header_is_refused(http):
    r = http.get("/api/v1/auth/me", headers={"host": "evil.example"})
    assert r.status_code == 421
    r = http.get("/app/chatgpt/status", headers={"host": "127.0.0.1.evil.example:8787"})
    assert r.status_code == 421


def test_loopback_hosts_and_the_bind_host_pass(http, settings):
    for host in ("127.0.0.1:8787", "localhost:8787", "[::1]:8787", f"{settings.host}:{settings.port}"):
        r = http.get("/api/v1/auth/me", headers={"host": host})
        assert r.status_code == 401, (host, r.status_code)


def test_the_bind_host_is_allowed_when_it_is_not_loopback(tmp_path, settings):
    settings.host = "203.0.113.20"
    with TestClient(create_app(settings), base_url="http://203.0.113.20:8787") as client:
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/auth/me", headers={"host": "evil.example"}).status_code == 421


def test_chatgpt_start_is_a_post_with_a_loopback_origin(http):
    assert http.get("/app/chatgpt/start").status_code == 405
    assert http.post("/app/chatgpt/start", headers={"origin": "http://evil.example"}).status_code == 403
    r = http.post("/app/chatgpt/start", headers={"origin": "http://127.0.0.1:8787"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://auth.openai.com/")
    r = http.post("/app/chatgpt/start", follow_redirects=False)        # a form post without an Origin (older browsers)
    assert r.status_code == 302


def test_the_pages_own_form_post_starts_the_sign_in_from_a_real_browser(http):
    """The page sets <meta name="referrer" content="no-referrer">, so a browser serializes the Origin of its own form POST as
    "null" (fetch: no-referrer policy, non-GET): the Captain's real browser got "cross-origin sign-in refused" on Sign in with
    ChatGPT (real-account run, 23931d7d). The browser's own Sec-Fetch-Site, which a page cannot set, tells same-origin apart; an
    attacker's no-referrer page posts cross-site and stays refused, as does a bare null."""
    page = http.get("/app/chatgpt").text
    assert '<meta name="referrer" content="no-referrer">' in page
    same = {"origin": "null", "sec-fetch-site": "same-origin"}
    r = http.post("/app/chatgpt/start", headers=same, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://auth.openai.com/")
    assert http.post("/app/chatgpt/signout", headers=same, follow_redirects=False).status_code == 303
    for hostile in ({"origin": "null", "sec-fetch-site": "cross-site"}, {"origin": "null", "sec-fetch-site": "same-site"},
                    {"origin": "null"}, {"origin": "http://evil.example", "sec-fetch-site": "same-origin"}):
        assert http.post("/app/chatgpt/start", headers=hostile, follow_redirects=False).status_code == 403, hostile


def test_the_pages_form_may_follow_the_sign_in_redirect(http):
    """A browser applies the page's CSP form-action to every redirect of its form post: with form-action 'self' the 302 to
    OpenAI was blocked and the button did nothing (the Captain's browser, after the null-Origin fix). The ChatGPT page names
    exactly the origin its start redirects to, and nothing else."""
    from urllib.parse import urlsplit
    csp = http.get("/app/chatgpt").headers["content-security-policy"]
    action = next(d.split()[1:] for d in csp.split(";") if d.strip().startswith("form-action"))
    start = http.post("/app/chatgpt/start", follow_redirects=False)
    target = urlsplit(start.headers["location"])
    assert action == ["'self'", f"{target.scheme}://{target.netloc}"], csp
    assert "form-action 'self';" in http.get("/app/docs").headers.get("content-security-policy", "form-action 'self';")


def test_the_page_starts_the_sign_in_with_a_form_post(http):
    r = http.get("/app/chatgpt")
    assert 'action="/app/chatgpt/start"' in r.text and 'method="post"' in r.text


def test_pending_sign_in_attempts_are_capped(http, app):
    for _ in range(40):
        http.post("/app/chatgpt/start", follow_redirects=False)
    assert len(app.state.chatgpt._pending) <= app.state.chatgpt.MAX_PENDING


def test_the_refresh_replay_cache_is_capped(app):
    auth = app.state.auth
    for i in range(auth.MAX_REPLAYS + 50):
        pair = auth.issue_pair()
        assert auth.refresh(pair["refresh_token"], f"key-{i}") is not None
    assert len(auth._refresh_replays) <= auth.MAX_REPLAYS
