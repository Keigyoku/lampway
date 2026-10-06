"""The ASGI application: REST routes the client calls plus the agent WebSocket."""

import asyncio
import contextlib
import json
import logging
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
from .ledger import default_path as Ledger_default_path
from .spendpolicy import SpendPolicy
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


def default_studio_service(receipts=None):
    """The Studio service over the project root and, when ``LAMPWAY_STUDIO_SHELF`` names it, the owner's shelf of AXI drivers."""
    from .agent.server_tools import project_root
    from .studios.service import StudioService
    return StudioService(project_root(), shelf=os.environ.get("LAMPWAY_STUDIO_SHELF") or None, receipts=receipts)


def _open_library(state_dir):
    """The Vault (library/store.py) under ``<state>/library``, or None when another process holds its one writer lock: the job hook then spools what it would
    have recorded (``<state>/library-spool.jsonl``) and ``provenance.replay_spool`` lands it once a library opens."""
    from .library import provenance as _prov
    from .library.store import AssetLibrary, LibraryError as VaultError
    try:
        lib = AssetLibrary(Path(state_dir) / "library")
    except VaultError:
        return None
    spool = Path(state_dir) / "library-spool.jsonl"
    if spool.is_file():
        _prov.replay_spool(lib, spool)                             # what a locked period spooled lands now
    return lib


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


def create_app(settings: Settings, provider=None, chatgpt_auth=None, swarm_provider_factory=None, job_backends=None, transcriber=None, studio_service=None, video=None, higgsfield_auth=None, prompts=None, job_services=None, job_receipts=None, cockpit=None, egress=None) -> Starlette:
    from . import egress as _EG
    if egress is not None:
        _EG.set_active(egress)                                                      # an explicit manager (tests, embedding) wins
    elif _EG.ACTIVE is None:
        _EG.set_active(_EG.Egress(settings.state_dir))                              # production: strict, every route off until the user opts in
    _EG.install()
    if not str(settings.openai_base_url).startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        from urllib.parse import urlsplit
        _EG.ACTIVE.register_host("custom_llm", urlsplit(settings.openai_base_url).hostname or "")
    logredact.install()          # no OAuth code/state/token in any log line, uvicorn's access log included
    provider_prefs.apply_saved(settings, provider_prefs.load(settings.state_dir))   # the saved provider choices apply where the environment is silent (an env var is the session's override)
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
    from . import jobreceipts as JR
    from .agent.server_tools import project_root as _project_root
    hf_auth = higgsfield_auth or HiggsfieldAuth(settings.state_dir, redirect_port=settings.port)      # ONE per server: refresh tokens rotate
    video_system = video if video is not None else videojobs.build_default(settings, hf_auth, Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects"))
    receipts = job_receipts if job_receipts is not None else JR.JobReceipts(_project_root(), ledger=Ledger(Ledger_default_path()), fetchers=video_system.receipt_fetchers())
    studio = studio_service if studio_service is not None else default_studio_service(receipts)
    prompt_service = prompts if prompts is not None else PromptService.from_env(settings.state_dir)
    library = _open_library(settings.state_dir)
    from .library import hooks as _vault_hooks
    jobs = JobQueue(default_job_backends(settings) if job_backends is None else job_backends, hub,
                    f"http://{settings.host}:{settings.port}", model_labels={"image_gen": settings.openrouter_image_model},
                    video=video_system, approvals=studio.approvals_store, prompts=prompt_service, registry=job_services, policy=SpendPolicy(lambda: settings.spend_policy), receipts=receipts,
                    provenance=_vault_hooks.job_hook(library, settings.state_dir / "library-spool.jsonl"))
    video_system.jobs = jobs
    for gate_action in ("higgsfield.job", "higgsfield.question", "service.job", "openrouter.job"):          # the user's click reaches the waiting job through the Studios' confirm
        studio.register_gate(gate_action, lambda a, answer: jobs.resolve_approval(a.id, True, answer), lambda a: jobs.resolve_approval(a.id, False))
    routes += stub_routes(auth, store, settings, jobs)
    if swarm_provider_factory is None and provider is None:        # the configured provider's cheap swarm model
        swarm_provider_factory = lambda label: make_swarm_provider(settings, label, chatgpt_auth=chatgpt)  # noqa: E731  (one sign-in)
    from .herdr.host import Cockpit
    cockpit = cockpit if cockpit is not None else Cockpit(Path(os.environ.get("LAMPWAY_HERDR_ROOT") or (Path(os.environ.get("LAMPWAY_HOME") or settings.state_dir) / "herdr")), project_root=str(_project_root()))
    assets = AssetIndex(settings.state_dir)
    agent = AgentHub(provider if provider is not None else make_provider(settings, chatgpt_auth=chatgpt),
                     swarm_provider_factory=swarm_provider_factory, studio=studio, video=video_system, prompts=prompt_service, jobs=jobs, cockpit=cockpit, assets=assets)

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

    mcp = McpServer(hub, agent, ledger=Ledger(Ledger_default_path()), caps=lambda: {"video_max_job_usd": settings.video_max_job_usd})

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

    # ---- the online Studios: the Client plans, the USER confirms (these routes are the only confirm there is)
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

    # ---- the cockpit: the user's real agent CLIs as panes of Lampway's OWN herdr server (herdr/): start/stop/close are explicit user actions, reconcile never spawns or kills
    from .herdr.host import CockpitError
    from .herdr import launcher as _HL

    def _wb(request):
        return None if _bearer_ok(request) else unauthorized()

    def _wb_err(exc, code=409):
        return JSONResponse({"detail": str(exc)}, status_code=code)

    async def mcp_inventory_get(request: Request):
        if (r := _wb(request)) is not None:
            return r
        from .mcp_inventory import api as _INV
        from .mcp import offered_tools
        inst = request.headers.get("x-mixar-instance-id", "")
        elig = lambda: (True, "connected") if hub.sockets.get(inst) is not None else (False, "desktop not connected")  # noqa: E731
        try:
            return JSONResponse(await asyncio.to_thread(_INV.inventory, _project_root(), Path.home(), None, request.query_params.get("client") or "all", request.query_params.get("scope") or "all",
                                                        elig, lambda: len(offered_tools())))
        except _INV.InventoryError as exc:
            return _wb_err(exc, 422)

    async def mcp_check_post(request: Request):
        if (r := _wb(request)) is not None:
            return r
        from .mcp_inventory import api as _INV
        body = await _json_body(request)
        try:
            return JSONResponse(await asyncio.to_thread(_INV.check, _project_root(), Path.home(), str(body.get("id") or "")))
        except _INV.InventoryError as exc:
            return _wb_err(exc, 422)
        except PermissionError as exc:                                               # egress consent: the mcp_probe route is off
            return _wb_err(exc, 403)

    async def egress_state(request: Request):
        if (r := _wb(request)) is not None:
            return r
        m = _EG.ACTIVE
        return JSONResponse({"routes": m.routes_view(), "indicator": m.indicator(), "overrides": m._prefs()["overrides"]})

    async def egress_route(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            return JSONResponse(_EG.ACTIVE.set_route(str(body.get("route") or ""), bool(body.get("enabled"))))
        except ValueError as exc:
            return _wb_err(exc, 422)

    async def egress_override(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            if request.method == "DELETE":
                _EG.ACTIVE.clear_override(str(body.get("asset_id") or ""), str(body.get("route") or ""))
                return JSONResponse({"cleared": True})
            return JSONResponse(_EG.ACTIVE.override(str(body.get("asset_id") or ""), str(body.get("route") or "")))
        except ValueError as exc:
            return _wb_err(exc, 422)

    async def egress_log(request: Request):
        if (r := _wb(request)) is not None:
            return r
        return JSONResponse({"rows": _EG.ACTIVE.log(int(request.query_params.get("limit") or 200))})

    async def egress_export(request: Request):
        if (r := _wb(request)) is not None:
            return r
        from starlette.responses import PlainTextResponse
        return PlainTextResponse(_EG.ACTIVE.export_text(), headers={"content-disposition": "attachment; filename=egress-log.jsonl"})

    async def video_ingest(request: Request):
        """The user's confirm of the ingest card (the agent's tool only proposes). One clip, with provenance."""
        if (r := _wb(request)) is not None:
            return r
        from . import videoingest as VIN
        body = await _json_body(request)
        try:
            return JSONResponse(await asyncio.to_thread(VIN.ingest, _project_root(), body.get("url"), "user", bool(body.get("confirmed")), bool(body.get("audio")), int(body.get("max_height") or 720),
                                                        int(body.get("max_seconds") or 600), int(body.get("max_bytes") or VIN.DEFAULT_BYTES), body.get("name"), body.get("range"), None,
                                                        Ledger(Ledger_default_path())))
        except (VIN.IngestError, ValueError) as exc:
            return _wb_err(exc, 422)

    async def wb_home(request: Request):
        if (r := _wb(request)) is not None:
            return r
        status = await asyncio.to_thread(_HL.server_status, cockpit.root)
        return JSONResponse({"server": {"running": bool(status.get("running")), "version": status.get("version"), "method": _HL.server_info(cockpit.root).get("method")},
                             "sessions": cockpit.list_sessions(), "offered": [] if status.get("running") else ["start", "resume"]})

    async def wb_server_start(request: Request):
        if (r := _wb(request)) is not None:
            return r
        try:
            return JSONResponse(await asyncio.to_thread(cockpit.ensure_server))
        except _HL.HerdrError as exc:
            return _wb_err(exc)

    async def wb_server_stop(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            return JSONResponse(await asyncio.to_thread(cockpit.stop_server, bool(body.get("confirm"))))
        except _HL.HerdrError as exc:
            return _wb_err(exc)

    async def wb_reconcile(request: Request):
        if (r := _wb(request)) is not None:
            return r
        return JSONResponse(await asyncio.to_thread(cockpit.reconcile))

    async def wb_create(request: Request):
        if (r := _wb(request)) is not None:
            return r
        from .agent import cli_adapters
        body = await _json_body(request)
        if body.get("bypass") and os.environ.get("LAMPWAY_ALLOW_BYPASS_ROUTE") != "1":
            return _wb_err("bypass can only be raised by the user's own click in the cockpit: a request cannot lift the permission level", 403)
        if body.get("agent") in ("claude", "codex", "opencode"):
            try:
                cli_adapters.require_enabled(settings.state_dir)
            except ValueError as exc:
                return _wb_err(f"the local CLI switch is off: {exc}", 403)
        try:
            rec = await asyncio.to_thread(cockpit.create_session, body.get("agent"), body.get("name"), body.get("cwd") or str(_project_root()), body.get("task") or "", body.get("effort"),
                                          False, body.get("resume_id"), body.get("command"), "user")
            return JSONResponse(rec)
        except (CockpitError, _HL.HerdrError) as exc:
            return _wb_err(exc)

    async def wb_screen(request: Request):
        if (r := _wb(request)) is not None:
            return r
        try:
            return JSONResponse({"screen": await asyncio.to_thread(cockpit.read_screen, request.path_params["sid"], int(request.query_params.get("lines") or 70))})
        except (CockpitError, _HL.HerdrError) as exc:
            return _wb_err(exc)

    async def wb_input(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            await asyncio.to_thread(cockpit.send_input, request.path_params["sid"], str(body.get("text") or ""), bool(body.get("submit", True)), body.get("by") or "agent", body.get("user_typed_at"))
            return JSONResponse({"sent": True})
        except (CockpitError, _HL.HerdrError) as exc:
            return _wb_err(exc)

    async def wb_close(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            return JSONResponse(await asyncio.to_thread(cockpit.close_session, request.path_params["sid"], bool(body.get("confirm"))))
        except (CockpitError, _HL.HerdrError) as exc:
            return _wb_err(exc)

    async def wb_agent_sends(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            cockpit.set_agent_sends(request.path_params["sid"], bool(body.get("on")))
            return JSONResponse({"ok": True})
        except CockpitError as exc:
            return _wb_err(exc)

    routes += [Route("/app/mcp/inventory", mcp_inventory_get, methods=["GET"]), Route("/app/mcp/check", mcp_check_post, methods=["POST"]), Route("/app/egress", egress_state, methods=["GET"]), Route("/app/egress/route", egress_route, methods=["POST"]), Route("/app/egress/override", egress_override, methods=["POST", "DELETE"]),
               Route("/app/egress/log", egress_log, methods=["GET"]), Route("/app/egress/export", egress_export, methods=["GET"]), Route("/app/video/ingest", video_ingest, methods=["POST"]), Route("/app/workbench", wb_home, methods=["GET"]), Route("/app/workbench/server/start", wb_server_start, methods=["POST"]),
               Route("/app/workbench/server/stop", wb_server_stop, methods=["POST"]), Route("/app/workbench/reconcile", wb_reconcile, methods=["POST"]),
               Route("/app/workbench/sessions", wb_create, methods=["POST"]), Route("/app/workbench/sessions/{sid}/screen", wb_screen, methods=["GET"]),
               Route("/app/workbench/sessions/{sid}/input", wb_input, methods=["POST"]), Route("/app/workbench/sessions/{sid}/close", wb_close, methods=["POST"]),
               Route("/app/workbench/sessions/{sid}/agent-sends", wb_agent_sends, methods=["POST"])]
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
            saved_values = provider_prefs.validate(body.get("values"))
            values = {k: v for k, v in saved_values.items() if settings.sources.get(k) != "env"}      # a field the environment sets stays as it has it this session
            trial = provider_prefs.trial(settings, values)
            new_main = None
            if provider_prefs.MAIN_FIELDS & set(values):
                new_main = make_provider(trial, chatgpt_auth=chatgpt)              # built BEFORE anything changes: a refusal leaves it all as it was
            if {"swarm_provider", "provider", "claude_swarm_model", "openrouter_swarm_model", "chatgpt_swarm_model",
                    "chatgpt_swarm_effort"} & set(values):
                make_swarm_provider(trial, "worker-1", chatgpt_auth=chatgpt)
        except (provider_prefs.PrefsError, ValueError, RuntimeError, OSError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        provider_prefs.save(settings.state_dir, provider_prefs.merge_values(provider_prefs.load(settings.state_dir), saved_values))
        provider_prefs.apply(settings, values)
        settings.sources.update({k: "saved" for k in values})
        if new_main is not None:
            agent.provider = new_main
        return JSONResponse(provider_prefs.view(settings))

    routes += [Route("/app/provider-settings", provider_get, methods=["GET"]), Route("/app/provider-settings", provider_put, methods=["PUT"])]
    routes.append(Route("/app/swarm", swarm_status, methods=["GET"]))
    routes.append(Route("/app/swarm/{swarm_id}/cancel/{worker}", swarm_cancel, methods=["POST"]))
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        """Receipts first: a restart finds every in-flight paid job in its receipt, resumes by provider id, and marks what it cannot know as submission_unknown (never resubmitted)."""
        try:
            await asyncio.to_thread(cockpit.reconcile)             # sessions and paid jobs are reconciled in ONE pass at start; the herdr server is never auto-started
        except Exception:  # noqa: BLE001
            logging.getLogger("lampway.jobs").warning("cockpit reconcile failed", exc_info=True)
        try:
            await jobs.recover()
        except Exception:  # noqa: BLE001 - a recovery problem must not stop the server; the receipts stay on disk
            logging.getLogger("lampway.jobs").warning("job recovery failed", exc_info=True)

        async def tick():
            while True:
                await asyncio.sleep(60)
                try:
                    await jobs.recover()
                except Exception:  # noqa: BLE001
                    pass
        task = asyncio.get_running_loop().create_task(tick())
        try:
            yield
        finally:
            task.cancel()

    app = Starlette(routes=routes, lifespan=lifespan)
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
    app.state.library = library
    return app
