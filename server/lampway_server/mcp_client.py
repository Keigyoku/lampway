# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small MCP client (streamable HTTP, JSON-RPC 2.0) over Lampway's own MCP sign-in (``mcp_oauth``), for any studio: ``initialize``
opens a session (``Mcp-Session-Id`` on every later call), ``tools/list`` is cached, ``tools/call`` returns the tool's structured result.
A 401 refreshes the token once and retries; a lost session re-initialises once. A transport timeout is its own error: the request may
already have been accepted, so callers must NEVER resubmit on it (poll the job instead). No token appears in any error text.
"""

import itertools
import json
import threading
from typing import Optional

import httpx

PROTOCOL = "2025-06-18"


class MCPError(RuntimeError):
    pass


class ToolError(MCPError):
    """The tool ran and reported an error (``isError``)."""


class TransportTimeout(MCPError):
    pass


class McpClient:
    def __init__(self, auth, *, url: str, label: str, page: str = "Connections", transport=None, timeout: float = 60.0):
        self.auth = auth
        self.url = url
        self.label, self.page = label, page
        self._transport = transport
        self._timeout = timeout
        self._session: Optional[str] = None
        self._tools: Optional[list] = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- transport
    def _post(self, body: dict, retry: bool = True):
        token = self.auth._access_token_sync()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL}
        if self._session and body.get("method") != "initialize":
            headers["Mcp-Session-Id"] = self._session
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                resp = client.post(self.url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise TransportTimeout(f"{self.label} did not answer in time ({type(exc).__name__}); the request may have been accepted and was NOT resubmitted") from None
        except httpx.RequestError as exc:
            raise MCPError(f"could not reach {self.label} ({type(exc).__name__})") from None
        if resp.status_code == 401 and retry:
            self.auth.invalidate_access_token()
            self._session = None
            return self._post_after_init(body)
        if resp.status_code == 404 and retry and self._session and body.get("method") != "initialize":
            self._session = None
            return self._post_after_init(body)
        if resp.status_code == 401:
            from .mcp_oauth import NotSignedIn
            where = "from Connections" if self.page == "Connections" else f"at {self.page}"
            raise NotSignedIn(f"{self.label} rejected the session: sign in again {where}")
        if resp.status_code >= 400:
            raise MCPError(f"{self.label} answered HTTP {resp.status_code}")
        return resp

    def _post_after_init(self, body: dict):
        self._initialize()
        return self._post(body, retry=False)

    @staticmethod
    def _message(resp, mid) -> dict:
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("id") == mid:
                        return msg
            raise MCPError("the event stream ended without an answer")
        return resp.json()

    def _rpc(self, method: str, params: Optional[dict] = None):
        mid = next(self._ids)
        body = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            body["params"] = params
        resp = self._post(body)
        if method == "initialize" and resp.headers.get("mcp-session-id"):
            self._session = resp.headers["mcp-session-id"]
        msg = self._message(resp, mid)
        if "error" in msg:
            raise MCPError(f"{method}: {msg['error'].get('message', 'error')}")
        return msg.get("result")

    def _initialize(self) -> None:
        self._session = None
        self._rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "Lampway", "version": "1"}})
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, retry=False)
        except MCPError:
            pass

    # ------------------------------------------------------------------------ API
    def _ready(self) -> None:
        if self._session is None:
            self._initialize()

    def tools(self) -> list:
        with self._lock:
            if self._tools is None:
                self._ready()
                self._tools = (self._rpc("tools/list") or {}).get("tools") or []
            return self._tools

    def has_tool(self, name: str) -> bool:
        return any(t.get("name") == name for t in self.tools())

    def call(self, name: str, arguments: Optional[dict] = None) -> dict:
        """The tool's structured result as a dict (the structuredContent, else the JSON in its first text block, else {"text": ...})."""
        with self._lock:
            self._ready()
            result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}}) or {}
        text = "\n".join(c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text")
        if result.get("isError"):
            raise ToolError(text[:500] or f"{name} failed")
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {"result": data}
        except ValueError:
            return {"text": text}
