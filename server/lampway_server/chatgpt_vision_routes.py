# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-use browser consent for the fixed ChatGPT vision check; no agent/MCP door."""
import ipaddress
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import brand_page as BP
from . import chatgpt_vision as V


def routes(auth, model_getter, caller_origin, *, run_probe=V.probe, on_change=lambda: None):
    pending = {}
    cookie = "lampway_chatgpt_vision"
    path = "/app/chatgpt/vision"

    def guard(request):
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local = False
        if not local or caller_origin(request) != "user" or request.headers.get("authorization"):
            return JSONResponse({"detail": "Vision checks require the user's local browser"}, status_code=403)
        origin = request.headers.get("origin")
        if origin:
            target = urlsplit(str(request.url))
            try:
                incoming = urlsplit(origin)
                same = incoming.scheme == target.scheme and incoming.netloc == target.netloc and incoming.path in {"", "/"}
            except ValueError:
                same = False
            if not same:
                return JSONResponse({"detail": "cross-origin vision check refused"}, status_code=403)
        if not auth.vision_account_scope():
            return JSONResponse({"detail": "Sign in and enable ChatGPT plan usage first"}, status_code=403)
        return None

    async def page(request):
        if (refusal := guard(request)) is not None:
            return refusal
        model = model_getter()
        now = time.time()
        for key, value in list(pending.items()):
            if value[3] < now:
                pending.pop(key, None)
        while len(pending) >= 16:
            pending.pop(next(iter(pending)))
        nonce, browser = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        uncertain = V._read(auth, model).get("status") in {"pending", "unknown"}
        pending[nonce] = (browser, auth.vision_account_scope(), model, now + 600, uncertain)
        line = V.DISCLOSURE
        if uncertain:
            line += " A previous check may already have used allowance. Clicking acknowledges that uncertainty and requests a new check."
        response = HTMLResponse(BP.page(title="Lampway - ChatGPT vision", headline="Check ChatGPT image support", line=line,
            parts=(BP.status(model, strong="Model:"), BP.form(path, "Run vision check", hidden={"consent": nonce}))),
            headers={"Cache-Control": "no-store"})
        response.set_cookie(cookie, browser, httponly=True, samesite="strict", path=path, max_age=600)
        return response

    async def check(request):
        if (refusal := guard(request)) is not None:
            return refusal
        raw = await request.body()
        if len(raw) > 1024 or request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
            return JSONResponse({"detail": "Use the displayed consent form"}, status_code=400)
        try:
            form = parse_qs(raw.decode("ascii"), strict_parsing=True)
        except (ValueError, UnicodeDecodeError):
            form = {}
        if set(form) != {"consent"} or len(form["consent"]) != 1:
            return JSONResponse({"detail": "Use the displayed consent form"}, status_code=400)
        attempt = pending.pop(form["consent"][0], None)
        if not attempt or not secrets.compare_digest(request.cookies.get(cookie, ""), attempt[0]) or attempt[3] < time.time():
            return JSONResponse({"detail": "Consent expired; reopen the vision check page"}, status_code=403)
        if auth.vision_account_scope() != attempt[1] or model_getter() != attempt[2]:
            return JSONResponse({"detail": "Account or model changed; reopen the vision check page"}, status_code=409)
        try:
            result = await run_probe(auth, attempt[2], consent=True, acknowledge_unknown=attempt[4])
        except Exception:
            return JSONResponse({"detail": "Vision check did not complete. Images remain withheld; reopen the page to review before retrying."}, status_code=502)
        finally:
            on_change()
        response = JSONResponse(result, headers={"Cache-Control": "no-store"})
        response.delete_cookie(cookie, path=path)
        return response

    return [Route(path, page, methods=["GET"]), Route(path, check, methods=["POST"])]
