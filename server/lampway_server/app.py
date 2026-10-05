"""The ASGI application: REST routes the client calls plus the agent WebSocket."""

import json
import asyncio
import os
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route, WebSocketRoute

from .agent.providers import make_provider, make_swarm_provider
from .agent.turns import AgentHub
from .agent_settings import AgentSettingsStore
from .auth import Auth
from .chatgpt_auth import ChatGPTAuth, LoginDeclined, LoginError
from . import higgsfield_auth as HFA
from .higgsfield_auth import HiggsfieldAuth
from .config import Settings
from .jobqueue import BadJob, JobQueue, UnknownService
from . import dictation, logredact, matgen, provider_prefs, videojobs
from .ledger import Ledger, LedgerError
from .prompts.service import PromptService
from .prompts.library import LibraryError
from .prompts.render import RenderError
from .assetsearch import AssetIndex
from .mcp import McpServer, parse as mcp_parse
from .rest import envelope, stub_routes
from .ws import AgentSocket, ConnectionHub, bearer_from
from starlette.responses import Response

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


async def _json_body(request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def default_studio_service():
    """The Studio service over the project root and, when ``LAMPWAY_STUDIO_SHELF`` names it, the owner's shelf of AXI drivers."""
    from .agent.server_tools import project_root
    from .studios.service import StudioService
    return StudioService(project_root(), shelf=os.environ.get("LAMPWAY_STUDIO_SHELF") or None)


def unauthorized(message="Not authenticated"):
    return JSONResponse({"detail": message}, status_code=401)


def default_job_backends(settings: Settings) -> dict:
    """The generation backends this server can run: OpenRouter's images API when its key resolves, else none (and the
    catalog stays empty, which hides the client's generation tabs rather than offering a job that cannot run)."""
    from . import imagegen
    from .agent.providers.openrouter import KeyMissing, resolve_api_key
    try:
        resolve_api_key()
    except KeyMissing:
        return {}
    return {"image_gen": imagegen.openrouter_image_backend}


def create_app(settings: Settings, provider=None, chatgpt_auth=None, swarm_provider_factory=None, job_backends=None, transcriber=None, studio_service=None, video=None, higgsfield_auth=None, prompts=None, job_services=None) -> Starlette:
    logredact.install()          # no OAuth code/state/token in any log line, uvicorn's access log included
    provider_prefs.apply(settings, provider_prefs.load(settings.state_dir))        # the owner's saved provider choices win over the environment
    chatgpt = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
    auth = Auth(
        secret=settings.resolve_jwt_secret(),
        email=settings.user_email,
        name=settings.user_name,
        password=settings.user_password,
        access_ttl_s=settings.access_token_ttl_s,
        credits=settings.fake_credits,
        store_path=settings.state_dir / "refresh_tokens.json",
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
    hub = ConnectionHub()
    studio = studio_service if studio_service is not None else default_studio_service()
    hf_auth = higgsfield_auth or HiggsfieldAuth(settings.state_dir, redirect_port=settings.port)      # ONE per server: refresh tokens rotate
    video_system = video if video is not None else videojobs.build_default(settings, hf_auth, Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects"))
    prompt_service = prompts if prompts is not None else PromptService.from_env(settings.state_dir)
    jobs = JobQueue(default_job_backends(settings) if job_backends is None else job_backends, hub,
                    f"http://{settings.host}:{settings.port}", model_labels={"image_gen": settings.openrouter_image_model},
                    video=video_system, approvals=studio.approvals_store, prompts=prompt_service, registry=job_services)
    video_system.jobs = jobs
    for gate_action in ("higgsfield.job", "higgsfield.question", "service.job"):          # the captain's click reaches the waiting job through the Studios' confirm
        studio.register_gate(gate_action, lambda a, answer: jobs.resolve_approval(a.id, True, answer), lambda a: jobs.resolve_approval(a.id, False))
    routes += stub_routes(auth, store, settings, jobs)
    if swarm_provider_factory is None and provider is None:        # the configured provider's cheap swarm model
        swarm_provider_factory = lambda label: make_swarm_provider(settings, label, chatgpt_auth=chatgpt)  # noqa: E731  (one sign-in)
    agent = AgentHub(provider if provider is not None else make_provider(settings, chatgpt_auth=chatgpt),
                     swarm_provider_factory=swarm_provider_factory, studio=studio, video=video_system, prompts=prompt_service, jobs=jobs)

    async def agent_ws(websocket):
        await AgentSocket(websocket, websocket.path_params["instance_id"], auth, hub, agent=agent, jobs=jobs).run()

    # ---- the job queue (jobqueue.py): the client's generation surfaces
    def _bearer_ok(request: Request) -> bool:
        token = bearer_token(request)
        return bool(token) and auth.verify_access(token) is not None

    async def job_submit(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        try:
            body = await request.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        try:
            job = jobs.submit(str(body.get("service") or ""), str(body.get("model") or ""), body.get("payload"),
                              body.get("idempotency_key") or None, request.headers.get("x-mixar-job-origin", "user"))
        except (UnknownService, BadJob) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        return JSONResponse(envelope(jobs.snapshot(job)))

    async def job_get(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        job = jobs.get(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"detail": "no such job"}, status_code=404)
        return JSONResponse(envelope(jobs.snapshot(job)))

    async def job_cancel(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        job = jobs.cancel(request.path_params["job_id"])
        if job is None:
            return JSONResponse({"detail": "no such job"}, status_code=404)
        return JSONResponse(envelope(jobs.snapshot(job)))

    async def job_info(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        service = request.path_params["job_type"]
        return JSONResponse(envelope({"service": service, "available": service in jobs.backends, "queue_length": 0}))

    async def job_file(request: Request):
        found = jobs.file(request.path_params["token"], request.path_params["name"])
        if found is None:
            return JSONResponse({"detail": "no such file"}, status_code=404)
        data, media_type = found
        return Response(data, media_type=media_type, headers={"Content-Length": str(len(data)), "Cache-Control": "private, max-age=3600"})

    async def matgen_route(request: Request):
        """A procedural material from a prompt, by the agent's own model (matgen.py)."""
        if not _bearer_ok(request):
            return unauthorized()
        try:
            body = await request.json()
        except ValueError:
            body = {}
        prompt = str((body or {}).get("prompt") or "").strip() if isinstance(body, dict) else ""
        if not prompt:
            return JSONResponse({"detail": "prompt is required"}, status_code=422)
        try:
            material = await matgen.generate(agent.provider, prompt, str(body.get("pipeline") or "fast"))
        except matgen.BadScript as exc:
            return JSONResponse({"detail": f"no usable script: {exc}"}, status_code=502)
        except Exception as exc:  # noqa: BLE001 - the provider failed; the reason goes to the person, never a token
            return JSONResponse({"detail": f"material generation failed: {type(exc).__name__}"}, status_code=502)
        return JSONResponse(material.as_dict())

    mcp = McpServer(hub, agent)
    assets = AssetIndex(settings.state_dir)

    def _metadata(value):
        """The form's ``metadata`` JSON list, or None when it is not a list of objects."""
        try:
            rows = json.loads(value or "[]")
        except ValueError:
            return None
        return rows if isinstance(rows, list) and all(isinstance(r, dict) for r in rows) else None

    async def assets_status_get(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse(envelope({"has_embeddings": assets.count > 0, "stored_asset_count": assets.count}))

    async def assets_status_post(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        rows = _metadata((await request.form()).get("metadata"))
        if rows is None:
            return JSONResponse({"detail": "metadata must be a JSON list of objects"}, status_code=422)
        return JSONResponse(envelope(assets.status(rows)))

    async def assets_prepare(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        rows = _metadata((await request.form()).get("metadata"))
        if rows is None:
            return JSONResponse({"detail": "metadata must be a JSON list of objects"}, status_code=422)
        return JSONResponse(envelope(assets.prepare(rows)))

    async def assets_train(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        form = await request.form()
        mode, rows = form.get("mode"), _metadata(form.get("metadata"))
        if mode not in ("full", "incremental") or rows is None:
            return JSONResponse({"detail": "mode must be full or incremental and metadata a JSON list of objects"}, status_code=422)
        try:
            removed = [str(x) for x in json.loads(form.get("removed_assets") or "[]")]
        except ValueError:
            return JSONResponse({"detail": "removed_assets must be a JSON list"}, status_code=422)
        images = {}
        for upload in form.getlist("images"):
            if hasattr(upload, "read"):
                images[Path(upload.filename or "").stem] = await upload.read()
        return JSONResponse(envelope(assets.train(mode, rows, removed, images, str(form.get("metadata_checksum") or ""))))

    async def assets_search(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        form = await request.form()
        image = form.get("image")
        data = await image.read() if image is not None and hasattr(image, "read") else None
        try:
            top_k = int(form.get("top_k") or 10)
        except ValueError:
            top_k = 10
        try:
            return JSONResponse(envelope({"results": assets.search(str(form.get("prompt") or ""), data, top_k)}))
        except LookupError:
            return JSONResponse({"detail": "no trained model: train the asset library first"}, status_code=404)

    async def assets_search_batch(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        try:
            prompts = json.loads((await request.form()).get("prompts") or "[]")
        except ValueError:
            prompts = None
        if not isinstance(prompts, list) or not all(isinstance(p, str) for p in prompts):
            return JSONResponse({"detail": "prompts must be a JSON list of strings"}, status_code=422)
        try:
            return JSONResponse(envelope({"results": {p: assets.search(p, None, 5) for p in prompts}}))
        except LookupError:
            return JSONResponse({"detail": "no trained model: train the asset library first"}, status_code=404)

    async def assets_delete(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse(envelope({"deleted": assets.clear()}))

    async def mcp_route(request: Request):
        """One MCP JSON-RPC message from an external AI app (mcp.py)."""
        if not _bearer_ok(request):
            return unauthorized()
        message, failure = mcp_parse(await request.body())
        if failure is not None:
            return JSONResponse(failure)
        reply = await mcp.handle(message, request.headers.get("x-mixar-instance-id", ""), request.headers.get("x-mixar-session-id", ""))
        return Response(status_code=202) if reply is None else JSONResponse(reply)

    async def mcp_eligibility(request: Request):
        """200 only when this desktop instance has a live agent socket; a 404 with another detail than "Not Found" is what the
        client maps to "desktop not connected"."""
        if not _bearer_ok(request):
            return unauthorized()
        instance = request.headers.get("x-mixar-instance-id", "")
        if not instance:
            return JSONResponse({"detail": "X-Mixar-Instance-Id is required"}, status_code=422)
        if instance not in hub.sockets:
            return JSONResponse({"detail": "desktop not connected"}, status_code=404)
        return JSONResponse({"eligible": True, "instance_id": instance, "contract": "mixar_ui_v1", "valid_for_seconds": 30})

    routes += [
        Route("/api/v1/asset-search/status", assets_status_get, methods=["GET"]),
        Route("/api/v1/asset-search/status", assets_status_post, methods=["POST"]),
        Route("/api/v1/asset-search/train/prepare", assets_prepare, methods=["POST"]),
        Route("/api/v1/asset-search/train", assets_train, methods=["POST"]),
        Route("/api/v1/asset-search/search", assets_search, methods=["POST"]),
        Route("/api/v1/asset-search/search-batch", assets_search_batch, methods=["POST"]),
        Route("/api/v1/asset-search/embeddings", assets_delete, methods=["DELETE"]),
        Route("/api/v1/mcp", mcp_route, methods=["POST"]),
        Route("/api/v1/mcp-desktop/eligibility", mcp_eligibility, methods=["GET"]),
        Route("/api/v1/matgen", matgen_route, methods=["POST"]),
        Route("/api/v1/job-queue/jobs", job_submit, methods=["POST"]),
        Route("/api/v1/job-queue/jobs/{job_id}", job_get, methods=["GET"]),
        Route("/api/v1/job-queue/jobs/{job_id}", job_cancel, methods=["DELETE"]),
        Route("/api/v1/job-queue/info/{job_type}", job_info, methods=["GET"]),
        Route("/api/v1/jobs/files/{token}/{name}", job_file, methods=["GET"]),
    ]

    routes.append(WebSocketRoute("/api/agent/ws/{instance_id}", agent_ws))

    stt = None if transcriber is False else (transcriber if transcriber is not None else dictation.default_transcriber(settings))

    async def dictation_ws(websocket):
        await dictation.run(websocket, auth, stt, bearer_from)
    routes.append(WebSocketRoute("/api/v1/dictation/ws", dictation_ws))

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

    # ---- the online Studios: the Client plans, the CAPTAIN confirms (these routes are the only confirm there is)
    def _studio_guard(request: Request):
        return None if _bearer_ok(request) else unauthorized()

    async def studio_home(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        from .studios.actions import ACTIONS
        return JSONResponse({"actions": [{"id": a.id, "studio": a.studio, "label": a.label, "needs_approval": a.needs_approval,
                                          "expected_price": a.expected_price} for a in ACTIONS.values()],
                             "approvals": studio.approvals(), "jobs": studio.jobs(),
                             "engine": {"shelf": studio.engine.shelf is not None}})

    async def studio_plan(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        from .studios.actions import ActionError
        body = await _json_body(request)
        try:
            return JSONResponse(await studio.plan(str(body.get("action") or ""), body.get("args") or {}, by="captain"))
        except ActionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)

    async def studio_confirm(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        from .studios.approvals import ApprovalError
        body = await _json_body(request)
        try:
            return JSONResponse(await studio.confirm(request.path_params["approval_id"], body.get("price"), by="captain", answer=body.get("answer")))
        except ApprovalError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404 if "no approval" in str(exc) else 409)

    async def studio_reject(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        from .studios.approvals import ApprovalError
        try:
            return JSONResponse(studio.reject(request.path_params["approval_id"], by="captain"))
        except ApprovalError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

    async def studio_job(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        job = studio.job(request.path_params["job_id"])
        return JSONResponse(job) if job else JSONResponse({"detail": "no such job"}, status_code=404)

    async def studio_job_file(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        path = studio.job_file(request.path_params["job_id"], request.path_params["name"])
        return FileResponse(path) if path else JSONResponse({"detail": "no such file"}, status_code=404)

    async def studio_ack_hung(request: Request):
        if (r := _studio_guard(request)) is not None:
            return r
        studio.acknowledge_hung(request.path_params["job_id"], by="captain")
        return JSONResponse({"ok": True})

    routes += [Route("/app/studio", studio_home, methods=["GET"]), Route("/app/studio/plan", studio_plan, methods=["POST"]),
               Route("/app/studio/approvals/{approval_id}/confirm", studio_confirm, methods=["POST"]),
               Route("/app/studio/approvals/{approval_id}/reject", studio_reject, methods=["POST"]),
               Route("/app/studio/jobs/{job_id}", studio_job, methods=["GET"]),
               Route("/app/studio/jobs/{job_id}/files/{name}", studio_job_file, methods=["GET"]),
               Route("/app/studio/jobs/{job_id}/acknowledge-hung", studio_ack_hung, methods=["POST"])]
    # ---- staged media for video jobs: POST /api/v1/uploads/<image|video> -> data{s3_key, duration_seconds}
    async def upload_media(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        kind = request.path_params["kind"]
        try:
            data = await asyncio.to_thread(video_system.uploads.put, kind, await request.body(), request.headers.get("x-file-name", ""))
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse(envelope(data))
    routes.append(Route("/api/v1/uploads/{kind}", upload_media, methods=["POST"]))

    # ---- sign in to Higgsfield (its MCP): the local pages, loopback only, the same shape as /app/chatgpt
    def _hf_page(body: str, status_code: int = 200) -> HTMLResponse:
        st = hf_auth.status()
        head = ('<p><b>Signed in to Higgsfield.</b> <form method="post" action="/app/higgsfield/signout"><button>Sign out</button></form>'
                if st["signed_in"] else '<form method="post" action="/app/higgsfield/start"><button>Continue with Higgsfield</button></form>')
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>Lampway - Higgsfield</title>
<style>body{{font:16px system-ui;max-width:40em;margin:3em auto;padding:0 1em}} .error{{color:#a00}}</style></head><body>
<h2>Higgsfield</h2>{body}{head}
<p style="color:#555">Your Higgsfield subscription pays for generations started from Lampway. Every credit spend waits for your confirmation
in the Client. Tokens stay in this machine's state directory.</p></body></html>""", status_code=status_code)

    async def hf_home(request: Request):
        return _hf_page("")

    async def hf_start(request: Request):
        if not loopback_origin(request):
            return JSONResponse({"detail": "cross-origin sign-in refused"}, status_code=403)
        try:
            attempt = await asyncio.to_thread(hf_auth.start_login)
        except (HFA.LoginError, HFA.TemporaryAuthError) as exc:
            return _hf_page(f"<p class='error'>Could not start the sign-in: {escape(str(exc))}</p>", status_code=502)
        return RedirectResponse(attempt.url, status_code=302)

    async def hf_callback(request: Request):
        query = {k: v for k, v in request.query_params.items()}
        try:
            await asyncio.to_thread(hf_auth.complete_login, query)
        except HFA.LoginDeclined as exc:
            return _hf_page(f"<p>Higgsfield access was not authorized ({escape(str(exc))}). You can try again.</p>")
        except HFA.LoginError as exc:
            return _hf_page(f"<p class='error'>Sign-in failed: {escape(str(exc))}</p>", status_code=400)
        except Exception as exc:  # noqa: BLE001 - shown to the person at the keyboard, never with a token
            return _hf_page(f"<p class='error'>Sign-in could not finish: {escape(type(exc).__name__)}</p>", status_code=502)
        return _hf_page("<p>Signed in.</p>")

    async def hf_status(request: Request):
        return JSONResponse(hf_auth.status())

    async def hf_signout(request: Request):
        if not loopback_origin(request):
            return JSONResponse({"detail": "cross-origin sign-out refused"}, status_code=403)
        await asyncio.to_thread(hf_auth.sign_out)
        return RedirectResponse("/app/higgsfield", status_code=303)

    routes += [Route("/app/higgsfield", hf_home, methods=["GET"]), Route("/app/higgsfield/start", hf_start, methods=["POST"]),
               Route(HFA.CALLBACK_PATH, hf_callback, methods=["GET"]), Route("/app/higgsfield/status", hf_status, methods=["GET"]),
               Route("/app/higgsfield/signout", hf_signout, methods=["POST"])]

    # ---- the prompt library: list / get / render / save (user scope) / rate / gates / stats
    def _tpl(t: dict, full: bool = False) -> dict:
        summary = {k: t[k] for k in ("id", "version", "title", "description", "purpose", "media", "scope")}
        if not full:
            return summary
        out = {k: v for k, v in t.items() if k != "file"}
        out["versions"] = [v["version"] for v in prompt_service.library.versions(t["id"])]
        return out

    async def prompts_list(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        media = request.query_params.get("media")
        return JSONResponse({"templates": [_tpl(t) for t in prompt_service.library.list(media)], "errors": prompt_service.library.errors})

    async def prompts_get(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        try:
            t = prompt_service.library.get(request.path_params["template_id"], request.query_params.get("version"))
        except LibraryError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return JSONResponse(_tpl(t, True))

    async def prompts_render(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        try:
            return JSONResponse(prompt_service.render(str(body.get("id") or ""), body.get("variables"), body.get("model"), body.get("version")))
        except LibraryError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        except RenderError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)

    async def prompts_save(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        try:
            path = await asyncio.to_thread(prompt_service.library.save, body.get("template"))
        except LibraryError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse({"saved": path, "scope": "user"})

    async def prompts_rate(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        try:
            prompt_service.runlog.rate(str(body.get("job_id") or ""), body.get("rating"), body.get("note") or "")
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        return JSONResponse({"ok": True})

    async def prompts_gates(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        if not isinstance(body.get("gates"), dict) or not body["gates"]:
            return JSONResponse({"detail": "gates must be an object of measurements"}, status_code=400)
        try:
            prompt_service.runlog.gates(request.path_params["job_id"], body["gates"])
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        return JSONResponse({"ok": True})

    async def prompts_runs(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse({"runs": prompt_service.runlog.runs(request.query_params.get("template"))})

    # ---- the experiment ledger (ledger.py): one record of every run, the prompt run log lives in the same file
    ledger = Ledger(prompt_service.runlog.path)

    async def ledger_list(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        q = request.query_params
        return JSONResponse({"rows": ledger.list(q.get("piece"), q.get("stage"), q.get("include_superseded") == "1")})

    async def ledger_record(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        try:
            body = await request.json()
            return JSONResponse(await asyncio.to_thread(ledger.record, body))
        except LedgerError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        except ValueError:
            return JSONResponse({"detail": "a JSON object is required"}, status_code=400)

    async def ledger_compare(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        try:
            return JSONResponse(ledger.compare([i for i in (request.query_params.get("ids") or "").split(",") if i]))
        except LedgerError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)

    async def ledger_receipt(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse(ledger.receipt(request.query_params.get("piece") or ""))

    async def prompts_stats(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse({"stats": prompt_service.runlog.stats(request.query_params.get("template"))})

    routes += [Route("/app/ledger", ledger_list, methods=["GET"]), Route("/app/ledger", ledger_record, methods=["POST"]),
               Route("/app/ledger/compare", ledger_compare, methods=["GET"]), Route("/app/ledger/receipt", ledger_receipt, methods=["GET"]),
               Route("/app/prompts", prompts_list, methods=["GET"]), Route("/app/prompts", prompts_save, methods=["PUT"]),
               Route("/app/prompts/render", prompts_render, methods=["POST"]), Route("/app/prompts/rate", prompts_rate, methods=["POST"]),
               Route("/app/prompts/stats", prompts_stats, methods=["GET"]), Route("/app/prompts/runs", prompts_runs, methods=["GET"]),
               Route("/app/prompts/runs/{job_id}/gates", prompts_gates, methods=["POST"]),
               Route("/app/prompts/{template_id}", prompts_get, methods=["GET"])]

    # ---- provider setup from the Client (main / swarm / image), saved in the state dir
    async def provider_get(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        return JSONResponse(provider_prefs.view(settings))

    async def provider_put(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        try:
            values = provider_prefs.validate(body.get("values"))
            trial = provider_prefs.trial(settings, values)
            new_main = None
            if provider_prefs.MAIN_FIELDS & set(values):
                new_main = make_provider(trial, chatgpt_auth=chatgpt)              # built BEFORE anything changes: a refusal leaves it all as it was
            if {"swarm_provider", "provider", "claude_swarm_model", "openrouter_swarm_model", "chatgpt_swarm_model",
                    "chatgpt_swarm_effort"} & set(values):
                make_swarm_provider(trial, "worker-1", chatgpt_auth=chatgpt)
        except (provider_prefs.PrefsError, ValueError, RuntimeError, OSError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        provider_prefs.save(settings.state_dir, provider_prefs.merge_values(provider_prefs.load(settings.state_dir), values))
        provider_prefs.apply(settings, values)
        if new_main is not None:
            agent.provider = new_main
        return JSONResponse(provider_prefs.view(settings))

    routes += [Route("/app/provider-settings", provider_get, methods=["GET"]), Route("/app/provider-settings", provider_put, methods=["PUT"])]
    routes.append(Route("/app/swarm", swarm_status, methods=["GET"]))
    routes.append(Route("/app/swarm/{swarm_id}/cancel/{worker}", swarm_cancel, methods=["POST"]))
    app = Starlette(routes=routes)
    app.add_middleware(HostGuard, bind_host=settings.host)
    app.state.hub = hub
    app.state.agent = agent
    app.state.settings = settings
    app.state.auth = auth
    app.state.store = store
    app.state.provider = provider
    app.state.chatgpt = chatgpt
    app.state.video = video_system
    app.state.jobs = jobs
    app.state.prompts = prompt_service
    app.state.higgsfield_auth = hf_auth
    app.state.jobs = jobs
    return app
