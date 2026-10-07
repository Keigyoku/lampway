# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's model gateway (docs/reports/agent-modes-spec.md E1.4): an OpenAI-compatible endpoint on the existing server, loopback
clients only, for the pinned Hermes of Lampway's own Mode 1 panes (``hermes serve``, spec A1) and for nobody else.

* ``POST /engine/v1/chat/completions`` (streaming SSE and plain JSON) and ``GET /engine/v1/models``; the models list is also answered at
  ``GET /api/v1/models``, because the pinned Hermes asks the ORIGIN of its base_url for it (measured by the coordinator, 2026-10-07).
* Authenticated by a per-engine-process bearer from ``Registry.issue_token(session_id)``: random, held in memory (as a digest), never
  logged (``logredact`` redacts the ``lwe_`` shape). The user's own login is not accepted here, and an engine token opens nothing else.
* A request is translated into Lampway's neutral ``ModelRequest`` and answered by the CURRENT main provider (``app.state.agent.provider``:
  whatever the user chose in Choices, an API key, a bare endpoint or Sign in with ChatGPT), or, for a Mode 1 swarm worker's pane, by
  the ``agent.worker`` choice (spec S2; ``wiring.provider_getter`` decides from the token's session), so Lampway's own egress gate,
  budgets and disclosure apply and the engine holds no key. The gateway never builds a provider and never retries or falls back to another one: a
  provider's failure is an OpenAI-style error object carrying its own recovery text (the ChatGPT usage-limit text, for one).
* ``GET /engine/v1/models-dev.json`` is the engine's models.dev mirror (hermes_config points ``models_dev.url`` at it): a minimal
  registry naming the gateway's model. Hermes fetches it with no key, so it is served to loopback clients without the token; it
  holds no secret. Measured 2026-10-07 with the pinned engine: the child's ``models_dev_cache.json`` is this registry.
* E1.3's start-up check: ``Registry.first_check`` (set by ``engine/wiring.py``) judges the tool list of a token's first request
  that carries tools; a refusal is an OpenAI-style 400 (``engine_tools_mismatch``) for that request and every later one of the token.
* Not carried, because the neutral request has no field for it: ``temperature``, ``max_tokens``, ``stop``, ``tool_choice``, ``usage``
  accounting. Image parts become a text placeholder (the neutral message is text and tool parts).

[UNVERIFIED] against the pinned Hermes beyond the coordinator's measured calls: whether it needs ``usage`` in responses, whether it
sends image parts, and how it reacts to a mid-stream ``error`` event (the OpenAI SDK raises on one).
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import secrets
import threading
import time
from typing import Callable, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from ..agent.providers.base import Message, ModelRequest, Stop, Text, ToolCall, ToolSpec
from ..logredact import redact_text

log = logging.getLogger("lampway.engine.gateway")

PREFIX = "lwe_"                                   # the shape logredact.py redacts
CHAT_PATH = "/engine/v1/chat/completions"
MODELS_PATHS = ("/engine/v1/models", "/api/v1/models")
MODELS_DEV_PATH = "/engine/v1/models-dev.json"   # hermes_config points ``models_dev.url`` here (E1.3)
OLLAMA_PROBE_PATH = "/api/show"                   # the pinned serve's Ollama probe at the base_url's origin (A1): a harmless 404
IMAGE_NOTE = "[image omitted: the engine gateway carries text only]"


class Registry:
    """The engine tokens: one per engine child process, bound to the Lampway session it serves. Held in memory only, as digests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict = {}                          # sha256 hex of the token -> session id
        self.observers: list = []                          # callables (session_id, provider_name), called before each model call
        #: E1.3's start-up check: ``(session_id, token, tools) -> refusal text or None``, run on a token's first request that
        #: carries tools (the tool list the model is sent); its verdict stands for the token's life (engine/wiring.py sets it).
        self.first_check: Optional[Callable] = None
        self._checked: dict = {}                           # sha256 hex of the token -> None (passed) or the refusal text

    def __repr__(self) -> str:
        return f"Registry({len(self._sessions)} tokens)"

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    #: The digest a pane's record keeps instead of its token (spec A1: the pane outlives the server).
    digest = _digest

    def issue_token(self, session_id: str) -> str:
        token = PREFIX + secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[self._digest(token)] = str(session_id)
        return token

    def adopt_digest(self, session_id: str, digest: str) -> None:
        """A token this server issued before a restart, known again by its digest: the Mode 1 pane that holds it (in its own 0600
        config) outlived the server and is re-adopted with its record (spec A1). The token itself is never read back."""
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("a token digest is a sha256 hex string")
        with self._lock:
            self._sessions[digest] = str(session_id)
            self._checked.pop(digest, None)

    def revoke(self, token: str) -> bool:
        with self._lock:
            self._checked.pop(self._digest(token), None)
            return self._sessions.pop(self._digest(token), None) is not None

    def revoke_session(self, session_id: str) -> int:
        with self._lock:
            gone = [d for d, s in self._sessions.items() if s == str(session_id)]
            for d in gone:
                del self._sessions[d]
                self._checked.pop(d, None)
        return len(gone)

    def check_first(self, token: str, session_id: str, tools) -> Optional[str]:
        """None when the request may go on; otherwise the refusal. Only a token's first request with tools is checked; a refused
        token stays refused (the engine's session is refused, E1.3) and a passed one is not checked again."""
        check = self.first_check
        if check is None or not tools:
            return None
        digest = self._digest(token)
        with self._lock:
            if digest in self._checked:
                return self._checked[digest]
        try:
            verdict = check(session_id, token, list(tools))
        except Exception as exc:  # noqa: BLE001 - a check that cannot decide refuses
            log.warning("engine gateway: the start-up check failed: %s", type(exc).__name__)
            verdict = f"refused: the engine's tools could not be checked against your Capabilities ({type(exc).__name__})"
        with self._lock:
            if digest in self._sessions:
                self._checked[digest] = verdict
        return verdict

    def session_for(self, token: str) -> Optional[str]:
        if not token:
            return None
        with self._lock:
            return self._sessions.get(self._digest(token))


ACTIVE: Optional[Registry] = None


def set_active(registry: Optional[Registry]) -> None:
    global ACTIVE
    ACTIVE = registry


def issue_token(session_id: str) -> str:
    """A token for the engine child serving ``session_id`` (the process manager calls this when it starts one)."""
    if ACTIVE is None:
        raise RuntimeError("the engine gateway is not mounted: no server has started")
    return ACTIVE.issue_token(session_id)


def revoke(token: str) -> bool:
    return ACTIVE is not None and ACTIVE.revoke(token)


# ---------------------------------------------------------------------------------------------------- errors
class BadRequest(Exception):
    pass


def error_body(message: str, *, type: str, code: str, param: Optional[str] = None) -> dict:
    return {"error": {"message": redact_text(message), "type": type, "param": param, "code": code}}


def _plan_status(exc) -> tuple:
    from ..agent.providers.chatgpt_plan import ChatGPTPlanError
    table = {"subscription_sharing_usage_limit_exceeded": 429, "subscription_sharing_user_not_eligible": 403,
             "subscription_sharing_unsupported_capability": 400, "subscription_sharing_route_not_supported": 400,
             "subscription_sharing_invalid_user": 424, "subscription_sharing_usage_unavailable": 503,
             "subscription_sharing_user_unavailable": 503, "chatpass_v2_scope_not_authorized": 424,
             "chatpass_v2_invalid_authorization_context": 424}
    assert isinstance(exc, ChatGPTPlanError)
    if exc.code in table:
        return table[exc.code], exc.code
    upstream = exc.status or 0
    if upstream == 429:
        return 429, exc.code or "provider_rate_limited"
    if upstream in (400, 404, 422):
        return 400, exc.code or "provider_rejected_request"
    return 502, exc.code or "provider_error"


def classify(exc: BaseException) -> tuple:
    """(HTTP status, error code) for a provider failure. A 4xx tells the engine not to retry; nothing here picks another provider."""
    from ..egress import EgressRefused
    from ..agent.providers.chatgpt_plan import ChatGPTPlanError
    from ..agent.providers.openrouter import KeyMissing
    from ..chatgpt_auth import NotSignedIn, PlanUsageDisabled, TemporaryAuthError
    if isinstance(exc, EgressRefused):
        return 403, "egress_refused"
    if isinstance(exc, ChatGPTPlanError):
        return _plan_status(exc)
    if isinstance(exc, NotSignedIn):
        return 424, "provider_not_signed_in"
    if isinstance(exc, PlanUsageDisabled):
        return 403, "plan_usage_disabled"
    if isinstance(exc, TemporaryAuthError):
        return 503, "provider_auth_unavailable"
    if isinstance(exc, KeyMissing):
        return 424, "provider_key_missing"
    return 502, "provider_error"


def _error_type(status: int) -> str:
    return {429: "rate_limit_error", 403: "permission_error"}.get(status, "invalid_request_error" if 400 <= status < 500 else "api_error")


def _provider_error(provider, exc: BaseException) -> tuple:
    status, code = classify(exc)
    log.warning("engine gateway: provider %s failed: %s (%s)", getattr(provider, "name", "?"), type(exc).__name__, code)
    return status, error_body(str(exc) or type(exc).__name__, type=_error_type(status), code=code)


# ---------------------------------------------------------------------------------------------------- translation in
def _text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text"):
                out.append(str(part.get("text") or ""))
            elif isinstance(part, dict) and part.get("type") in ("image_url", "input_image", "image"):
                out.append(IMAGE_NOTE)
        return "".join(out)
    raise BadRequest("message content must be a string or a list of content parts")


def _arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {"__invalid_json__": raw}
    return value if isinstance(value, dict) else {"__invalid_json__": raw}


def to_request(body: dict, session_id: str) -> ModelRequest:
    """An OpenAI chat-completions body as Lampway's neutral request. Raises ``BadRequest`` with the reason."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise BadRequest("messages must be a non-empty list")
    if body.get("n") not in (None, 1):
        raise BadRequest("n must be 1: the gateway returns one choice")
    system: list = []
    out: list = []
    for m in messages:
        if not isinstance(m, dict):
            raise BadRequest("each message must be an object")
        role = m.get("role")
        if role in ("system", "developer"):
            system.append(_text_of(m.get("content")))
        elif role == "user":
            out.append(Message("user", [{"type": "text", "text": _text_of(m.get("content"))}]))
        elif role == "assistant":
            parts = [{"type": "text", "text": _text_of(m.get("content"))}] if _text_of(m.get("content")) else []
            for call in m.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                if not (call or {}).get("id") or not fn.get("name"):
                    raise BadRequest("an assistant tool call needs an id and a function name")
                parts.append({"type": "tool_call", "id": call["id"], "name": fn["name"], "arguments": _arguments(fn.get("arguments"))})
            out.append(Message("assistant", parts))
        elif role == "tool":
            call_id = m.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id:
                raise BadRequest("a tool message needs its tool_call_id")
            part = {"type": "tool_result", "tool_call_id": call_id, "content": _text_of(m.get("content")), "is_error": False}
            last = out[-1] if out else None
            if last is not None and last.role == "user" and last.content and all(p.get("type") == "tool_result" for p in last.content):
                last.content.append(part)                                   # the results of one assistant turn travel together, in order
            else:
                out.append(Message("user", [part]))
        else:
            raise BadRequest(f"unsupported message role {role!r}")
    tools = []
    for t in body.get("tools") or []:
        fn = (t or {}).get("function") if isinstance(t, dict) else None
        if not isinstance(t, dict) or t.get("type") != "function" or not isinstance(fn, dict) or not fn.get("name"):
            raise BadRequest("only function tools are supported")
        tools.append(ToolSpec(fn["name"], str(fn.get("description") or ""), fn.get("parameters") or {"type": "object", "properties": {}}))
    return ModelRequest("\n\n".join(s for s in system if s), out, tools, session_id=session_id)


# ---------------------------------------------------------------------------------------------------- translation out
def _finish(stop: str, calls: int) -> str:
    if stop in ("length", "max_tokens", "max_output_tokens"):
        return "length"
    if stop in ("content_filter", "refusal"):
        return "content_filter"
    return "tool_calls" if calls else "stop"


def _model_of(provider) -> str:
    return str(getattr(provider, "model", None) or getattr(provider, "name", None) or "lampway")


class _Completion:
    """Folds a provider's events into OpenAI chunks (streaming) or one message (not)."""

    def __init__(self, model: str):
        self.id = "chatcmpl-" + secrets.token_hex(12)
        self.created = int(time.time())
        self.model = model
        self.text: list = []
        self.calls: list = []
        self.stop = ""

    def chunk(self, delta: dict, finish: Optional[str] = None) -> str:
        obj = {"id": self.id, "object": "chat.completion.chunk", "created": self.created, "model": self.model,
               "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return f"data: {json.dumps(obj)}\n\n"

    def take(self, event) -> Optional[dict]:
        """The streaming delta for one event, or None."""
        if isinstance(event, Text):
            self.text.append(event.text)
            return {"content": event.text} if event.text else None
        if isinstance(event, ToolCall):
            self.calls.append(event)
            return {"tool_calls": [{"index": len(self.calls) - 1, "id": event.id, "type": "function",
                                    "function": {"name": event.name, "arguments": json.dumps(event.arguments)}}]}
        if isinstance(event, Stop):
            self.stop = event.reason
        return None

    def finish_reason(self) -> str:
        return _finish(self.stop, len(self.calls))

    def message(self) -> dict:
        msg: dict = {"role": "assistant", "content": "".join(self.text) or None}
        if self.calls:
            msg["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                 for c in self.calls]
        return msg

    def full(self) -> dict:
        return {"id": self.id, "object": "chat.completion", "created": self.created, "model": self.model,
                "choices": [{"index": 0, "message": self.message(), "finish_reason": self.finish_reason()}]}


# ---------------------------------------------------------------------------------------------------- models.dev
DEFAULT_CONTEXT = 200000          # Hermes's own fallback for an uncatalogued model (agent/models_dev.py at the pin)


def models_dev_registry(provider, model_id: str = "lampway") -> dict:
    """The smallest registry Hermes's ``agent/models_dev.py`` accepts (a non-empty ``{provider: {..., "models": {...}}}``), naming
    the gateway's model ids: the one the engine's config asks for and the current provider's own."""
    window = getattr(provider, "context_length", None)
    window = window if isinstance(window, int) and window > 0 else DEFAULT_CONTEXT
    models = {}
    for mid in dict.fromkeys((model_id, _model_of(provider))):
        models[mid] = {"id": mid, "name": mid, "family": "lampway", "tool_call": True, "reasoning": False, "attachment": False,
                       "temperature": True, "modalities": {"input": ["text"], "output": ["text"]}, "limit": {"context": window},
                       "cost": {"input": 0, "output": 0}}
    return {"lampway": {"id": "lampway", "name": "Lampway gateway", "env": [], "api": "", "doc": "", "models": models}}


# ---------------------------------------------------------------------------------------------------- the routes
def _loopback_client(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def gateway_routes(registry: Registry, provider_getter: Callable) -> list:
    """The gateway's routes. ``provider_getter()`` returns the current main provider at call time (a Choices change swaps it). A
    getter that takes an argument gets the token's session id, so a session can be answered on another choice than the main one:
    ``wiring.provider_getter`` answers a unit's main pane with the current main provider and a Mode 1 worker's pane (its token keyed
    by its swarm binding) with the ``agent.worker`` choice (spec S2 as superseded by A). A getter that cannot build a pane's provider
    raises: that request is an OpenAI-style error, never answered by another provider."""
    import inspect
    try:
        takes_session = len(inspect.signature(provider_getter).parameters) >= 1
    except (TypeError, ValueError):
        takes_session = False

    def provider_for(session_id):
        return provider_getter(session_id) if takes_session else provider_getter()

    def provider_or_error(session_id):
        """(provider, None) or (None, the OpenAI-style error response): a pane whose choice cannot be built is told so."""
        try:
            return provider_for(session_id), None
        except Exception as exc:  # noqa: BLE001 - a missing key, a retired option: reported, never answered by another provider
            status, err = _provider_error(None, exc)
            return None, JSONResponse(err, status_code=status)

    def admit(request: Request):
        """(session id, None) or (None, the refusal response)."""
        if not _loopback_client(request):
            return None, JSONResponse(error_body("the engine gateway answers loopback clients only", type="permission_error", code="not_loopback"), status_code=403)
        session_id = registry.session_for(_bearer(request))
        if session_id is None:
            return None, JSONResponse(error_body("Incorrect API key provided: the engine gateway takes only the key Lampway issued to its engine process.",
                                                 type="invalid_request_error", code="invalid_api_key"), status_code=401)
        return session_id, None

    async def models(request: Request):
        session_id, refused = admit(request)
        if refused is not None:
            return refused
        provider, refused = provider_or_error(session_id)
        if refused is not None:
            return refused
        entry = {"id": _model_of(provider), "object": "model", "created": 0, "owned_by": "lampway"}
        window = getattr(provider, "context_length", None)
        if isinstance(window, int) and window > 0:
            entry["context_length"] = window
        return JSONResponse({"object": "list", "data": [entry]})

    async def models_dev(request: Request):
        """A models.dev registry describing the gateway's model, so the engine's model metadata never needs the network (E1.3).
        Hermes fetches it with a plain GET and no key, so it is served to loopback clients without the token: it carries the
        model's name and context window only, no secret."""
        if not _loopback_client(request):
            return JSONResponse(error_body("the engine gateway answers loopback clients only", type="permission_error", code="not_loopback"), status_code=403)
        return JSONResponse(models_dev_registry(provider_getter()))

    async def chat(request: Request):
        session_id, refused = admit(request)
        if refused is not None:
            return refused
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return JSONResponse(error_body("the request body must be a JSON object", type="invalid_request_error", code="invalid_json"), status_code=400)
        try:
            req = to_request(body, session_id)
        except BadRequest as exc:
            return JSONResponse(error_body(str(exc), type="invalid_request_error", code="invalid_request"), status_code=400)
        refusal = registry.check_first(_bearer(request), session_id, body.get("tools"))
        if refusal is not None:                                        # E1.3: the engine offered what the choices do not allow
            return JSONResponse(error_body(refusal, type="invalid_request_error", code="engine_tools_mismatch"), status_code=400)
        provider, refused = provider_or_error(session_id)
        if refused is not None:
            return refused
        for observer in list(registry.observers):                      # e.g. the island's one-time "Using your ChatGPT plan" notice
            try:
                observer(session_id, getattr(provider, "name", ""))
            except Exception:  # noqa: BLE001 - a listener must never stop a model call
                log.debug("an engine gateway observer failed", exc_info=True)
        done = _Completion(_model_of(provider))
        events = provider.stream(req).__aiter__()
        if not body.get("stream"):
            try:
                async for event in events:
                    done.take(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reported to the engine, never retried here
                status, err = _provider_error(provider, exc)
                return JSONResponse(err, status_code=status)
            return JSONResponse(done.full())
        try:                                                           # before the first event the HTTP status can still carry the failure
            first = await events.__anext__()
        except StopAsyncIteration:
            first = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            status, err = _provider_error(provider, exc)
            return JSONResponse(err, status_code=status)

        async def sse():
            try:
                yield done.chunk({"role": "assistant", "content": ""})
                pending = [] if first is None else [first]
                try:
                    while True:
                        event = pending.pop(0) if pending else await events.__anext__()
                        delta = done.take(event)
                        if delta is not None:
                            yield done.chunk(delta)
                except StopAsyncIteration:
                    yield done.chunk({}, done.finish_reason())
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - after the first byte only an error event can say it
                    _, err = _provider_error(provider, exc)
                    yield f"data: {json.dumps(err)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                aclose = getattr(events, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:  # noqa: BLE001
                        pass

        return StreamingResponse(sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def ollama_probe(request: Request):
        """``POST /api/show`` at the origin of the engine's base_url: the pinned ``hermes serve`` probes a custom endpoint for an
        Ollama model card, with or without the key (measured 2026-10-07, spec A1). Answered here, harmlessly: an OpenAI-style 404
        naming no model, so Hermes keeps its own defaults. The provider is never asked."""
        if not _loopback_client(request):
            return JSONResponse(error_body("the engine gateway answers loopback clients only", type="permission_error", code="not_loopback"), status_code=403)
        return JSONResponse(error_body("this is Lampway's engine gateway, not an Ollama server", type="invalid_request_error",
                                       code="not_ollama"), status_code=404)

    return ([Route(CHAT_PATH, chat, methods=["POST"])] + [Route(p, models, methods=["GET"]) for p in MODELS_PATHS]
            + [Route(MODELS_DEV_PATH, models_dev, methods=["GET"]), Route(OLLAMA_PROBE_PATH, ollama_probe, methods=["POST"])])
