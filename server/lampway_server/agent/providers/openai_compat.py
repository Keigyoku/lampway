"""An OpenAI-compatible chat-completions provider (Ollama, LM Studio, llama.cpp,
vLLM, OpenAI itself, ...) over plain httpx. The key, when there is one, is the
``api_key`` the caller passes (read from the environment in make_provider) and is
only ever placed in the Authorization header."""

import json
from typing import AsyncIterator, Optional

import httpx

from .base import Message, ModelRequest, ProviderEvent, Stop, Text, ToolCall, ToolSpec


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, base_url: str, model: str, api_key: str = "", *, transport=None,
                 http_client: Optional[httpx.AsyncClient] = None, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or ""
        self.client = http_client or httpx.AsyncClient(transport=transport, timeout=timeout)

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        body = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "system", "content": request.system}]
            + [m for message in request.messages for m in self._messages(message)],
        }
        if request.tools:
            body["tools"] = [self._tool(t) for t in request.tools]
        body.update(self._extra_body())
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream", **self._extra_headers()}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._before_request()
        calls: dict[int, dict] = {}
        finish = ""
        async with self.client.stream("POST", f"{self.base_url}/chat/completions", json=body,
                                      headers=headers) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:500]
                raise RuntimeError(self._http_error(response.status_code, detail))
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                self._on_chunk(chunk)
                for choice in chunk.get("choices") or []:
                    finish = choice.get("finish_reason") or finish
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield Text(delta["content"])
                    for call in delta.get("tool_calls") or []:
                        slot = calls.setdefault(call.get("index", 0), {"id": "", "name": "", "arguments": ""})
                        slot["id"] = call.get("id") or slot["id"]
                        function = call.get("function") or {}
                        slot["name"] = function.get("name") or slot["name"]
                        slot["arguments"] += function.get("arguments") or ""
        for index in sorted(calls):
            slot = calls[index]
            try:
                arguments = json.loads(slot["arguments"] or "{}")
            except ValueError:
                arguments = {"__invalid_json__": slot["arguments"]}
            if not isinstance(arguments, dict):
                arguments = {"__invalid_json__": slot["arguments"]}
            yield ToolCall(id=slot["id"] or f"call_{index}", name=slot["name"], arguments=arguments)
        if finish and finish not in ("stop", "tool_calls"):     # only the abnormal ones: length, content_filter, ...
            yield Stop(finish)

    # ------------------------------------------------------------ seams for gateways that add to the protocol
    def _extra_body(self) -> dict:
        return {}

    def _extra_headers(self) -> dict:
        return {}

    def _before_request(self) -> None:
        """Called once per model call, before anything is sent; raising refuses the call."""

    def _on_chunk(self, chunk: dict) -> None:
        """Called with every decoded SSE chunk."""

    def _http_error(self, status: int, detail: str) -> str:
        return f"{self.base_url} answered HTTP {status}: {self._redact(detail)}"

    def _redact(self, text: str) -> str:
        """The configured key, and any bearer value, never reach a message (an OpenAI-compatible server can echo the
        Authorization value in an error body)."""
        import re
        out = str(text)
        if self._api_key:
            out = out.replace(self._api_key, "[redacted]")
        return re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}", "Bearer [redacted]", out)

    # ------------------------------------------------------------ translation
    @staticmethod
    def _tool(tool: ToolSpec) -> dict:
        return {"type": "function", "function": {
            "name": tool.name, "description": tool.description, "parameters": tool.parameters}}

    @staticmethod
    def _messages(message: Message) -> list[dict]:
        if message.role == "assistant":
            out = {"role": "assistant", "content": message.text() or None}
            calls = [{"id": p["id"], "type": "function", "function": {
                "name": p["name"], "arguments": json.dumps(p.get("arguments") or {})}}
                for p in message.content if p.get("type") == "tool_call"]
            if calls:
                out["tool_calls"] = calls
            return [out]
        results = [{"role": "tool", "tool_call_id": p["tool_call_id"], "content": p.get("content", "")}
                   for p in message.content if p.get("type") == "tool_result"]
        if results:
            return results
        return [{"role": "user", "content": message.text()}]
