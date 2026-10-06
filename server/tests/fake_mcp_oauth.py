# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A fake MCP server with the standard MCP authorization, shaped like Hyper3D's as measured on 2026-10-05 (specs/studios/hyper3d.md):
an unauthenticated initialize answers 401 with ``WWW-Authenticate: Bearer resource_metadata="<mcp>/.well-known/oauth-protected-resource",
scope="rodin:generate rodin:read"`` (RFC 9728), the authorization server's metadata sits at ``<issuer>/.well-known/oauth-authorization-server``
(RFC 8414), registration is dynamic (RFC 7591), the code exchange checks S256 PKCE, refresh tokens rotate and a reused one is refused.
The MCP endpoint serves initialize, tools/list (the recorded definitions) and tools/call for the seven Rodin tools; every call is recorded."""

import base64
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

MCP = "https://api.hyper3d.com/api/mcp"
AS = "https://api.hyper3d.com/api/grant/oauth"
PRM = MCP + "/.well-known/oauth-protected-resource"
SCOPE = "rodin:generate rodin:read"
TOOLS = json.loads((Path(__file__).parent / "fixtures" / "hyper3d_tools_list.json").read_text(encoding="utf-8"))["tools"]


class FakeMcpOAuth:
    def __init__(self):
        self.registered, self.token_requests, self.calls, self.methods, self.requests = [], [], [], [], []
        self.codes, self.refresh_tokens, self.access_tokens = {}, set(), set()
        self.n = 0
        self.session = "sess-" + uuid.uuid4().hex[:8]
        self.generations = {}

    def transport(self):
        return httpx.MockTransport(self.handler)

    # ------------------------------------------------------------------------------------------------- the browser
    def authorize(self, url: str) -> dict:
        """The person's consent in the browser: returns the callback query the loopback route receives."""
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["code_challenge_method"] == "S256" and q["scope"] == SCOPE and q["resource"] == MCP
        code = "code-" + uuid.uuid4().hex[:8]
        self.codes[code] = (q["code_challenge"], q["client_id"], q["redirect_uri"])
        return {"code": code, "state": q["state"]}

    def _issue(self):
        self.n += 1
        at, rt = f"h3d-access-{self.n}-{uuid.uuid4().hex[:6]}", f"h3d-refresh-{self.n}-{uuid.uuid4().hex[:6]}"
        self.access_tokens.add(at)
        self.refresh_tokens.add(rt)
        return httpx.Response(200, json={"access_token": at, "refresh_token": rt, "expires_in": 3600, "token_type": "Bearer", "scope": SCOPE})

    # ------------------------------------------------------------------------------------------------- the server
    def handler(self, request: httpx.Request):
        url = str(request.url)
        self.requests.append((request.method, url))
        if request.method == "GET" and url == PRM:
            return httpx.Response(200, json={"resource": MCP, "authorization_servers": [AS], "scopes_supported": SCOPE.split()})
        if request.method == "GET" and url == AS + "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json={"issuer": AS, "authorization_endpoint": AS + "/authorize", "token_endpoint": AS + "/token",
                                             "registration_endpoint": AS + "/register", "code_challenge_methods_supported": ["S256"]})
        if url == AS + "/register":
            body = json.loads(request.content)
            self.registered.append(body)
            return httpx.Response(201, json={"client_id": f"client-{len(self.registered)}", **body})
        if url == AS + "/token":
            body = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(body)
            if body.get("grant_type") == "authorization_code":
                challenge, client, redirect = self.codes.pop(body.get("code"), (None, None, None))
                digest = base64.urlsafe_b64encode(hashlib.sha256(body.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
                if challenge is None or digest != challenge or client != body.get("client_id") or redirect != body.get("redirect_uri"):
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return self._issue()
            if body.get("grant_type") == "refresh_token":
                if body.get("refresh_token") not in self.refresh_tokens:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                self.refresh_tokens.discard(body["refresh_token"])
                return self._issue()
            return httpx.Response(400, json={"error": "unsupported_grant_type"})
        if url == MCP:
            return self._mcp(request)
        return httpx.Response(404, json={})

    def _mcp(self, request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] not in self.access_tokens:
            return httpx.Response(401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{PRM}", scope="{SCOPE}"'}, json={})
        msg = json.loads(request.content)
        self.methods.append(msg.get("method"))
        if msg.get("id") is None:
            return httpx.Response(202)
        if msg["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": self.session}, json={"jsonrpc": "2.0", "id": msg["id"], "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "hyper3d-rodin", "version": "1.0.0"}}})
        if msg["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS}})
        if msg["method"] == "tools/call":
            name, args = msg["params"]["name"], msg["params"].get("arguments") or {}
            self.calls.append((name, args))
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"structuredContent": self._tool(name, args), "isError": False}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "no method"}})

    def _tool(self, name, args):
        if name == "rodin_create_uploads":
            return {"uploads": [{"upload_id": f"up-{i}", "upload_url": f"https://uploads.hyper3d.com/put/{i}?sig=x", "filename": f["filename"]}
                                for i, f in enumerate(args.get("files") or [])]}
        if name in ("rodin_generate", "rodin_generate_bang"):
            gid = f"gen-{len(self.generations) + 1}"
            self.generations[gid] = name
            return {"generation_id": gid, "display_url": f"https://hyper3d.ai/g/{gid}"}
        if name in ("rodin_get_status", "rodin_wait"):
            return {"generation_id": args["generation_id"], "status": "Done", "stage": {"name": "done", "current": 3, "total": 3}}
        if name == "rodin_get_result":
            return {"generation_id": args["generation_id"], "files": [{"role": "model", "url": "https://files.hyper3d.com/m.glb?sig=x", "name": "m.glb"}]}
        return {}
