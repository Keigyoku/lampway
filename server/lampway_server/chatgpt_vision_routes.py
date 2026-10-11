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


def routes(auth, model_getter, caller_origin, *, human_session, run_probe=V.probe, on_change=lambda: None):
    pending = {}
    admissions = {}
    cookie = "lampway_chatgpt_vision"
    path = "/app/chatgpt/vision"

    def guard(request, *, authenticated=False):
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local = False
        if not local or caller_origin(request) != "user" or (not authenticated and request.headers.get("authorization")):
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

    async def ticket(request):
        if (refusal := guard(request, authenticated=True)) is not None:
            return refusal
        session = human_session(request)
        if not session:
            return JSONResponse({"detail": "Open the vision check from the authenticated Lampway Client"}, status_code=403)
        if await request.body() not in (b"", b"{}"):
            return JSONResponse({"detail": "Vision admission takes no caller-supplied settings"}, status_code=400)
        now = time.time()
        for key, value in list(admissions.items()):
            if value[3] < now:
                admissions.pop(key, None)
        while len(admissions) >= 16:
            admissions.pop(next(iter(admissions)))
        opaque = secrets.token_urlsafe(24)
        from .logredact import register_secret
        register_secret(opaque)  # redact this opaque URL capability before any access log can see it
        admissions[opaque] = (session[0], auth.vision_account_scope(), model_getter(), min(now + 120, session[1]), session[1])
        return JSONResponse({"path": path + "?ticket=" + opaque}, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    async def page(request):
        if (refusal := guard(request)) is not None:
            return refusal
        values = request.query_params.getlist("ticket")
        admission = admissions.pop(values[0], None) if len(values) == 1 and set(request.query_params) == {"ticket"} else None
        if not admission or admission[3] < time.time():
            return JSONResponse({"detail": "Open the vision check from Agent preferences in the Lampway Client"}, status_code=403)
        if admission[1] != auth.vision_account_scope() or admission[2] != model_getter():
            return JSONResponse({"detail": "Account or model changed; reopen the vision check from the Client"}, status_code=409)
        model = model_getter()
        now = time.time()
        for key, value in list(pending.items()):
            if value[3] < now:
                pending.pop(key, None)
        while len(pending) >= 16:
            pending.pop(next(iter(pending)))
        nonce, browser = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        uncertain = V._read(auth, model).get("status") in {"pending", "unknown"}
        pending[nonce] = (browser, auth.vision_account_scope(), model, min(now + 600, admission[4]), uncertain, admission[0])
        line = V.DISCLOSURE
        if uncertain:
            line += " A previous check may already have used allowance. Clicking acknowledges that uncertainty and requests a new check."
        response = HTMLResponse(BP.page(title="Lampway - ChatGPT vision", headline="Check ChatGPT image support", line=line,
            parts=(BP.status(model, strong="Model:"), BP.form(path, "Run vision check", hidden={"consent": nonce}))),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": BP.CSP})
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

    return [Route(path + "/ticket", ticket, methods=["POST"]), Route(path, page, methods=["GET"]), Route(path, check, methods=["POST"])]
