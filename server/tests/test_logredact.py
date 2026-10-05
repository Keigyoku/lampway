"""No OAuth secret belongs in a log. Uvicorn's access logger writes the request line, and the sign-in callback's query
carries the authorization `code`, `state` and `client_id`; the redaction runs when the record is made, so it holds whatever
handler or logging configuration uvicorn installs afterwards."""

import logging

from lampway_server import logredact
from lampway_server.app import create_app

CODE = "ac_SECRETCODE_1234567890"
STATE = "st-SECRETSTATE-abcdef"
JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl"


def test_sensitive_query_values_are_replaced_and_the_rest_is_kept():
    out = logredact.redact_text(f"/auth/callback?code={CODE}&state={STATE}&client_id=oaiapp_X&scope=openid&foo=bar")
    assert CODE not in out and STATE not in out and "oaiapp_X" not in out
    assert "scope=openid" in out and "foo=bar" in out and out.count("[redacted]") == 3
    assert "/auth/callback?" in out


def test_a_token_shaped_value_is_replaced_anywhere():
    assert JWT not in logredact.redact_text(f"refresh failed for Bearer {JWT} today")


def test_the_access_log_line_is_redacted_after_create_app(settings):
    create_app(settings)
    seen = []

    class Grab(logging.Handler):
        def emit(self, record):
            seen.append(self.format(record))

    log = logging.getLogger("uvicorn.access")        # uvicorn gives it its own handler and propagate=False; take its seat
    handler, old_level = Grab(), log.level
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET",
                 f"/auth/callback?code={CODE}&state={STATE}&client_id=oaiapp_X", "1.1", 200)
    finally:
        log.removeHandler(handler)
        log.setLevel(old_level)
    text = "\n".join(seen)
    assert "/auth/callback" in text and CODE not in text and STATE not in text and "oaiapp_X" not in text


def test_the_callback_error_message_does_not_echo_a_long_provider_error(http):
    from urllib.parse import parse_qs, urlparse
    start = http.post("/app/chatgpt/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    r = http.get("/auth/callback", params={"error": "x" * 500, "state": state, "code": CODE})
    assert r.status_code == 400 and CODE not in r.text
    assert "x" * 100 not in r.text, "an error value from the query is capped, not echoed whole"
