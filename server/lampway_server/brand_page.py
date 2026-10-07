# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ONE template for every page Lampway serves to a browser: the password sign-in, the loopback OAuth callbacks
(ChatGPT, Higgsfield, Hyper3D and the next studio through ``callback``), their status pages, and (rendered at build time
by ``scripts/generate_sso_success_page.py``) the desktop app's own loopback pages and their native mirror.

Brand (DESIGN v2): the tokens (``web/workbench/tokens.css``, generated from ``theme/tokens.json``: Night, and Paper when
the system asks for light), the Lampway lockup, the site's faces (Fraunces for the headline, IBM Plex Sans for the text,
both vendored under ``web/brand/fonts`` with their OFL texts) and a calm card. Every page is self-contained: the faces and
the mark are inlined, so it makes no request of its own (no CDN, nothing after a loopback server has shut down) and it
carries no script. Text arguments are escaped; no token or secret is ever an argument.

Standard library only: the build-time generator imports this file outside the server's environment."""

import base64
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE / "web" / "brand"
TOKENS_CSS = HERE / "web" / "workbench" / "tokens.css"
FACES = (("Fraunces", "fraunces-latin-opsz-normal.woff2", "300 700"),
         ("IBM Plex Sans", "ibm-plex-sans-latin-400-normal.woff2", "400"),
         ("IBM Plex Sans", "ibm-plex-sans-latin-600-normal.woff2", "600"))
TONES = ("ok", "error", "cancelled", "expired", "info")
# The CSP every served page carries: nothing loads from anywhere (faces and mark are data: URIs), forms post to this origin.
CSP = ("default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; form-action 'self'; "
       "base-uri 'none'; frame-ancestors 'none'")
_CACHE = {}


def face_bytes() -> dict:
    """{file name: woff2 bytes} of the faces a page inlines (the generator subsets them for the desktop app's pages)."""
    return {name: (BRAND / "fonts" / name).read_bytes() for _family, name, _weight in FACES}


def faces_css(faces: dict = None) -> str:
    """The site's faces as @font-face rules with the woff2 inlined (``faces`` replaces the files: {file name: bytes})."""
    data = face_bytes() if faces is None else faces
    return "".join(
        f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;"
        f"src:url(data:font/woff2;base64,{base64.b64encode(data[name]).decode('ascii')}) format('woff2')}}"
        for family, name, weight in FACES if name in data)


def tokens_css(light_selector: str = None, night_only: bool = False) -> str:
    """The tokens as ``--lw-*`` custom properties: Night on :root, Paper when the system asks for light, or (``light_selector``)
    under that selector instead (the report cards' ``html[data-lw-theme="light"]``); ``night_only`` for a viewfinder whose
    controls sit over a live picture (the phone camera page)."""
    css = re.sub(r"/\*.*?\*/", "", TOKENS_CSS.read_text(encoding="utf-8"), flags=re.S)
    if night_only:
        return css.split("@media (prefers-color-scheme: light)", 1)[0]
    if light_selector:
        night, paper = css.split("@media (prefers-color-scheme: light)", 1)
        css = night + light_selector + " " + paper.strip()[1:].strip()[:-1].strip().replace(":root ", "", 1)
    return css


def mark_svg() -> str:
    """The Lampway lockup (crook lantern and wordmark), its own colours for both schemes."""
    return (BRAND / "lockup.svg").read_text(encoding="utf-8")


def _css(faces: dict = None) -> str:
    key = "css" if faces is None else None
    if key and key in _CACHE:
        return _CACHE[key]
    css = faces_css(faces) + tokens_css() + _LAYOUT
    if key:
        _CACHE[key] = css
    return css


def _mark() -> str:
    if "mark" not in _CACHE:
        svg = re.sub(r"<\?xml.*?\?>|<!--.*?-->", "", (BRAND / "lockup.svg").read_text(encoding="utf-8"), flags=re.S).strip()
        _CACHE["mark"] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return _CACHE["mark"]


_LAYOUT = """
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{min-height:100vh;display:grid;place-items:center;padding:32px 20px;background:var(--lw-canvas);color:var(--lw-text);
 font:400 15px/1.55 'IBM Plex Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
main{width:100%;max-width:30rem;background:var(--lw-surface);border:1px solid var(--lw-line);border-radius:14px;padding:32px 32px 28px}
.mark{display:block;height:34px;margin:0 0 28px}
.tone{display:inline-block;margin:0 0 12px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;letter-spacing:.02em}
.tone.ok{background:var(--lw-go_bed);color:var(--lw-go)}
.tone.error{background:var(--lw-stop_bed);color:var(--lw-stop)}
.tone.cancelled,.tone.info{background:var(--lw-raised);color:var(--lw-muted)}
.tone.expired{background:var(--lw-accent_bed);color:var(--lw-accent_text)}
h1{margin:0 0 10px;font:400 30px/1.15 'Fraunces',Georgia,serif;color:var(--lw-text_hi);letter-spacing:-.01em}
p{margin:0 0 10px}
.line{color:var(--lw-text)}
.next{color:var(--lw-muted)}
.detail{color:var(--lw-muted);font-size:13px;border-top:1px solid var(--lw-line);margin-top:18px;padding-top:14px}
form{margin:18px 0 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
label{display:flex;flex-direction:column;gap:6px;flex:1 1 100%;color:var(--lw-muted);font-size:13px}
input[type=password]{font:inherit;color:var(--lw-text);background:var(--lw-well);border:1px solid var(--lw-line_hi);border-radius:8px;padding:9px 12px}
input[type=password]:focus{outline:2px solid var(--lw-accent);outline-offset:1px}
button{font:600 14px 'IBM Plex Sans',system-ui,sans-serif;border-radius:8px;padding:9px 18px;cursor:pointer;border:1px solid var(--lw-line_hi);
 background:var(--lw-raised);color:var(--lw-text)}
button.primary{background:var(--lw-accent);border-color:var(--lw-accent);color:var(--lw-on_accent)}
a{color:var(--lw-accent_text)}
"""


def _e(text) -> str:
    return html.escape(str(text or ""), quote=True)


class Fragment(str):
    """Markup this module built (a form, a status line): the only HTML ``page`` accepts besides its own."""


def form(action: str, label: str, *, primary: bool = True, hidden: dict = None, password: bool = False) -> Fragment:
    """A POST form to this origin: hidden fields, an optional password field, one button."""
    fields = "".join(f'<input type="hidden" name="{_e(k)}" value="{_e(v)}">' for k, v in (hidden or {}).items())
    if password:
        fields += '<label>Password<input type="password" name="password" autocomplete="current-password" autofocus></label>'
    cls = ' class="primary"' if primary else ""
    return Fragment(f'<form method="post" action="{_e(action)}">{fields}<button type="submit"{cls}>{_e(label)}</button></form>')


def status(text: str, *, strong: str = "", link: tuple = None) -> Fragment:
    """One line of state ("Using ChatGPT plan (you@example.com). Manage usage"): bold lead, text, an optional link."""
    lead = f"<b>{_e(strong)}</b> " if strong else ""
    tail = f' <a href="{_e(link[1])}" rel="noreferrer">{_e(link[0])}</a>' if link else ""
    return Fragment(f'<p class="line">{lead}{_e(text)}{tail}</p>')


def page(*, title: str, headline: str, line: str = "", next_step: str = "", tone: str = "info", parts=(), detail: str = "",
         faces: dict = None) -> str:
    """The whole document. ``title`` names the page in the tab ("Lampway - ChatGPT"); ``headline`` the state; ``line`` one
    line of explanation; ``next_step`` what to do now; ``parts`` Fragments (forms, status lines); ``detail`` the small print.
    ``faces`` replaces the inlined woff2 files ({file name: bytes}; the generator passes subsets sized for a C literal)."""
    if tone not in TONES:
        raise ValueError(f"tone is one of {TONES}")
    for p in parts:
        if not isinstance(p, Fragment):
            raise TypeError("page() takes markup only from form() and status(): raw HTML is refused")
    word = {"ok": "Done", "error": "Not done", "cancelled": "Cancelled", "expired": "Expired", "info": ""}[tone]
    badge = f'<p class="tone {tone}">{word}</p>' if word else ""
    body = "".join(p for p in (
        badge, f"<h1>{_e(headline)}</h1>",
        f'<p class="line">{_e(line)}</p>' if line else "",
        f'<p class="next">{_e(next_step)}</p>' if next_step else "",
        *parts,
        f'<p class="detail">{_e(detail)}</p>' if detail else ""))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta name=\"color-scheme\" content=\"dark light\"><meta name=\"referrer\" content=\"no-referrer\">"
            f"<title>{_e(title)}</title><link rel=\"icon\" href=\"data:,\"><style>{_css(faces)}</style></head><body><main>"
            f"<img class=\"mark\" src=\"{_mark()}\" alt=\"Lampway\">{body}</main></body></html>")


def callback(service: str, outcome: str, *, reason: str = "", where: str = "Connections", parts=(), faces: dict = None) -> str:
    """A sign-in callback's page, the same four states for every service: ``ok``, ``cancelled`` (the person declined),
    ``expired`` (a stale or forged callback: the state matches no sign-in of ours) and ``error`` (the reason, then what to
    do). ``reason`` is the exception's own sentence (it never carries a token)."""
    title = f"Lampway - {service}"
    if outcome == "ok":
        return page(title=title, tone="ok", headline=f"Signed in to {service}",
                    line="You can close this tab and return to Lampway.", parts=parts, faces=faces)
    if outcome == "cancelled":
        return page(title=title, tone="cancelled", headline=f"{service} sign-in cancelled",
                    line=f"{service} access was not authorized, so nothing was stored.",
                    next_step=f"To try again, start the sign-in from {where} in Lampway.", detail=reason, parts=parts, faces=faces)
    if outcome == "expired":
        return page(title=title, tone="expired", headline="This sign-in link has expired",
                    line="It does not belong to a sign-in Lampway started, or that sign-in has already ended (its state does not match).",
                    next_step=f"Start a fresh sign-in from {where} in Lampway.", detail=reason, parts=parts, faces=faces)
    if outcome == "error":
        return page(title=title, tone="error", headline=f"{service} sign-in did not finish",
                    line=reason or "The sign-in could not be completed.",
                    next_step=f"Close this tab and start a fresh sign-in from {where} in Lampway.", parts=parts, faces=faces)
    raise ValueError("outcome is ok, cancelled, expired or error")


def outcome_of(exc) -> str:
    """Which callback state an exception is: declined -> cancelled, a state mismatch -> expired, anything else -> error."""
    if exc is None:
        return "ok"
    if type(exc).__name__ == "LoginDeclined":
        return "cancelled"
    if "state does not match" in str(exc):
        return "expired"
    return "error"
