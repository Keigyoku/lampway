# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every page Lampway serves to a browser, rendered by a real headless Chromium in Night and Paper (the system's light or
dark preference), each captured to a PNG, and every request the page made counted. Chromium is forced through a proxy
that is this test's own loopback server (loopback included: ``--proxy-bypass-list=<-loopback>``), so a request to any
host, ours or not, is a line in its log: a page that asks for a font, a script or an image anywhere fails.

    LAMPWAY_CHROMIUM=<chrome-headless-shell>   without it the test skips and says why
    LAMPWAY_WEB_CAPTURES=<dir>                 keep the captures there (else the test's tmp_path)

Chromium runs with its own HOME, XDG dirs and profile under the test's directory."""

import http.server
import importlib.util
import os
import runpy
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHROME = os.environ.get("LAMPWAY_CHROMIUM", "")
_spec = importlib.util.spec_from_file_location("brand_page", ROOT / "server/lampway_server/brand_page.py")
BP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BP)
NIGHT, PAPER = (0x0E, 0x10, 0x16), (0xE4, 0xDC, 0xCB)      # tokens.json canvas: dark, light


def _server_pages() -> dict:
    """The pages the Lampway server renders, built the way app.py builds them (same template calls)."""
    form = BP.form
    return {
        "login": BP.page(title="Lampway - sign in", headline="Sign in to Lampway", line="Sign in to connect the desktop app to this server.",
                         parts=(form("/app/desktop-login", "Continue", hidden={"state": "s"}, password=True),)),
        "login_wrong": BP.page(title="Lampway - sign in", tone="error", headline="Wrong password", line="Sign in to connect the desktop app to this server.",
                               next_step="Type this server's password again.", parts=(form("/app/desktop-login", "Continue", password=True),)),
        "chatgpt_home": BP.page(title="Lampway - ChatGPT", headline="ChatGPT plan usage", line="Your ChatGPT Plus or Pro plan pays for this server's agent.",
                                parts=(form("/app/chatgpt/start", "Continue with ChatGPT"),)),
        "chatgpt_ok": BP.callback("ChatGPT", "ok", parts=(BP.status("(you@example.com).", strong="Using ChatGPT plan",
                                                                     link=("Manage usage", "https://chatgpt.com/settings/usage")),)),
        "chatgpt_cancelled": BP.callback("ChatGPT", "cancelled", reason="ChatGPT plan use was not authorized (access_denied); no code was exchanged",
                                         parts=(form("/app/chatgpt/start", "Continue with ChatGPT"),)),
        "chatgpt_expired": BP.callback("ChatGPT", "expired", reason="the callback's state does not match a sign-in attempt of ours (a stale or forged callback)"),
        "chatgpt_error": BP.callback("ChatGPT", "error", reason="the code exchange failed (HTTP 400: invalid_grant); start a fresh sign-in"),
        "hyper3d_ok": BP.callback("Hyper3D", "ok"),
        "higgsfield_cancelled": BP.callback("Higgsfield", "cancelled", reason="Higgsfield access was not authorized (access_denied)"),
    }


def _desktop_pages() -> dict:
    """The desktop app's loopback pages exactly as shipped (the generated sso_pages.py and the native header)."""
    ns = runpy.run_path(str(ROOT / "src/scripts/mixar/modules/auth/core/sso_pages.py"))
    gen = runpy.run_path(str(ROOT / "scripts/generate_sso_success_page.py"), run_name="not_main")
    native = gen["_read_c"]()
    return {"desktop_ok": ns["SUCCESS_PAGE"].decode("utf-8"), "desktop_expired": ns["EXPIRED_PAGE"].decode("utf-8"),
            "native_failure": native["FAILURE_PAGE"]}


def _site_files() -> dict:
    """The pages that link their own files: a report card (its _shared folder, as the cards' content server serves it) and
    the phone camera page (its webapp folder, as the app's camera server serves it). {path: (bytes, content type)}."""
    import mimetypes
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "server"))
    from lampway_server.cards import assets as CA
    from lampway_server.cards.content import light
    card = ('<!doctype html><html lang="en" data-lw-report="document"><head><meta charset="utf-8"><title>Boots1 receipt</title>'
            '<link rel="stylesheet" href="../_shared/report.css"></head><body><main><img class="mark" src="../_shared/lockup.svg" alt="Lampway">'
            '<h1>Boots1 receipt</h1><div class="grid"><div class="cell chosen"><p class="tag">take B</p><p>13.5 credits, read back from Tripo</p></div>'
            '<div class="cell rejected"><p class="tag">take A</p><p class="mark-rejected">rejected: the shin ridge is lost</p></div></div></main></body></html>').encode()
    files = {"/cards/c1/night.html": (card, "text/html"), "/cards/c1/paper.html": (light(card), "text/html"),
             "/cards/_shared/report.css": (CA.REPORT_CSS.encode(), "text/css"), "/cards/_shared/lockup.svg": (CA.LOCKUP_SVG.encode(), "image/svg+xml")}
    web = ROOT / "src/scripts/mixar/modules/virtual_camera/webapp"
    for f in web.rglob("*"):
        if f.is_file():
            files["/cam/" + f.relative_to(web).as_posix()] = (f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return files


class _Proxy(http.server.BaseHTTPRequestHandler):
    log = []
    pages = {}
    files = {}

    def do_GET(self):
        _Proxy.log.append(self.path)
        if not self.path.startswith("http://127.0.0.1:"):
            self.send_response(404)
            self.end_headers()
            return
        path = "/" + self.path.split("/", 3)[3].split("?")[0]
        if path in _Proxy.files:
            data, ctype = _Proxy.files[path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        name = self.path.rstrip("/").rsplit("/", 1)[-1]
        body = _Proxy.pages.get(name)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # no CSP here: the page itself must ask for nothing (the server adds brand_page.CSP on top; the desktop app's
        # loopback sends none), so the harness judges the markup, not the header
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = do_HEAD = do_GET

    def do_CONNECT(self):        # an https request through the proxy: logged, refused
        _Proxy.log.append("CONNECT " + self.path)
        self.send_response(403)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def proxy():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def _capture(tmp, port, name, scheme, path=None):
    home = tmp / "home"
    for d in ("cache", "config", "data", "run"):
        (home / d).mkdir(parents=True, exist_ok=True)
    os.chmod(home / "run", 0o700)
    out = tmp / f"{name}-{scheme}.png"
    env = {"HOME": str(home), "XDG_CACHE_HOME": str(home / "cache"), "XDG_CONFIG_HOME": str(home / "config"),
           "XDG_DATA_HOME": str(home / "data"), "XDG_RUNTIME_DIR": str(home / "run"), "PATH": "/usr/bin:/bin"}
    cmd = [CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-background-networking",
           "--disable-component-update", "--disable-sync", "--disable-default-apps", f"--user-data-dir={home / 'profile'}",
           f"--proxy-server=http://127.0.0.1:{port}", "--proxy-bypass-list=<-loopback>", "--hide-scrollbars",
           f"--blink-settings=preferredColorScheme={0 if scheme == 'night' else 1}", "--window-size=880,760",
           "--virtual-time-budget=3000", f"--screenshot={out}", f"http://127.0.0.1:{port}{path or '/page/' + name}"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert out.exists(), (r.returncode, r.stderr[-1500:])
    return out


@pytest.mark.skipif(not CHROME or not Path(CHROME).exists(), reason="no headless Chromium: set LAMPWAY_CHROMIUM")
@pytest.mark.parametrize("scheme", ["night", "paper"])
def test_every_page_renders_on_brand_and_asks_for_nothing(proxy, tmp_path, scheme):
    from PIL import Image
    pages = {**_server_pages(), **_desktop_pages()}
    _Proxy.pages = pages
    out_dir = Path(os.environ.get("LAMPWAY_WEB_CAPTURES") or tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    port = proxy.server_address[1]
    want = NIGHT if scheme == "night" else PAPER
    for name in pages:
        _Proxy.log = []
        png = _capture(out_dir, port, name, scheme)
        assert _Proxy.log == [f"http://127.0.0.1:{port}/page/{name}"], (name, _Proxy.log)
        img = Image.open(png).convert("RGB")
        corner = img.getpixel((4, 4))
        assert max(abs(a - b) for a, b in zip(corner, want)) <= 2, (name, scheme, corner, want)
        # the card (surface) is drawn, so the page is not a bare canvas
        assert len(set(img.resize((88, 76)).getdata())) > 20, (name, "the page drew almost nothing")


@pytest.mark.skipif(not CHROME or not Path(CHROME).exists(), reason="no headless Chromium: set LAMPWAY_CHROMIUM")
def test_the_card_pages_and_the_camera_page_are_on_brand_and_stay_on_their_origin(proxy, tmp_path):
    """A report card (Night, and Paper under the content server's light mark) and the phone camera page's gate: the canvas
    of the theme, the lockup drawn, and every request to the page's own origin."""
    from PIL import Image
    _Proxy.files = _site_files()
    out_dir = Path(os.environ.get("LAMPWAY_WEB_CAPTURES") or tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    port = proxy.server_address[1]
    tokens = __import__("json").loads((ROOT / "scripts/lampway/facelift/theme/tokens.json").read_text())["colour"]
    rgb = lambda hx: tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
    for name, path, want in (("card-night", "/cards/c1/night.html", rgb(tokens["surface"]["dark"])),
                             ("card-paper", "/cards/c1/paper.html", rgb(tokens["surface"]["light"])),
                             ("camera-gate", "/cam/index.html", rgb(tokens["canvas"]["dark"]))):
        _Proxy.log = []
        png = _capture(out_dir, port, name, "night", path=path)
        assert _Proxy.log and all(r.startswith(f"http://127.0.0.1:{port}/") for r in _Proxy.log), (name, _Proxy.log)
        assert any(r.endswith("lockup.svg") for r in _Proxy.log), (name, "the lockup is drawn", _Proxy.log)
        corner = Image.open(png).convert("RGB").getpixel((4, 4))
        assert max(abs(a - b) for a, b in zip(corner, want)) <= 2, (name, corner, want)
