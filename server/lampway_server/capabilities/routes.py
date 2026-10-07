# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Capabilities routes (docs/reports/agent-modes-spec.md E2). Every route needs the bearer; a change also refuses a declared
agent origin and a cross-origin request, so only the user's click in the Client changes what an agent may do."""

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
        row = next(r for r in CAP.ACTIVE.view(body.get("project")) if r["id"] == cid) if cid in {c.id for c in CAP.CATALOGUE} else {
            "id": cid, **CAP.ACTIVE.setting(cid, body.get("project"))}
        return JSONResponse(row)

    return [Route("/app/capabilities", listing, methods=["GET"]), Route("/app/capabilities/{cid}", put, methods=["PUT"])]
