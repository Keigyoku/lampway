"""ChatGPT plan usage as a model provider: the Responses API route of Sign in with ChatGPT, from its documented requirements
(developers.openai.com/siwc/token-sharing-open-source/preview-limitations and models-and-inference).

* ``POST https://api.openai.com/v1/responses`` with the OAuth access token as the bearer; never ChatGPT's backend-api.
* ``store: false``, ``stream: true``; the full history in ``input`` (no ``previous_response_id``); the system prompt as
  ``instructions`` (explicit system-role items are rejected); none of the rejected fields.
* function tools grouped in one namespace; nothing the route does not support (image generation, file search, code
  interpreter, computer use, hosted MCP, tool_search): GPT Image is not available here.
* a stream counts as success only after ``response.completed``; ``response.failed`` stops inference with its exact error code
  and the documented recovery, and nothing falls back to another billing path.

Used only by the agent loop for the signed-in user's own chat turns: there is no endpoint that forwards arbitrary requests to
this route (the terms forbid general-purpose access for other tools).
"""

import json
from typing import AsyncIterator, Optional

import httpx

from .base import Message, ModelRequest, ProviderEvent, Text, ToolCall, ToolSpec

BASE_URL = "https://api.openai.com/v1"
EFFORTS = {"", "minimal", "low", "medium", "high"}                # Responses API reasoning.effort; '' leaves it unset
NAMESPACE = "lampway"
USAGE_URL = "https://chatgpt.com/settings/usage"

_RECOVERY = {
    "subscription_sharing_usage_limit_exceeded": f"Your ChatGPT plan usage limit was reached. Review or raise it at {USAGE_URL} (an app-specific limit may also apply); new requests are paused.",
    "subscription_sharing_user_not_eligible": "ChatGPT plan usage is not available for this user, workspace or policy. This will not work by retrying.",
    "subscription_sharing_usage_unavailable": "Usage availability could not be checked right now; try again later.",
    "subscription_sharing_unsupported_capability": "The request used an unsupported input, tool, model or option for ChatGPT plan usage; it will not be retried unchanged.",
    "subscription_sharing_route_not_supported": "This route is not supported for ChatGPT plan usage (only POST /v1/responses is).",
    "subscription_sharing_invalid_user": "The ChatGPT sign-in could not be validated; sign in again at /app/chatgpt.",
    "subscription_sharing_user_unavailable": "User information is temporarily unavailable; try again later.",
    "chatpass_v2_scope_not_authorized": "The sign-in does not authorize this operation; check the app's grant at ChatGPT settings.",
    "chatpass_v2_invalid_authorization_context": "The sign-in does not authorize this operation; check the app's grant at ChatGPT settings.",
}


class ChatGPTPlanError(RuntimeError):
    def __init__(self, message: str, *, code: str = "", status: Optional[int] = None, param: str = "", request_id: str = ""):
        super().__init__(message)
        self.code, self.status, self.param, self.request_id = code, status, param, request_id


class ChatGPTPlanProvider:
    name = "chatgpt_plan"

    def __init__(self, auth, model: str, *, effort: str = "", base_url: str = BASE_URL, transport=None,
                 http_client: Optional[httpx.AsyncClient] = None, timeout: float = 600.0):
        if effort not in EFFORTS:
            raise ValueError(f"reasoning effort {effort!r} is not one of {sorted(EFFORTS)}")
        self.auth = auth
        self.model = model
        self.effort = effort                                         # '' = the model's default; sent as reasoning.effort
        self.base_url = base_url.rstrip("/")
        self.client = http_client or httpx.AsyncClient(transport=transport, timeout=timeout)

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        token = await self.auth.access_token()                     # NotSignedIn / PlanUsageDisabled stop here, before any request
        body = {"model": self.model, "instructions": request.system, "store": False, "stream": True,
                "input": [item for m in request.messages for item in self._items(m)]}
        if self.effort:
            body["reasoning"] = {"effort": self.effort}
        if request.tools:
            body["tools"] = [self._namespace(request.tools)]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"}
        completed = False
        async with self.client.stream("POST", f"{self.base_url}/responses", json=body, headers=headers) as response:
            rid = response.headers.get("x-request-id", "")
            if response.status_code >= 400:
                text = (await response.aread()).decode("utf-8", "replace")[:600]
                from ...logredact import redact_text
                text = redact_text(text)               # a provider error body never carries a token into a message or log
                raise ChatGPTPlanError(f"ChatGPT plan request refused: HTTP {response.status_code}: {text}",
                                       status=response.status_code, code=self._code_of(text), request_id=rid)
            event_type = ""
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except ValueError:
                    continue
                kind = event.get("type") or event_type
                if kind == "response.output_text.delta" and event.get("delta"):
                    yield Text(event["delta"])
                elif kind == "response.output_item.done" and (event.get("item") or {}).get("type") == "function_call":
                    item = event["item"]
                    try:
                        arguments = json.loads(item.get("arguments") or "{}")
                    except ValueError:
                        arguments = {"__invalid_json__": item.get("arguments")}
                    if not isinstance(arguments, dict):
                        arguments = {"__invalid_json__": item.get("arguments")}
                    yield ToolCall(id=item.get("call_id") or item.get("id") or "", name=item.get("name", ""), arguments=arguments)
                elif kind == "response.failed":
                    err = (event.get("response") or {}).get("error") or {}
                    code = err.get("code") or "unknown_error"
                    raise ChatGPTPlanError(_RECOVERY.get(code) or f"ChatGPT plan request failed: {code}: {err.get('message', '')}",
                                           code=code, param=err.get("param") or "", request_id=rid)
                elif kind == "response.incomplete":
                    reason = ((event.get("response") or {}).get("incomplete_details") or {}).get("reason", "unknown")
                    raise ChatGPTPlanError(f"the response was incomplete ({reason})", code="incomplete", request_id=rid)
                elif kind == "response.completed":
                    completed = True
                    break
        if not completed:
            raise ChatGPTPlanError("the stream ended without response.completed (interrupted); treating the turn as failed")

    @staticmethod
    def _code_of(text: str) -> str:
        try:
            data = json.loads(text)
            return str((data.get("error") or {}).get("code") or "")
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def _namespace(tools: list) -> dict:
        return {"type": "namespace", "name": NAMESPACE, "description": "Tools that work on the user's Blender scene and files.",
                "tools": [{"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters}
                          for t in tools]}

    @staticmethod
    def _items(message: Message) -> list:
        if message.role == "assistant":
            out = []
            if message.text():
                out.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": message.text()}]})
            for p in message.content:
                if p.get("type") == "tool_call":
                    out.append({"type": "function_call", "call_id": p["id"], "name": p["name"], "namespace": NAMESPACE,
                                "arguments": json.dumps(p.get("arguments") or {})})
            return out
        results = [{"type": "function_call_output", "call_id": p["tool_call_id"], "output": p.get("content", "")}
                   for p in message.content if p.get("type") == "tool_result"]
        if results:
            return results
        return [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": message.text()}]}]


#: The disclosure the developer guidance asks for, shown on the model chip and once per session in the transcript (spec R0a).
PLAN_NOTICE = "Using your ChatGPT plan"


async def list_models(auth, *, base_url: str = BASE_URL, transport=None, timeout: float = 15.0) -> list:
    """[{id, label}] of the models the route lists for this account: ``GET /v1/models`` with the access token, keeping only
    entries whose ``visibility`` is ``list`` (spec R0a). The entry keys (``slug`` or ``id``, ``display_name``) follow the research
    of 2026-10-06 and are [UNVERIFIED] against a live account; the live suite (test_chatgpt_live.py) checks the call answers."""
    token = await auth.access_token()
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    out = []
    for entry in (response.json() or {}).get("models") or []:
        if not isinstance(entry, dict) or entry.get("visibility") != "list":
            continue
        mid = str(entry.get("slug") or entry.get("id") or "")
        if mid:
            out.append({"id": mid, "label": str(entry.get("display_name") or mid)})
    return out
