"""The ASGI application: REST routes the client calls plus the agent WebSocket."""

from html import escape
from urllib.parse import parse_qs, urlencode

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from .auth import Auth
from .config import Settings

_PKCE_FIELDS = ("port", "code_challenge", "code_challenge_method", "state", "source")


def render_login_page(fields: dict, error: str = "") -> str:
    hidden = "".join(
        f'<input type="hidden" name="{name}" value="{escape(str(fields.get(name, "")), quote=True)}">'
        for name in _PKCE_FIELDS
    )
    notice = f'<p class="error">{escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Lampway - sign in</title>
<style>body{{font-family:sans-serif;max-width:28em;margin:4em auto}} .error{{color:#b00}}</style></head>
<body><h1>Lampway</h1><p>Sign in to connect the desktop app to this server.</p>{notice}
<form method="post" action="/app/desktop-login">{hidden}
<label>Password <input type="password" name="password" autofocus></label>
<button type="submit">Continue</button></form></body></html>"""


def bearer_token(request: Request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def unauthorized(message="Not authenticated"):
    return JSONResponse({"detail": message}, status_code=401)


def create_app(settings: Settings, provider=None) -> Starlette:
    auth = Auth(
        secret=settings.resolve_jwt_secret(),
        email=settings.user_email,
        name=settings.user_name,
        password=settings.user_password,
        access_ttl_s=settings.access_token_ttl_s,
        credits=settings.fake_credits,
    )

    async def login(request: Request):
        form = parse_qs((await request.body()).decode("utf-8", "replace"))
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        if not auth.check_password(username, password):
            return unauthorized("Incorrect username or password")
        return JSONResponse(auth.issue_pair())

    async def me(request: Request):
        token = bearer_token(request)
        if not token or auth.verify_access(token) is None:
            return unauthorized()
        return JSONResponse(auth.profile())

    # ---- PKCE desktop SSO: the page the client opens in the browser (sso.py:154-168)
    def _loopback_redirect(fields):
        port = fields.get("port", "")
        if not port.isdigit():
            return JSONResponse({"detail": "port must be numeric"}, status_code=400)
        code = auth.begin_pkce(fields.get("code_challenge", ""), fields.get("code_challenge_method", ""))
        if code is None:
            return JSONResponse({"detail": "code_challenge with method S256 is required"}, status_code=400)
        query = urlencode({"code": code, "state": fields.get("state", "")})
        return RedirectResponse(f"http://127.0.0.1:{port}/?{query}", status_code=302)

    async def desktop_login_get(request: Request):
        fields = {k: v for k, v in request.query_params.items()}
        if not fields.get("code_challenge"):
            return JSONResponse({"detail": "code_challenge with method S256 is required"}, status_code=400)
        if not auth.password_required():
            return _loopback_redirect(fields)
        return HTMLResponse(render_login_page(fields))

    async def desktop_login_post(request: Request):
        form = parse_qs((await request.body()).decode("utf-8", "replace"))
        fields = {k: v[0] for k, v in form.items()}
        if auth.password_required() and not auth.check_password(auth.email, fields.get("password", "")):
            return HTMLResponse(render_login_page(fields, error="Wrong password."), status_code=401)
        return _loopback_redirect(fields)

    async def desktop_token(request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = {}
        pair = auth.exchange_code(body.get("code"), body.get("code_verifier"))
        if pair is None:
            return JSONResponse({"detail": "Invalid or expired authorization code"}, status_code=400)
        return JSONResponse(pair)

    async def refresh(request: Request):
        try:
            body = await request.json()
        except ValueError:
            body = {}
        pair = auth.refresh(body.get("refresh_token"), request.headers.get("idempotency-key"))
        if pair is None:
            return unauthorized("Invalid refresh token")
        return JSONResponse(pair)

    routes = [
        Route("/api/v1/auth/login", login, methods=["POST"]),
        Route("/api/v1/auth/me", me, methods=["GET"]),
        Route("/api/v1/auth/desktop/token", desktop_token, methods=["POST"]),
        Route("/api/v1/auth/refresh", refresh, methods=["POST"]),
        Route("/app/desktop-login", desktop_login_get, methods=["GET"]),
        Route("/app/desktop-login", desktop_login_post, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    app.state.settings = settings
    app.state.auth = auth
    app.state.provider = provider
    return app
