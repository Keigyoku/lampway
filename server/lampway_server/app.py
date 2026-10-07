"""The ASGI application: REST routes the client calls plus the agent WebSocket."""

import asyncio
import contextlib
import json
import logging
import os
import threading
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
from .library import rest as library_rest
from .library.vault import Vault
from .cards import routes as cards_routes
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


def _open_library(vault):
    """The shared Vault's library, or None when another process holds its one writer lock: the job hook then spools what it would have recorded
    (``vault.spool``) and ``provenance.replay_spool`` lands it the next time a server opens the library."""
    from .library import provenance as _prov
    from .library.store import LibraryError as VaultError
    try:
        lib = vault.lib
    except VaultError:
        return None
    if vault.spool.is_file():
        _prov.replay_spool(lib, vault.spool)                       # what a locked period spooled lands now
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


def _local_job_services(settings: Settings):
    """The Client's mesh job types backed by Lampway's own tools in a headless Lampway (job_backends.py) when LAMPWAY_BLENDER names the binary; else empty."""
    from . import job_backends as JB
    work = Path(settings.state_dir) / "jobs-local"
    work.mkdir(parents=True, exist_ok=True)
    return JB.default_registry(work=work)


def _register_endpoint_host(base_url: str) -> None:
    """Law 2 for the user's own OpenAI-compatible endpoint: loopback is local; any other host (a LAN box included) belongs to the
    custom_llm route, which is off until the user opts in."""
    from urllib.parse import urlsplit
    from . import egress as _EG
    if not str(base_url).startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")) and _EG.ACTIVE is not None:
        _EG.ACTIVE.register_host("custom_llm", urlsplit(str(base_url)).hostname or "")


def create_app(settings: Settings, provider=None, chatgpt_auth=None, swarm_provider_factory=None, job_backends=None, transcriber=None, studio_service=None, video=None, higgsfield_auth=None, prompts=None, job_services=None, job_receipts=None, cockpit=None, egress=None,
               handwriting_reader=None, connections_transport=None) -> Starlette:
    from . import egress as _EG
    if egress is not None:
        _EG.set_active(egress)                                                      # an explicit manager (tests, embedding) wins
    elif _EG.ACTIVE is None:
        _EG.set_active(_EG.Egress(settings.state_dir))                              # production: strict, every route off until the user opts in
    _EG.install()
    _register_endpoint_host(settings.openai_base_url)
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
        """Finding F8: the bearer, and whether the sign-in works - never the email or the client id (the row in Connections shows those, masked)."""
        token = bearer_token(request)
        if not token or auth.verify_access(token) is None:
            return unauthorized()
        st = chatgpt.status()
        return JSONResponse({"signed_in": bool(st["signed_in"]), "plan_usage_enabled": bool(st["plan_usage_enabled"])})

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
    vault = Vault(settings.state_dir)                         # the Asset Vault: ONE writer per process, shared by its routes, the agent tools, MCP, the job hook and the renderer
    library = _open_library(vault)
    from .library import hooks as _vault_hooks
    from .library.render import Renderer as _VaultRenderer
    renderer = _VaultRenderer(library, blender=os.environ.get("LAMPWAY_BIN") or None) if library is not None else None     # previews: never the live window
    def image_chooser(service, model, payload, origin):
        """The image job's purpose (the Client's ``params.purpose``, else AI Render, which follows Plates), on what its backend runs
        (OpenRouter), the Client's model a job override (HC6, HC10)."""
        from . import choices as CHO
        from .choices import registry as CREG
        purpose = str(((payload or {}).get("params") or {}).get("purpose") or "")
        pid = f"image.{purpose}" if f"image.{purpose}" in CREG.PURPOSES else "image.ai_render"
        override = None if model in ("", "default", None) else (model if ":" in model else f"openrouter:{model}")
        return CHO.resolve(pid, CHO.Job(needs={"runs_on": ["openrouter"]}, override=override, origin="user" if origin == "user" else "agent"))
    jobs = JobQueue(default_job_backends(settings) if job_backends is None else job_backends, hub,
                    f"http://{settings.host}:{settings.port}", model_labels={"image_gen": settings.openrouter_image_model},
                    video=video_system, approvals=studio.approvals_store, prompts=prompt_service, registry=job_services if job_services is not None else _local_job_services(settings),
                    policy=SpendPolicy(lambda: settings.spend_policy), receipts=receipts, provenance=_vault_hooks.job_hook(library, vault.spool),
                    chooser=image_chooser if job_backends is None and "image_gen" in default_job_backends(settings) else None)
    video_system.jobs = jobs
    for gate_action in ("higgsfield.job", "higgsfield.question", "service.job", "openrouter.job"):          # the user's click reaches the waiting job through the Studios' confirm
        studio.register_gate(gate_action, lambda a, answer: jobs.resolve_approval(a.id, True, answer), lambda a: jobs.resolve_approval(a.id, False))
    choice_hook = []                                          # filled below, once the agent exists: a saved choice rebuilds what it decides
    routes += stub_routes(auth, store, settings, jobs, on_choice=lambda pid: [f(pid) for f in choice_hook])
    if swarm_provider_factory is None and provider is None:        # the configured provider's cheap swarm model
        swarm_provider_factory = lambda label: make_swarm_provider(settings, label, chatgpt_auth=chatgpt)  # noqa: E731  (one sign-in)
    from .herdr.host import Cockpit
    cockpit = cockpit if cockpit is not None else Cockpit(Path(os.environ.get("LAMPWAY_HERDR_ROOT") or (Path(os.environ.get("LAMPWAY_HOME") or settings.state_dir) / "herdr")), project_root=str(_project_root()))
    assets = AssetIndex(settings.state_dir)                  # the legacy /asset-search endpoints the Client's Train/Search UI calls
    def _main_provider():
        """5.6: built from agent.main's resolution (the user's fallback runs when the preferred option cannot); with nothing that can
        serve, from the settings as before, so the provider's own refusal names the fix at the first call."""
        from . import choices as CHO
        try:
            return make_provider(settings, chatgpt_auth=chatgpt, resolution=CHO.resolve("agent.main", CHO.Job()))
        except CHO.NoChoice:
            return make_provider(settings, chatgpt_auth=chatgpt)
        except (ValueError, RuntimeError):
            return make_provider(settings, chatgpt_auth=chatgpt)
    agent = AgentHub(provider if provider is not None else _main_provider(),
                     swarm_provider_factory=swarm_provider_factory, studio=studio, video=video_system, prompts=prompt_service, jobs=jobs, cockpit=cockpit, assets=vault,
                     switch_dir=settings.state_dir)

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

    def _material_provider():
        """HC3: agent.material_script's choice; ``follow:agent.main`` (the shipped default) is the running agent's own provider."""
        from . import choices as CHO
        from .choices.bridge import settings_for_option
        try:
            r = CHO.resolve("agent.material_script", CHO.Job(content_class="public"))
        except CHO.NoChoice:
            return agent.provider
        if r.followed == "agent.main" or r.option.startswith("follow:"):
            return agent.provider
        return make_provider(settings_for_option(settings, r.option, r.params), chatgpt_auth=chatgpt)

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
            material = await matgen.generate(_material_provider(), prompt, str(body.get("pipeline") or "fast"))
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
        *library_rest.routes(vault, _bearer_ok),
        *cards_routes.routes(_bearer_ok, api_port=settings.port),
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

    # ---- handwriting into composer text (handwriting.py): blank ink never reaches a model
    from . import handwriting as HW
    hw_reader = None if handwriting_reader is False else (handwriting_reader if handwriting_reader is not None else HW.default_reader(settings))

    async def handwriting_recognize(request: Request):
        if not _bearer_ok(request):
            return unauthorized()
        form = await request.form()
        up = form.get("image")
        if up is None or not hasattr(up, "read"):
            return JSONResponse({"detail": "send the ink as a multipart 'image' field"}, status_code=422)
        data = await up.read()
        if len(data) > HW.MAX_BYTES:
            return JSONResponse({"detail": "image too large: rasterise at <= 2048 px"}, status_code=413)
        try:
            has, _crop = HW.ink(data)
        except HW.NotAnImage as exc:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        if has and hw_reader is None:
            return JSONResponse({"detail": "no vision model configured: set one in Providers (OpenRouter key, LAMPWAY_HANDWRITING_MODEL)"}, status_code=503)
        out = await HW.recognize(data, str(form.get("hint") or ""), hw_reader)
        return JSONResponse(envelope(out))
    routes.append(Route("/api/v1/handwriting/recognize", handwriting_recognize, methods=["POST"]))

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

    wb_last_reconcile: dict = {}

    async def wb_reconcile(request: Request):
        if (r := _wb(request)) is not None:
            return r
        out = await asyncio.to_thread(cockpit.reconcile)
        wb_last_reconcile.clear()
        wb_last_reconcile.update(out)
        return JSONResponse(out)

    # ---- the Lampway terminal (facelift contract 16): an optional WezTerm add-on; every write is the user's, never an agent's
    def _term_home():
        return Path(os.environ.get("LAMPWAY_HOME") or settings.state_dir)

    def _term_guard(request, write=False):
        if (r := _wb(request)) is not None:
            return r
        if write and request.headers.get("x-lampway-origin", "").lower() == "agent":
            return JSONResponse({"detail": "only your click installs, opens or removes the Lampway terminal"}, status_code=403)
        return None

    async def terminal_status(request: Request):
        if (r := _term_guard(request)) is not None:
            return r
        from .addons import wezterm as _WZ
        home = _term_home()
        exe = _WZ.binary(home)
        try:
            pin = _WZ.pin_for(_WZ.platform_key())
        except _WZ.TerminalRefused as exc:
            pin = {"refused": str(exc)}
        state = await asyncio.to_thread(_WZ.reconcile, home, str(exe)) if exe else {"window": "gone", "panes": [], "foreign_panes": []}
        return JSONResponse({"installed": bool(exe), "binary": str(exe) if exe else None, "pin": {k: pin.get(k) for k in ("version", "bytes", "refused")},
                             **state})

    async def terminal_get(request: Request):
        if (r := _term_guard(request, True)) is not None:
            return r
        from .addons import wezterm as _WZ
        try:
            return JSONResponse(await asyncio.to_thread(_WZ.get, _term_home(), _WZ.pin_for(_WZ.platform_key())))
        except (_WZ.TerminalRefused, _EG.EgressRefused) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)

    async def terminal_open(request: Request):
        if (r := _term_guard(request, True)) is not None:
            return r
        from .addons import wezterm as _WZ
        home = _term_home()
        exe = _WZ.binary(home)
        if not exe:
            return JSONResponse({"detail": "the Lampway terminal is not installed: Get it first (about 49 MB from github.com)"}, status_code=409)
        body = await _json_body(request)
        try:
            boot = [_HL.bin_path(), "session", "attach", "lampway"]
        except _HL.HerdrError:
            boot = None
        try:
            return JSONResponse(await asyncio.to_thread(_WZ.launch, home, str(exe), cockpit.root, body.get("position"), True, boot))
        except _WZ.TerminalRefused as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)

    async def terminal_remove(request: Request):
        if (r := _term_guard(request, True)) is not None:
            return r
        from .addons import wezterm as _WZ
        return JSONResponse(await asyncio.to_thread(_WZ.remove, _term_home()))

    routes += [Route("/app/terminal", terminal_status, methods=["GET"]), Route("/app/terminal/get", terminal_get, methods=["POST"]),
               Route("/app/terminal/open", terminal_open, methods=["POST"]), Route("/app/terminal/remove", terminal_remove, methods=["POST"])]

    # ---- the cockpit window (facelift contract 10): a static page from this origin only; its data behind the bearer
    _WB_PAGE = Path(__file__).resolve().parent / "web" / "workbench"
    _WB_STATIC = {"cockpit.js": "text/javascript", "cockpit.css": "text/css", "tokens.css": "text/css"}
    _WB_CSP = ("default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
               "frame-src http://127.0.0.1:* http://localhost:*; base-uri 'none'; form-action 'none'")

    async def wb_page(request: Request):
        return HTMLResponse((_WB_PAGE / "index.html").read_text(encoding="utf-8"), headers={"Content-Security-Policy": _WB_CSP, "Cache-Control": "no-store"})

    async def wb_static(request: Request):
        name = request.path_params["name"]
        if name not in _WB_STATIC:
            return JSONResponse({"detail": "not found"}, status_code=404)
        return Response((_WB_PAGE / name).read_bytes(), media_type=_WB_STATIC[name], headers={"Cache-Control": "no-store"})

    async def wb_view(request: Request):
        if (r := _wb(request)) is not None:
            return r
        from . import workbench_view as _WV
        status = await asyncio.to_thread(_HL.server_status, cockpit.root)
        home = {"server": {"running": bool(status.get("running"))}, "sessions": cockpit.list_sessions()}
        return JSONResponse(_WV.view(home, dict(wb_last_reconcile) or None))

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

    def _wb_origin(request: Request) -> str:
        """Who is typing, decided from the caller and never from ``body.by`` (agent-modes spec B6): a request that declares an agent
        origin, a cross-origin request, or a token minted for an agent or an MCP client is an agent send; the user's own Client (the
        cockpit page, the Blender panel) is the user."""
        from .connections.routes import _cross_origin
        if any((request.headers.get(h) or "").strip().lower() in ("agent", "mcp") for h in ("x-lampway-origin", "x-mixar-job-origin")):
            return "agent"
        if _cross_origin(request):
            return "agent"
        claims = auth.verify_access(bearer_token(request) or "") or {}
        if str(claims.get("origin") or "").lower() in ("agent", "mcp") or str(claims.get("aud") or "").lower() == "mcp":
            return "agent"
        return "user"

    async def wb_input(request: Request):
        if (r := _wb(request)) is not None:
            return r
        body = await _json_body(request)
        try:
            await asyncio.to_thread(cockpit.send_input, request.path_params["sid"], str(body.get("text") or ""), bool(body.get("submit", True)), _wb_origin(request), body.get("user_typed_at"))
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
               Route("/app/egress/log", egress_log, methods=["GET"]), Route("/app/egress/export", egress_export, methods=["GET"]), Route("/app/video/ingest", video_ingest, methods=["POST"]), Route("/app/workbench", wb_home, methods=["GET"]), Route("/app/workbench/page", wb_page, methods=["GET"]),
               Route("/app/workbench/static/{name}", wb_static, methods=["GET"]), Route("/app/workbench/view", wb_view, methods=["GET"]), Route("/app/workbench/server/start", wb_server_start, methods=["POST"]),
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
        if not _bearer_ok(request):                                                      # finding F8
            return unauthorized()
        return JSONResponse({"signed_in": bool(hf_auth.status()["signed_in"])})

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
        from .choices.bridge import save_dialog_choices
        rest = save_dialog_choices(settings, saved_values)          # step 9: what Choices models is the user's choice now; the rest stays here
        if rest:
            provider_prefs.save(settings.state_dir, provider_prefs.merge_values(provider_prefs.load(settings.state_dir), rest))
        provider_prefs.apply(settings, values)
        settings.sources.update({k: "saved" for k in values})
        if new_main is not None:
            agent.provider = new_main
        return JSONResponse(provider_prefs.view(settings))

    # ---- the way out of submission_unknown (jobreceipts): the USER acknowledges (it did not run) or links (here is the provider's job id); never an agent
    def _receipt_user(request: Request, body: dict):
        if (r := _wb(request)) is not None:
            return r
        if str(body.get("by") or "user") != "user" or request.headers.get("X-Lampway-Origin", "").lower() == "agent":
            return JSONResponse({"detail": "only the user resolves a submission_unknown job, in the Client: an agent may not"}, status_code=403)
        return None

    def _receipt_view(r: dict) -> dict:
        v = JR.export_safe(r)
        if r["state"] == "submission_unknown":
            v["actions"] = ["acknowledge", "link"]
        return v

    async def receipts_list(request: Request):
        if (r := _wb(request)) is not None:
            return r
        state = request.query_params.get("state") or None
        return JSONResponse({"receipts": [_receipt_view(x) for x in receipts.list(state)]})

    async def _receipt_resolve(request: Request, action: str):
        body = await _json_body(request)
        if (r := _receipt_user(request, body)) is not None:
            return r
        rec = receipts.get(request.path_params["key"])
        if rec is None:
            return JSONResponse({"detail": f"no receipt {request.path_params['key']}"}, status_code=404)
        if rec["state"] != "submission_unknown":
            return JSONResponse({"detail": f"only a submission_unknown job is resolved here; this one is {rec['state']}"}, status_code=409)
        try:
            if action == "acknowledge":
                rec = receipts.acknowledge(rec, "user")
            else:
                if not str(body.get("provider_job_id") or "").strip():
                    return JSONResponse({"detail": "link needs provider_job_id: the job id from the provider's own history"}, status_code=422)
                rec = receipts.link(rec, str(body["provider_job_id"]).strip(), "user")
        except JR.ReceiptError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        try:
            await jobs.recover()                                                   # the queue shows the new state now; a linked job resumes by its provider id
        except Exception:  # noqa: BLE001 - the receipt is already moved on disk; recovery runs again at the next start
            logging.getLogger("lampway.jobs").warning("recovery after a receipt resolution failed", exc_info=True)
        return JSONResponse({"receipt": _receipt_view(rec)})

    async def receipt_acknowledge(request: Request):
        return await _receipt_resolve(request, "acknowledge")

    async def receipt_link(request: Request):
        return await _receipt_resolve(request, "link")

    routes += [Route("/app/receipts", receipts_list, methods=["GET"]), Route("/app/receipts/{key}/acknowledge", receipt_acknowledge, methods=["POST"]),
               Route("/app/receipts/{key}/link", receipt_link, methods=["POST"])]
    async def generate_estimate(request: Request):
        """The island's Image / Video tab before Generate (facelift contract 08): the estimate, the policy and the caps. Sends nothing."""
        if not _bearer_ok(request):
            return unauthorized()
        body = await _json_body(request)
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        try:
            refs = max(0, int(body.get("references") or 0))
        except (TypeError, ValueError):
            return JSONResponse({"detail": "references is a count"}, status_code=422)
        return JSONResponse(await asyncio.to_thread(jobs.estimate, str(body.get("service") or ""), str(body.get("model") or ""), params, refs))

    async def spend_view(request: Request):
        """What the status bar's spend gauge reads (facelift contract 03): each provider in its own unit, what this server session spent, and the
        caps and click rule the Providers dialog set. Read-only. There is no day ledger, so the scope says session."""
        if not _bearer_ok(request):
            return unauthorized()
        from .spendpolicy import PROVIDERS
        policy = jobs.policy
        rows = []
        for p in PROVIDERS:
            cfg = policy._cfg(p)
            rows.append({"provider": p, "unit": "USD" if p == "openrouter" else "credits", "spent": round(float(policy.spent.get(p, 0.0)), 6),
                         "session_cap": cfg.get("session_cap"), "job_cap": cfg.get("job_cap"), "click": cfg.get("click", "always"), "above": cfg.get("above")})
        return JSONResponse({"scope": "session", "providers": rows})

    routes += [Route("/app/provider-settings", provider_get, methods=["GET"]), Route("/app/provider-settings", provider_put, methods=["PUT"]),
               Route("/app/spend", spend_view, methods=["GET"]), Route("/app/generate/estimate", generate_estimate, methods=["POST"])]
    # ---- Connections (connections/): every credential, its source and its status; the user's writes; the read-only view the agent gets
    from . import connections as CONN
    from .higgsfield_mcp import HiggsfieldMCP
    from . import mcp_oauth as MOA
    from .mcp_client import McpClient
    conn_hub = CONN.Hub(settings.state_dir, oauth={"chatgpt_plan": chatgpt, "higgsfield": hf_auth},
                        endpoint=lambda: settings.openai_base_url, mcp_clients={"higgsfield": lambda: HiggsfieldMCP(hf_auth)},
                        byok_present=lambda: bool((store.byok() or {}).get("api_key")), transport=connections_transport)
    import httpx as _httpx
    h3d_auth = MOA.for_store(MOA.HYPER3D, conn_hub.store, conn_hub.secrets_dir, redirect_port=settings.port,      # ONE per server: its session lives in the store
                             http=_httpx.Client(transport=connections_transport, timeout=30.0))
    conn_hub.oauth["mcp:hyper3d"] = h3d_auth
    conn_hub.mcp_clients["mcp:hyper3d"] = lambda: McpClient(h3d_auth, url=MOA.HYPER3D.mcp_url, label="Hyper3D", transport=connections_transport)
    CONN.set_active(conn_hub)
    store.migrate_into_connections()                         # finding F3: an older plain BYOK key moves into Connections, verified first

    async def h3d_callback(request: Request):
        """The loopback end of the Hyper3D sign-in Connections starts (POST /app/connections/mcp:hyper3d/signin)."""
        query = {k: v for k, v in request.query_params.items()}
        try:
            await asyncio.to_thread(h3d_auth.complete_login, query)
        except MOA.LoginDeclined as exc:
            return HTMLResponse(f"<p>Hyper3D access was not authorized ({escape(str(exc))}). You can try again from Connections.</p>")
        except MOA.LoginError as exc:
            return HTMLResponse(f"<p class='error'>Sign-in failed: {escape(str(exc))}</p>", status_code=400)
        except Exception as exc:  # noqa: BLE001 - shown to the person at the keyboard, never with a token
            return HTMLResponse(f"<p class='error'>Sign-in could not finish: {escape(type(exc).__name__)}</p>", status_code=502)
        return HTMLResponse("<p>Signed in to Hyper3D. You can close this tab and go back to Connections.</p>")
    routes.append(Route(MOA.HYPER3D.callback_path, h3d_callback, methods=["GET"]))
    from .connections.routes import connection_routes
    routes += connection_routes(lambda: conn_hub, _bearer_ok)
    # ---- Choices (choices/): what serves each purpose, its fallbacks and why; the user's writes; the agent reads and proposes
    from . import choices as CHO
    from .choices.routes import choices_routes
    CHO.set_active(CHO.FileStore(settings.state_dir), settings.state_dir)
    from . import capabilities as CAPS
    from .capabilities.routes import capabilities_routes
    CAPS.set_active(CAPS.Store(settings.state_dir))                             # spec E2: what an agent may do, the user's switches
    try:
        CHO.propose_dead_preferences(store._data.get("preferences") or {})      # HC22: proposed once, never applied silently
    except Exception:  # noqa: BLE001 - a migration note must never stop the server
        logging.getLogger("lampway.choices").warning("the per-role preferences could not be proposed", exc_info=True)
    try:
        from .choices.bridge import import_embed_defaults
        import_embed_defaults(settings.state_dir / "library")                  # HC20: the unwired embedding defaults become Choices, once
    except Exception:  # noqa: BLE001
        logging.getLogger("lampway.choices").warning("the embedding defaults could not be imported", exc_info=True)
    def choice_changed(pid):
        """A saved choice takes effect at once where the settings decide (the Providers dialog's PUT did the same): the agent's
        provider is rebuilt BEFORE it replaces the old one, so a refusal leaves everything as it was."""
        from .choices.bridge import apply_choices
        if pid not in ("agent.main", "agent.worker") and not pid.startswith(("image.", "video.")):
            return
        trial = provider_prefs.trial(settings, {})
        trial.sources = dict(settings.sources)
        apply_choices(trial)
        if pid == "agent.main":
            try:
                new_main = make_provider(trial, chatgpt_auth=chatgpt)
            except (ValueError, RuntimeError, OSError) as exc:
                logging.getLogger("lampway.choices").warning("the main agent's choice could not be built: %s", exc)
                return
            agent.provider = new_main
        _register_endpoint_host(trial.openai_base_url)                # a remote endpoint is the custom_llm route's, off until opted in
        for k in ("provider", "anthropic_model", "openai_model", "openai_base_url", "chatgpt_model", "chatgpt_effort", "openrouter_model", "swarm_provider",
                  "claude_swarm_model", "chatgpt_swarm_model", "openrouter_swarm_model", "image_backend", "image_purposes", "video_purposes"):
            setattr(settings, k, getattr(trial, k))
        settings.sources.update({k: v for k, v in trial.sources.items() if v == "choices"})
    choice_hook.append(choice_changed)
    routes += choices_routes(_bearer_ok, choice_changed)
    routes += capabilities_routes(_bearer_ok)
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

        render_stop = threading.Event()
        render_thread = renderer.start(render_stop) if renderer is not None else None     # one worker thread: due previews, then thumbnails nobody asked for yet

        async def tick():
            while True:
                await asyncio.sleep(60)                            # never a remote check at start: the first poll is a minute in
                try:
                    await jobs.recover()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await asyncio.to_thread(conn_hub.poll)          # C2: reads only, routes on, used in the last day, every 30 min
                except Exception:  # noqa: BLE001
                    logging.getLogger("lampway.connections").warning("the connections poll failed", exc_info=True)
        task = asyncio.get_running_loop().create_task(tick())
        try:
            yield
        finally:
            task.cancel()
            render_stop.set()
            if render_thread is not None:
                render_thread.join(10)                                # a preview in flight finishes before its library closes
            vault.close()

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
    app.state.connections = conn_hub
    app.state.vault = vault
    app.state.jobs = jobs
    app.state.library = library
    app.state.renderer = renderer
    return app
