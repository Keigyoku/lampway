"""REST endpoints beyond auth: the house envelope, ETag revalidation, and the
stubs that keep the client quiet (telemetry, updates, meter, catalogues,
notifications, referrals) plus the agent settings store."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .agent_settings import known_models, models_catalog

CATALOG_VERSION = "lampway-v0"


def envelope(data, message="ok") -> dict:
    return {"status": "success", "message": message, "data": data}


def ok(data, message="ok") -> JSONResponse:
    return JSONResponse(envelope(data, message))


def error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status_code)


def cached(request: Request, body: dict) -> Response:
    """Answer with an ETag; 304 when the client's If-None-Match already has it."""
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    etag = '"' + hashlib.sha1(encoded).hexdigest() + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(encoded, media_type="application/json", headers={"ETag": etag})


def require_bearer(auth):
    def decorator(handler):
        @wraps(handler)
        async def guarded(request: Request):
            header = request.headers.get("authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else ""
            if not token or auth.verify_access(token) is None:
                return error(401, "Not authenticated")
            return await handler(request)
        return guarded
    return decorator


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def stub_routes(auth, store, settings):
    guard = require_bearer(auth)

    @guard
    async def sounds(request):
        return cached(request, envelope({"sounds": []}))

    @guard
    async def client_version(request):
        return ok({})

    @guard
    async def updates_check(request):
        current = request.query_params.get("current_version", "")
        return ok({"update_available": False, "current_version": current, "latest_version": current})

    @guard
    async def subscription_status(request):
        now = datetime.now(timezone.utc)
        cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cycle_end = (cycle_start + timedelta(days=32)).replace(day=1)
        return ok({
            "plan_slug": "lampway-local", "plan_name": "Lampway (local)", "billing_interval": "month",
            "credits_per_month": settings.fake_credits, "balance_cents": 0, "plan_value_cents": 0,
            "usage_pct": 0, "cycle_start": cycle_start.isoformat(), "cycle_end": cycle_end.isoformat(),
            "days_left": max(0, (cycle_end - now).days), "subscription_expires_at": None,
        })

    @guard
    async def generation_catalog(request):
        return cached(request, envelope({
            "catalog_version": CATALOG_VERSION, "capabilities": [], "styles": {}, "credit_costs": {},
        }))

    @guard
    async def chat_options(request):
        return cached(request, envelope({"catalog_version": CATALOG_VERSION, "options": []}))

    @guard
    async def agent_models(request):
        return cached(request, envelope(models_catalog(settings)))

    @guard
    async def credentials_get(request):
        return ok(store.credentials_view())

    @guard
    async def byok_put(request):
        body = await _json(request)
        provider, model = body.get("provider"), body.get("model")
        if not provider or not model:
            return error(422, "provider and model are required")
        return ok(store.save_byok(provider, model, body.get("api_key"), body.get("base_url"),
                                  body.get("supports_vision")), "Credentials saved")

    @guard
    async def credentials_delete_all(request):
        return ok({"removed": store.delete_byok()})

    @guard
    async def preference_get(request):
        return ok(store.preference_view())

    @guard
    async def preference_put(request):
        body = await _json(request)
        provider, model = body.get("provider"), body.get("model")
        role = body.get("role") or "default"
        if not provider or not model:
            return error(422, "provider and model are required")
        if (provider, model) not in known_models(settings):
            return error(400, f"Model not available: {provider}/{model}")
        label = next(m["label"] for p in models_catalog(settings)["providers"] if p["id"] == provider
                     for m in p["models"] if m["id"] == model)
        return ok(store.save_preference(role, provider, model, label, body.get("thinking_level")))

    @guard
    async def preference_delete_role(request):
        if not store.delete_preference(request.path_params["role"]):
            return error(404, "No preference for that role")
        return ok({"removed": 1})

    @guard
    async def preference_delete_all(request):
        return ok({"removed": store.delete_all_preferences()})

    @guard
    async def referrals_dashboard(request):
        return ok({"invite_url": "", "award_amounts": {"invitee": 0, "inviter": 0, "paid_total": 0},
                   "qualified_count": 0})

    @guard
    async def telemetry(request):
        await request.body()  # read and discard
        return ok({"accepted": 0})

    return [
        Route("/api/v1/notifications/sounds", sounds, methods=["GET"]),
        Route("/api/v1/notifications/me/client-version", client_version, methods=["PUT"]),
        Route("/api/v1/updates/check", updates_check, methods=["GET"]),
        Route("/api/v1/subscriptions/status", subscription_status, methods=["GET"]),
        Route("/api/v1/generation-catalog", generation_catalog, methods=["GET"]),
        Route("/api/v1/generation-catalog/chat-options", chat_options, methods=["GET"]),
        Route("/api/v1/agent/models", agent_models, methods=["GET"]),
        Route("/api/v1/agent/credentials", credentials_get, methods=["GET"]),
        Route("/api/v1/agent/byok", byok_put, methods=["PUT"]),
        Route("/api/v1/agent/credentials/all", credentials_delete_all, methods=["DELETE"]),
        Route("/api/v1/agent/model-preference", preference_get, methods=["GET"]),
        Route("/api/v1/agent/model-preference", preference_put, methods=["PUT"]),
        Route("/api/v1/agent/model-preference", preference_delete_all, methods=["DELETE"]),
        Route("/api/v1/agent/model-preference/{role}", preference_delete_role, methods=["DELETE"]),
        Route("/api/v1/referrals/dashboard", referrals_dashboard, methods=["GET"]),
        Route("/api/v1/telemetry/events", telemetry, methods=["POST"]),
    ]
