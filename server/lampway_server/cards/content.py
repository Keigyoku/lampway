"""The card content server (specs/mrmak/09-report-cards.md section 6.4): report pages are untrusted HTML to the UI, so they are served on their OWN loopback origin (a second
port; a page's script can never read the API's token), by GET and HEAD only, to the server's own Host only (421 otherwise), under a random grant per served root, inside a
realpath jail, with private names refused (dot-names, node_modules, target, oauth_*.json, *_secret*.json, token(s).json, auth.json) and byte ranges answered (206 / 416)."""
from __future__ import annotations

import mimetypes
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .registry import CardError

PRIVATE = re.compile(r"^(\..*|node_modules|target|oauth_.*\.json|.*_secret.*\.json|tokens?\.json|auth\.json)$", re.IGNORECASE)
LOOPBACK = ("127.0.0.1", "localhost", "::1")
HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cross-Origin-Resource-Policy": "same-site", "Accept-Ranges": "bytes",
           "Cache-Control": "no-store"}


class ContentServer:
    def __init__(self, root, host: str = "127.0.0.1", port: int = 0, api_port: int = 8787):
        if port and port == api_port:
            raise CardError("the content server needs its own port: a report on the API's origin could read the API token")
        self.root, self.host, self.api_port = Path(root), host, api_port
        self.port = port                       # 0 = the operating system picks one when ``serve`` binds
        self._grants: dict = {}
        self.app = Starlette(routes=[Route("/view/{grant}/{path:path}", self._serve, methods=["GET", "HEAD"])])

    def origin(self) -> str:
        if not self.port:
            raise CardError("the content server is not serving yet: serve() first")
        return f"http://{self.host}:{self.port}"

    def serve(self, timeout: float = 10.0) -> str:
        """Start uvicorn on its own thread (a daemon: it ends with the server) and learn the port it bound; the origin is never the API's."""
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning", lifespan="off"))
        threading.Thread(target=server.run, name="lampway-cards-content", daemon=True).start()
        deadline = time.monotonic() + timeout
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            raise CardError("the content server did not start: is the loopback port free?")
        self.port = server.servers[0].sockets[0].getsockname()[1]
        if self.port == self.api_port:
            server.should_exit = True
            raise CardError("the content server needs its own port: a report on the API's origin could read the API token")
        return self.origin()

    def grant(self, root=None) -> str:
        root = str(Path(root or self.root).resolve())
        for token, r in self._grants.items():
            if r == root:
                return token
        token = secrets.token_urlsafe(32)
        self._grants[token] = root
        return token

    def url(self, rel: str, root=None) -> str:
        return f"{self.origin()}/view/{self.grant(root)}/{rel}"

    def _host_ok(self, request: Request) -> bool:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        return host in LOOPBACK or host == self.host

    def _file(self, grant: str, rel: str):
        root = self._grants.get(grant)
        if root is None:
            return None, 404
        rel = unquote(rel)
        if any(PRIVATE.match(p) for p in Path(rel).parts):
            return None, 403
        full = Path(os.path.realpath(Path(root) / rel))
        if full != Path(root) and Path(root) not in full.parents:
            return None, 403
        if not full.is_file():
            return None, 404
        return full, 200

    async def _serve(self, request: Request):
        if not self._host_ok(request):
            return Response("misdirected request", status_code=421, headers=HEADERS)
        full, status = self._file(request.path_params["grant"], request.path_params["path"])
        if full is None:
            return Response("not found" if status == 404 else "refused", status_code=status, headers=HEADERS)
        size = full.stat().st_size
        ctype = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
        start, end, status = 0, size - 1, 200
        rng = request.headers.get("range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                return Response(status_code=416, headers={**HEADERS, "Content-Range": f"bytes */{size}"})
            if m.group(1) == "":
                start = max(0, size - int(m.group(2)))
            else:
                start, end = int(m.group(1)), int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            if start >= size or start > end:
                return Response(status_code=416, headers={**HEADERS, "Content-Range": f"bytes */{size}"})
            status = 206
        headers = {**HEADERS, "Content-Length": str(end - start + 1)}
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        if request.method == "HEAD":
            return Response(status_code=status, headers=headers, media_type=ctype)
        with open(full, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        return Response(data, status_code=status, headers=headers, media_type=ctype)
