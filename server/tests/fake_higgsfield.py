"""A fake Higgsfield, built from the coordinator's SPEC (scratch/subs/higgsfield/SPEC.md): the Clerk OAuth endpoints (dynamic client
registration, authorize/token with S256 PKCE, refresh rotation) and the MCP endpoint (streamable HTTP JSON-RPC: initialize, tools/list,
tools/call for models_explore, balance, generate_video / generate_image with get_cost and unlim_choice, media_upload + the presigned PUT +
media_confirm, jobs_wait, motion_control). The response BODY shapes of the tools are an assumption (the SPEC gives names and params);
the live read-only diff after sign-in is what checks them."""

import base64
import hashlib
import json
import uuid
from urllib.parse import parse_qs, urlparse

import httpx

MCP = "https://mcp.higgsfield.ai/mcp"
AS = "https://clerk.higgsfield.ai"
META = "https://mcp.higgsfield.ai/.well-known/oauth-protected-resource/mcp"

MODELS = {
    "video": [
        {"id": "seedance1_5", "name": "Seedance 1.5 Pro", "durations": [4, 8, 12], "resolutions": ["480p", "720p", "1080p"],
         "aspect_ratios": ["16:9", "9:16", "1:1"], "medias": [{"roles": ["start_image", "end_image"]}], "supports_audio": False},
        {"id": "seedance_2_0", "name": "Seedance 2.0", "durations": list(range(4, 16)), "resolutions": ["480p", "720p", "1080p", "4k"],
         "aspect_ratios": ["16:9", "9:16", "1:1"], "medias": [{"roles": ["start_image", "end_image", "image_references", "video_references", "audio_references"]}],
         "supports_unlim": True},
        {"id": "hf_mult_motion_control", "name": "Genjutsu (motion transfer)", "durations": [5, 10], "resolutions": ["720p"],
         "aspect_ratios": ["16:9", "9:16"], "medias": [{"roles": ["image_references", "video_references"]}]},
    ],
    "image": [{"id": "gpt_image_2_5", "name": "GPT Image 2.5", "aspect_ratios": ["1:1", "3:2", "2:3"], "resolutions": ["1k", "2k"]}],
}
COSTS = {"seedance1_5": 9.6, "seedance_2_0": 45.0, "hf_mult_motion_control": 30.0, "gpt_image_2_5": 3.0}


class FakeHiggsfield:
    def __init__(self):
        self.calls = []                     # (tool, arguments) for every tools/call
        self.puts = []                      # (url, bytes) presigned uploads
        self.registered = []
        self.token_requests = []
        self.session = "sess-" + uuid.uuid4().hex[:8]
        self.codes = {}
        self.access = {}                    # access token -> refresh token it came from
        self.refresh_tokens = set()
        self.fail_next_generate = None      # 'timeout' to simulate a transport timeout on generate
        self.unlim_question = False
        self.job_status = ["queued", "in_progress", "completed"]
        self.jobs = {}
        self.media = {}
        self.balance = 623.86
        self.unauthorised_once = False

    # ---------------------------------------------------------------- transport
    def transport(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        if request.method == "PUT" and "upload.higgsfield.test" in url:
            self.puts.append((url, request.content))
            return httpx.Response(200)
        if url == META:
            return httpx.Response(200, json={"resource": MCP, "authorization_servers": [AS, "https://fnf-device-auth.higgsfield.ai"],
                                              "scopes_supported": ["openid", "email", "offline_access"]})
        if url.startswith(AS + "/.well-known/oauth-authorization-server"):
            return httpx.Response(200, json={"issuer": AS, "authorization_endpoint": AS + "/oauth/authorize", "token_endpoint": AS + "/oauth/token",
                                              "registration_endpoint": AS + "/oauth/register", "code_challenge_methods_supported": ["S256"],
                                              "grant_types_supported": ["authorization_code", "refresh_token"]})
        if url == AS + "/oauth/register":
            body = json.loads(request.content)
            self.registered.append(body)
            return httpx.Response(201, json={"client_id": "hf-client-" + uuid.uuid4().hex[:6], **body})
        if url == AS + "/oauth/token":
            return self._token(parse_qs(request.content.decode()))
        if url == MCP:
            return self._mcp(request)
        return httpx.Response(404)

    # -------------------------------------------------------------------- oauth
    def authorize(self, authorize_url: str) -> dict:
        """What the browser does: the authorize URL -> the callback query the server receives."""
        q = {k: v[0] for k, v in parse_qs(urlparse(authorize_url).query).items()}
        code = "code-" + uuid.uuid4().hex
        self.codes[code] = {"challenge": q["code_challenge"], "client_id": q["client_id"], "redirect_uri": q["redirect_uri"]}
        return {"code": code, "state": q["state"]}

    def _token(self, form):
        f = {k: v[0] for k, v in form.items()}
        self.token_requests.append(f)
        if f["grant_type"] == "authorization_code":
            info = self.codes.pop(f.get("code"), None)
            if not info or info["client_id"] != f["client_id"] or info["redirect_uri"] != f["redirect_uri"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            digest = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            if digest != info["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "pkce"})
        elif f["grant_type"] == "refresh_token":
            if f["refresh_token"] not in self.refresh_tokens:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.refresh_tokens.discard(f["refresh_token"])            # rotation: a refresh token works once
        else:
            return httpx.Response(400, json={"error": "unsupported_grant_type"})
        access, refresh = "hf-access-" + uuid.uuid4().hex, "hf-refresh-" + uuid.uuid4().hex
        self.access[access] = refresh
        self.refresh_tokens.add(refresh)
        return httpx.Response(200, json={"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": 3600,
                                         "scope": "openid email offline_access"})

    # ---------------------------------------------------------------------- mcp
    def _mcp(self, request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] not in self.access or self.unauthorised_once:
            self.unauthorised_once = False
            return httpx.Response(401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{META}", scope="openid email offline_access"'})
        msg = json.loads(request.content)
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            return httpx.Response(200, headers={"Mcp-Session-Id": self.session}, json={"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "higgsfield", "version": "1"}}})
        if request.headers.get("mcp-session-id") != self.session:
            return httpx.Response(404, json={"error": "unknown session"})
        if mid is None:
            return httpx.Response(202)
        if method == "tools/list":
            return self._ok(mid, {"tools": [{"name": n, "description": n, "inputSchema": {"type": "object"}} for n in (
                "models_explore", "generate_video", "generate_image", "media_upload", "media_confirm", "jobs_wait", "motion_control",
                "balance", "transactions", "generate_video_batch", "show_generation_by_ids", "media_import_url")]})
        if method == "tools/call":
            name, args = msg["params"]["name"], msg["params"].get("arguments") or {}
            self.calls.append((name, args))
            fn = getattr(self, "tool_" + name, None)
            if fn is None:
                return self._ok(mid, {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True})
            out = fn(args)
            if isinstance(out, httpx.Response):
                return out
            return self._ok(mid, {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out, "isError": False})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "no such method"}})

    @staticmethod
    def _ok(mid, result):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": mid, "result": result})

    # -------------------------------------------------------------------- tools
    def tool_balance(self, a):
        return {"plan": "plus", "credits": self.balance}

    def tool_models_explore(self, a):
        kind = a.get("type") or "video"
        if a.get("action") == "get":
            return next((m for m in MODELS.get(kind, []) if m["id"] == a.get("model_id")), {"error": "not found"})
        return {"models": MODELS.get(kind, [])}

    def _generate(self, a, kind):
        if self.fail_next_generate == "timeout":
            self.fail_next_generate = None
            raise httpx.ReadTimeout("simulated transport timeout")
        mid = a["model"]
        if a.get("get_cost"):
            return {"get_cost": True, "credits": COSTS.get(mid, 5.0), "model": mid}
        if self.unlim_question and a.get("use_unlim") is None and mid == "seedance_2_0":
            return {"unlim_choice": {"question": "Use your unlimited allowance for this generation?", "options": [True, False]}}
        count = int(a.get("count") or 1)
        ids = []
        for _ in range(count):
            jid = "job-" + uuid.uuid4().hex[:8]
            self.jobs[jid] = {"polls": 0, "kind": kind, "model": mid}
            ids.append(jid)
        return {"jobs": [{"index": i, "job_id": j} for i, j in enumerate(ids)]}

    def tool_generate_video(self, a):
        return self._generate(a, "video")

    def tool_generate_image(self, a):
        return self._generate(a, "image")

    def tool_motion_control(self, a):
        if a.get("get_cost"):
            return {"get_cost": True, "credits": 24.0}
        jid = "job-" + uuid.uuid4().hex[:8]
        self.jobs[jid] = {"polls": 0, "kind": "video", "model": "kling3_motion"}
        return {"jobs": [{"index": 0, "job_id": jid}]}

    def tool_media_upload(self, a):
        out = []
        for i, f in enumerate(a.get("files") or [{}]):
            mid = "media-" + uuid.uuid4().hex[:8]
            self.media[mid] = {"type": a.get("type")}
            out.append({"media_id": mid, "upload_url": f"https://upload.higgsfield.test/{mid}", "content_type": f.get("content_type")})
        return {"uploads": out}

    def tool_media_confirm(self, a):
        return {"confirmed": a.get("media_ids") or [a.get("media_id")]}

    def tool_jobs_wait(self, a):
        assert a.get("timeout_seconds", 15) <= 15
        rows = []
        for j in a["jobs"]:
            st = self.jobs[j["job_id"]]
            st["polls"] += 1
            status = self.job_status[min(st["polls"] - 1, len(self.job_status) - 1)]
            row = {"index": j.get("index", 0), "job_id": j["job_id"], "status": status}
            if status == "completed":
                ext = "mp4" if st["kind"] == "video" else "png"
                row["result_url"] = f"https://cdn.higgsfield.test/{j['job_id']}.{ext}"
            rows.append(row)
        return {"jobs": rows}
