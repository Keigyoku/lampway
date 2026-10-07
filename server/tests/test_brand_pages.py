# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain (2026-10-06): every page Lampway serves to a browser is on-brand, not a basic white HTML page - "that's how
the Sign in with ChatGPT page looked when I signed in originally". One template (lampway_server/brand_page.py) renders the
password sign-in, every loopback OAuth callback and status page, and (at build time) the desktop app's own loopback pages.
These tests hold the template to the brand and every auth and loopback module to the template."""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from lampway_server import brand_page as BP

SERVER = Path(__file__).resolve().parents[1]
ROOT = SERVER.parent
# The modules that answer a browser during a sign-in or on a loopback port (server and desktop app).
AUTH_AND_LOOPBACK = [SERVER / "lampway_server" / n for n in ("app.py", "chatgpt_auth.py", "mcp_oauth.py", "higgsfield_auth.py")] + \
    sorted((SERVER / "lampway_server" / "connections").glob("*.py")) + \
    [ROOT / "src/scripts/mixar/modules/auth/core" / n for n in ("sso.py", "auth.py")]
HTML_TAG = re.compile(r"<\s*(!doctype|html|body|p|h[1-6]|form|button|div|main|style)\b", re.I)


def raw_html_literals(source: str) -> list:
    """Every string constant (f-string parts included) that holds an HTML tag."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value.decode("utf-8", "replace") if isinstance(node.value, bytes) else node.value
            if HTML_TAG.search(text):
                out.append((node.lineno, text[:60]))
    return out


@pytest.mark.parametrize("path", [p for p in AUTH_AND_LOOPBACK if p.exists()], ids=lambda p: p.name)
def test_no_auth_or_loopback_module_writes_its_own_html(path):
    """The template is the only place a page is written: a callback that builds HTML by hand is the white page again."""
    assert raw_html_literals(path.read_text(encoding="utf-8")) == [], path


def test_the_scan_sees_the_old_pages():
    """The scan's falsifier: app.py as it was before the template (c0872d90) wrote its pages by hand, and the scan finds them."""
    old = subprocess.run(["git", "-C", str(ROOT), "show", "c0872d90:server/lampway_server/app.py"], capture_output=True, text=True)
    if old.returncode != 0:
        pytest.skip("c0872d90 is not in this clone")
    found = raw_html_literals(old.stdout)
    assert len(found) >= 8 and any("Sign-in failed" in t for _, t in found), found


def test_every_html_response_in_the_server_goes_through_html_page():
    tree = ast.parse((SERVER / "lampway_server" / "app.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "HTMLResponse"]
    # html_page itself, and the cockpit page (its own document, web/workbench/index.html, with the tokens and its CSP)
    allowed = {"text", "(_WB_PAGE / 'index.html').read_text(encoding='utf-8')"}
    assert sorted(ast.unparse(c.args[0]) for c in calls) == sorted(allowed), [ast.unparse(c.args[0]) for c in calls]


@pytest.mark.parametrize("outcome", ["ok", "cancelled", "expired", "error"])
def test_each_callback_state_has_a_headline_a_line_and_a_next_step(outcome):
    page = BP.callback("ChatGPT", outcome, reason="the sign-in returned an error: server_error")
    h1 = re.search(r"<h1>(.*?)</h1>", page).group(1)
    assert h1 == {"ok": "Signed in to ChatGPT", "cancelled": "ChatGPT sign-in cancelled", "expired": "This sign-in link has expired",
                  "error": "ChatGPT sign-in did not finish"}[outcome]
    if outcome == "ok":
        assert "You can close this tab and return to Lampway." in page
    else:
        assert 'class="next"' in page and "in Lampway." in page, "the next step is said"
    assert "<script" not in page.lower()


def test_the_states_are_told_apart_from_the_exceptions():
    class LoginDeclined(Exception):
        pass
    assert BP.outcome_of(None) == "ok"
    assert BP.outcome_of(LoginDeclined("x")) == "cancelled"
    assert BP.outcome_of(ValueError("the callback's state does not match a sign-in attempt of ours (a stale or forged callback)")) == "expired"
    assert BP.outcome_of(ValueError("the code exchange failed (HTTP 400: invalid_grant); start a fresh sign-in")) == "error"


def test_a_page_loads_nothing_and_follows_the_system_theme():
    page = BP.page(title="Lampway - x", headline="h", line="l", parts=(BP.form("/app/x", "Go"),))
    resources = re.findall(r"""(?:src|href)\s*=\s*["']([^"']+)""", page) + re.findall(r"url\(([^)]+)\)", page)
    assert resources and all(r.startswith("data:") or r.startswith("/") for r in resources), resources
    assert "@import" not in page and "<script" not in page.lower()
    css = page[page.index("<style>"):page.index("</style>")]
    assert "@media (prefers-color-scheme: light)" in css, "Paper when the system asks for light"
    assert "font-family:'Fraunces'" in css and "font-family:'IBM Plex Sans'" in css, "the site's faces, inlined"
    assert "default-src 'none'" in BP.CSP and "font-src data:" in BP.CSP


def test_text_is_escaped_and_raw_markup_is_refused():
    page = BP.page(title="t", headline="<img src=x onerror=alert(1)>", line="a & b")
    assert "<img src=x" not in page and "&lt;img" in page
    with pytest.raises(TypeError):
        BP.page(title="t", headline="h", parts=("<p>raw</p>",))


def test_the_served_pages_carry_the_brand_and_its_csp(settings, provider, tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from lampway_server.app import create_app
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787", follow_redirects=False) as http:
        for path, params in (("/app/chatgpt", None), ("/app/higgsfield", None), ("/auth/callback", {"code": "x", "state": "forged"}),
                             ("/auth/higgsfield/callback", {"code": "x", "state": "forged"}), ("/auth/hyper3d/callback", {"code": "x", "state": "forged"})):
            r = http.get(path, params=params)
            assert r.headers["content-type"].startswith("text/html"), path
            assert r.headers.get("content-security-policy") == BP.CSP, path
            assert 'class="mark"' in r.text and "--lw-canvas" in r.text, path
        assert "This sign-in link has expired" in http.get("/auth/callback", params={"code": "x", "state": "forged"}).text
        # the cockpit page (contract 10) takes the same faces and mark from its own origin
        for _family, name, _weight in BP.FACES:
            r = http.get(f"/app/workbench/static/{name}")
            assert r.status_code == 200 and r.headers["content-type"] == "font/woff2" and r.content[:4] == b"wOF2", name
        assert http.get("/app/workbench/static/lockup.svg").headers["content-type"].startswith("image/svg+xml")


def test_the_desktop_apps_loopback_pages_are_rendered_from_the_template():
    """sso_pages.py and the native mirror are generated by scripts/generate_sso_success_page.py from brand_page; --check
    fails when either is stale."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts/generate_sso_success_page.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
