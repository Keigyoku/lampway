# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hub's HTTP surface (connections_store.md section 4.1). Every route needs the client's bearer. A write also refuses a declared agent
origin and a cross-origin browser request (CONNECTIONS.md section 7.3); no route returns a secret, a pointer's contents or an
environment value."""

import asyncio
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .errors import AGENT_WRITE, Refused

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _agent_declared(request: Request) -> bool:
    return any((request.headers.get(h) or "").strip().lower() == "agent" for h in ("x-lampway-origin", "x-mixar-job-origin"))


def _cross_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    try:
        return (urlparse(origin).hostname or "") not in LOOPBACK
    except ValueError:
        return True


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def connection_routes(get_hub, bearer_ok) -> list:
    def guard(request, write=False):
        if not bearer_ok(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        if write and _agent_declared(request):
            return JSONResponse({"detail": AGENT_WRITE}, status_code=403)
        if write and _cross_origin(request):
            return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
        return None

    def handler(fn, write=False):
        async def route(request: Request):
            if (r := guard(request, write)) is not None:
                return r
            try:
                return JSONResponse(await asyncio.to_thread(fn, get_hub(), request.path_params, await _body(request) if write else {}))
            except Refused as exc:
                return JSONResponse({"detail": str(exc), **({"needs_connection": exc.needs_connection} if getattr(exc, "needs_connection", None) else {})},
                                    status_code=exc.status)
        return route

    def listing(hub, p, b):
        return {"store": hub.store_info(), "scanned_at": hub._read().get("scanned_at"), "connections": hub.view()}

    by = "user"
    return [
        Route("/app/connections", handler(listing), methods=["GET"]),
        Route("/app/connections/scan", handler(lambda h, p, b: h.scan(by), True), methods=["POST"]),
        Route("/app/connections/{cid}", handler(lambda h, p, b: h.one(p["cid"])), methods=["GET"]),
        Route("/app/connections/{cid}/source", handler(lambda h, p, b: h.set_source(p["cid"], str(b.get("mode") or ""), b.get("ref"), by), True), methods=["POST"]),
        Route("/app/connections/{cid}/secret", handler(lambda h, p, b: h.put_secret(p["cid"], b.get("fields"), by), True), methods=["PUT"]),
        Route("/app/connections/{cid}/rotate", handler(lambda h, p, b: h.rotate(p["cid"], b.get("fields"), by), True), methods=["POST"]),
        Route("/app/connections/{cid}/test", handler(lambda h, p, b: h.test(p["cid"], by), True), methods=["POST"]),
        Route("/app/connections/{cid}/signin", handler(lambda h, p, b: h.signin(p["cid"], by), True), methods=["POST"]),
        Route("/app/connections/{cid}/signout", handler(lambda h, p, b: h.signout(p["cid"], by), True), methods=["POST"]),
        Route("/app/connections/{cid}/source/{mode}", handler(lambda h, p, b: h.forget(p["cid"], p["mode"], by), True), methods=["DELETE"]),
        Route("/app/connections/{cid}/move-to-keyring", handler(lambda h, p, b: h.move_to_keyring(p["cid"], by), True), methods=["POST"]),
    ]
