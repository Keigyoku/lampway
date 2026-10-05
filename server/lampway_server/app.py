"""The ASGI application: REST routes the client calls plus the agent WebSocket."""

from html import escape
from urllib.parse import parse_qs, urlencode, urlparse

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route, WebSocketRoute

from .agent.providers import make_provider, make_swarm_provider
from .agent.turns import AgentHub
from .agent_settings import AgentSettingsStore
from .auth import Auth
from .chatgpt_auth import ChatGPTAuth, LoginDeclined, LoginError
from .config import Settings
from .rest import stub_routes
from .ws import AgentSocket, ConnectionHub

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


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def host_allowed(host_header: str, bind_host: str) -> bool:
    """True when the request's Host names this server: a loopback name or the configured bind host. Anything else
    (a DNS name rebound to 127.0.0.1, a look-alike) is not us."""
    raw = (host_header or "").strip()
    if not raw:
        return False
    try:
        hostname = urlparse(f"//{raw}").hostname or ""
    except ValueError:
        return False
    return hostname in LOOPBACK_HOSTS or (bool(bind_host) and hostname == bind_host.strip("[]").lower())


class HostGuard:
    """ASGI middleware: 421 for every HTTP request (and a refused WebSocket) whose Host is not ours."""

    def __init__(self, app, bind_host: str):
        self.app = app
        self.bind_host = bind_host

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"host"), "")
            if not host_allowed(host, self.bind_host):
                if scope["type"] == "http":
                    response = JSONResponse({"detail": "Misdirected request: this server answers only its own host"},
                                            status_code=421)
                    await response(scope, receive, send)
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)


def loopback_origin(request: Request) -> bool:
    """A missing Origin (a plain form post) or one naming a loopback host."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        return (urlparse(origin).hostname or "") in LOOPBACK_HOSTS
    except ValueError:
        return False


def bearer_token(request: Request):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def unauthorized(message="Not authenticated"):
    return JSONResponse({"detail": message}, status_code=401)


def create_app(settings: Settings, provider=None, chatgpt_auth=None, swarm_provider_factory=None) -> Starlette:
    chatgpt = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
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

    # ---- Sign in with ChatGPT (plan usage): the local pages. Loopback only; they start and finish the documented OAuth flow
    def _chatgpt_page(body: str, status_code: int = 200) -> HTMLResponse:
        st = chatgpt.status()
        if st["signed_in"] and st["plan_usage_enabled"]:
            head = (f'<p><b>Using ChatGPT plan</b> ({escape(st["email"] or "signed in")}). '
                    f'<a href="{st["manage_usage_url"]}">Manage usage</a></p>'
                    '<form method="post" action="/app/chatgpt/signout"><button>Sign out</button></form>')
        elif st["signed_in"]:
            head = ('<p>Signed in, but ChatGPT plan usage is not enabled for this sign-in. '
                    '<a href="/app/chatgpt/start">Enable it</a> or use an API key.</p>')
        else:
            head = '<form method="post" action="/app/chatgpt/start"><button>Continue with ChatGPT</button></form>'
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>Lampway - ChatGPT plan</title>
<style>body{{font-family:sans-serif;max-width:34em;margin:4em auto}}</style></head><body><h1>Lampway</h1>
<h2>ChatGPT plan usage</h2>{body}{head}
<p style="color:#555">Your ChatGPT Plus or Pro plan pays for this server's agent. Tokens stay in this machine's state directory;
nothing is sent anywhere but OpenAI. Image generation is not available on this route.</p></body></html>""", status_code=status_code)

    async def chatgpt_home(request: Request):
        return _chatgpt_page("")

    async def chatgpt_start(request: Request):
        """Begins a sign-in attempt, so it is a POST from a loopback page: a sandboxed script's GET or a cross-site
        navigation cannot start one."""
        if not loopback_origin(request):
            return JSONResponse({"detail": "cross-origin sign-in refused"}, status_code=403)
        return RedirectResponse(chatgpt.start_login().url, status_code=302)

    async def chatgpt_callback(request: Request):
        import asyncio
        query = {k: v for k, v in request.query_params.items()}
        try:
            await asyncio.to_thread(chatgpt.complete_login, query)
        except LoginDeclined as exc:
            return _chatgpt_page(f"<p>ChatGPT plan use was not authorized ({escape(str(exc))}). You can try again.</p>")
        except LoginError as exc:
            return _chatgpt_page(f"<p class='error'>Sign-in failed: {escape(str(exc))}</p>", status_code=400)
        except Exception as exc:  # noqa: BLE001 - shown to the person at the keyboard, never with a token
            return _chatgpt_page(f"<p class='error'>Sign-in could not finish: {escape(type(exc).__name__)}</p>", status_code=502)
        return _chatgpt_page("<p>Signed in.</p>")

    async def chatgpt_status(request: Request):
        return JSONResponse(chatgpt.status())

    async def chatgpt_signout(request: Request):
        if not loopback_origin(request):
            return JSONResponse({"detail": "cross-origin sign-out refused"}, status_code=403)
        import asyncio
        await asyncio.to_thread(chatgpt.sign_out)
        return RedirectResponse("/app/chatgpt", status_code=303)

    routes = [
        Route("/app/chatgpt", chatgpt_home, methods=["GET"]),
        Route("/app/chatgpt/start", chatgpt_start, methods=["POST"]),
        Route("/auth/callback", chatgpt_callback, methods=["GET"]),
        Route("/app/chatgpt/status", chatgpt_status, methods=["GET"]),
        Route("/app/chatgpt/signout", chatgpt_signout, methods=["POST"]),
        Route("/api/v1/auth/login", login, methods=["POST"]),
        Route("/api/v1/auth/me", me, methods=["GET"]),
        Route("/api/v1/auth/desktop/token", desktop_token, methods=["POST"]),
        Route("/api/v1/auth/refresh", refresh, methods=["POST"]),
        Route("/app/desktop-login", desktop_login_get, methods=["GET"]),
        Route("/app/desktop-login", desktop_login_post, methods=["POST"]),
    ]
    store = AgentSettingsStore(settings.state_dir)
    routes += stub_routes(auth, store, settings)
    hub = ConnectionHub()
    if swarm_provider_factory is None and provider is None:        # the configured provider's cheap swarm model
        swarm_provider_factory = lambda label: make_swarm_provider(settings, label)  # noqa: E731
    agent = AgentHub(provider if provider is not None else make_provider(settings, chatgpt_auth=chatgpt),
                     swarm_provider_factory=swarm_provider_factory)

    async def agent_ws(websocket):
        await AgentSocket(websocket, websocket.path_params["instance_id"], auth, hub, agent=agent).run()

    routes.append(WebSocketRoute("/api/agent/ws/{instance_id}", agent_ws))

    async def swarm_status(request: Request):
        token = bearer_token(request)
        if not token or auth.verify_access(token) is None:
            return unauthorized()
        return JSONResponse({"swarms": {sid: {"parent_session": sw.parent_session, "collected": sw.collected,
                                              "workers": [w.detail() for w in sw.workers]}
                                        for sid, sw in agent.swarm.swarms.items()}})

    async def swarm_cancel(request: Request):
        """The owner's stop button for one worker (the same effect as the orchestrator's swarm_cancel tool)."""
        token = bearer_token(request)
        if not token or auth.verify_access(token) is None:
            return unauthorized()
        swarm = agent.swarm.swarms.get(request.path_params["swarm_id"])
        worker = next((w for w in swarm.workers if w.id == request.path_params["worker"]), None) if swarm else None
        if worker is None:
            return JSONResponse({"detail": "no such worker"}, status_code=404)
        agent.swarm.cancel_worker(worker)
        return JSONResponse(worker.public())

    routes.append(Route("/app/swarm", swarm_status, methods=["GET"]))
    routes.append(Route("/app/swarm/{swarm_id}/cancel/{worker}", swarm_cancel, methods=["POST"]))
    app = Starlette(routes=routes)
    app.add_middleware(HostGuard, bind_host=settings.host)
    app.state.hub = hub
    app.state.settings = settings
    app.state.auth = auth
    app.state.store = store
    app.state.provider = provider
    app.state.chatgpt = chatgpt
    return app
