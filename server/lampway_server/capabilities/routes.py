# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Capabilities routes (docs/reports/agent-modes-spec.md E2). Every route needs the bearer; a change also refuses a declared
agent origin and a cross-origin request, so only the user's click in the Client changes what an agent may do.

* ``GET /app/capabilities[?project=]``: the board and the open proposals.
* ``PUT /app/capabilities/{id}``: the user's switch (``enabled``, ``approval``, ``options``, ``project``).
* ``DELETE /app/capabilities/{id}?project=<root>``: drop that project's override, back to the global value.
* ``POST /app/capabilities/proposals/{pid}`` with ``{"action": "accept"|"decline", "project"?}``: the user's answer to an agent's
  proposal; accept applies it (to ``project`` when given), and both take it off the open list."""

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..connections.routes import _agent_declared, _body, _cross_origin
from . import AGENT_WRITE, Refused, UnknownCapability


def capabilities_routes(bearer_ok) -> list:
    from .. import capabilities as CAP

    def guard(request, write=False):
        if not bearer_ok(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        if write and (_agent_declared(request) or _cross_origin(request)):
            return JSONResponse({"detail": AGENT_WRITE}, status_code=403)
        if CAP.ACTIVE is None:
            return JSONResponse({"detail": "the Capabilities board is not available"}, status_code=503)
        return None

    def row(cid, project):
        if cid in {c.id for c in CAP.CATALOGUE}:
            return next(r for r in CAP.ACTIVE.view(project) if r["id"] == cid)
        return {"id": cid, **CAP.ACTIVE.setting(cid, project)}

    async def listing(request: Request):
        if (r := guard(request)) is not None:
            return r
        project = request.query_params.get("project") or None
        rows = await asyncio.to_thread(CAP.ACTIVE.view, project)
        return JSONResponse({"capabilities": rows, "proposals": CAP.ACTIVE.proposals()})

    async def put(request: Request):
        if (r := guard(request, write=True)) is not None:
            return r
        body = await _body(request)
        cid = request.path_params["cid"]
        try:
            await asyncio.to_thread(CAP.ACTIVE.set, cid, enabled=body.get("enabled"), approval=body.get("approval"),
                                    options=body.get("options"), project=body.get("project"), by="user")
        except UnknownCapability:
            return JSONResponse({"detail": f"no capability {cid!r}"}, status_code=404)
        except Refused as exc:
            return JSONResponse({"detail": str(exc)}, status_code=exc.status)
        return JSONResponse(row(cid, body.get("project")))

    async def delete(request: Request):
        if (r := guard(request, write=True)) is not None:
            return r
        cid = request.path_params["cid"]
        project = request.query_params.get("project") or None
        try:
            await asyncio.to_thread(CAP.ACTIVE.clear, cid, project, by="user")
        except UnknownCapability:
            return JSONResponse({"detail": f"no capability {cid!r}"}, status_code=404)
        except Refused as exc:
            return JSONResponse({"detail": str(exc)}, status_code=exc.status)
        return JSONResponse(row(cid, project))

    async def decide(request: Request):
        if (r := guard(request, write=True)) is not None:
            return r
        body = await _body(request)
        try:
            done = await asyncio.to_thread(CAP.ACTIVE.decide, request.path_params["pid"], body.get("action"),
                                           project=body.get("project") or None, by="user")
        except UnknownCapability as exc:
            return JSONResponse({"detail": f"the proposal names no capability {exc}"}, status_code=404)
        except Refused as exc:
            return JSONResponse({"detail": str(exc)}, status_code=exc.status)
        return JSONResponse(done)

    return [Route("/app/capabilities", listing, methods=["GET"]),
            Route("/app/capabilities/proposals/{pid}", decide, methods=["POST"]),
            Route("/app/capabilities/{cid}", put, methods=["PUT"]),
            Route("/app/capabilities/{cid}", delete, methods=["DELETE"])]
