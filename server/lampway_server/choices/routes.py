# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Choices routes (choices_store.md 4.1). Every route needs the bearer; a write also refuses a declared agent origin and a
cross-origin request. No route returns an identity, a balance, a credential, a source path or a variable's value."""

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..connections.routes import _agent_declared, _body, _cross_origin
from . import registry as REG
from .resolver import Job, NoChoice
from .store import AGENT_WRITE, Refused


def _job(raw) -> Job:
    raw = raw if isinstance(raw, dict) else {}
    return Job(content_class=raw.get("content_class"), needs=dict(raw.get("needs") or {}), project=raw.get("project"), override=raw.get("override"),
               origin="user", avoid=tuple(raw.get("avoid") or ()))


def choices_routes(bearer_ok, on_change=None) -> list:
    from .. import choices as CH

    def guard(request, write=False):
        if not bearer_ok(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        if write and (_agent_declared(request) or _cross_origin(request)):
            return JSONResponse({"detail": AGENT_WRITE}, status_code=403)
        return None

    def handler(fn, write=False):
        async def route(request: Request):
            if (r := guard(request, write)) is not None:
                return r
            body = await _body(request) if request.method in ("PUT", "POST") else {}
            try:
                return JSONResponse(await asyncio.to_thread(fn, request, body))
            except Refused as exc:
                return JSONResponse({"detail": str(exc)}, status_code=exc.status)
            except REG.UnknownPurpose as exc:
                return JSONResponse({"detail": str(exc)}, status_code=404)
            except NoChoice as exc:
                return JSONResponse({"refused": str(exc), "skipped": exc.skipped, "fix": exc.fix, "needs_choice": exc.needs_choice}, status_code=409)
        return route

    def q(request, name):
        return request.query_params.get(name) or None

    def listing(request, body):
        return CH.list_view(Job(project=q(request, "project"), content_class=q(request, "content_class")), q(request, "group"))

    def one(request, body):
        return CH.purpose_view(request.path_params["purpose"], Job(project=q(request, "project"), content_class=q(request, "content_class")))

    def put(request, body):
        pid = request.path_params["purpose"]
        entry = {k: body[k] for k in ("preferred", "fallbacks", "params", "override_policy") if k in body}
        scope = body.get("scope") or "global"
        CH.active_store().set(pid, scope, body.get("project"), entry, by="user")
        if on_change is not None:
            on_change(pid)
        return CH.purpose_view(pid, Job(project=body.get("project")))

    def delete(request, body):
        pid = request.path_params["purpose"]
        CH.active_store().clear(pid, q(request, "project"), by="user")
        if on_change is not None:
            on_change(pid)
        return CH.purpose_view(pid, Job(project=q(request, "project")))

    def dry(request, body):
        from . import views as V
        job = _job(body.get("job"))
        pid = str(body.get("purpose") or "")
        w, d = CH.world(), CH.document(job.project)
        r = CH.resolve(pid, job, world_=w, doc=d)
        return V.resolution_view(r, REG.get(pid), job, w, d)

    def acknowledge(request, body):
        option = str(body.get("option") or "")
        at = CH.active_store().acknowledge(option, bool(body.get("private")), by="user")
        return {"option": option, "acknowledged_at": at}

    def proposals(request, body):
        return {"proposals": CH.active_store().proposals(state=q(request, "state"))}

    def decide(accept):
        def fn(request, body):
            row = CH.active_store().decide(request.path_params["pid"], accept, by="user", scope=body.get("scope") or "global", project=body.get("project"))
            if accept and on_change is not None:
                on_change(row["purpose"])
            return CH.purpose_view(row["purpose"]) if accept else {"declined": row["id"]}
        return fn

    def quality(request, body):
        return {"records": CH.active_store().quality(purpose=q(request, "purpose"), option=q(request, "option"))}

    def quality_import(request, body):
        return {"imported": CH.import_quality(str(body.get("source") or ""), str(body.get("path") or ""), by="user")}

    return [
        Route("/app/choices", handler(listing), methods=["GET"]),
        Route("/app/choices/quality", handler(quality), methods=["GET"]),
        Route("/app/choices/quality/import", handler(quality_import, True), methods=["POST"]),
        Route("/app/choices/resolve", handler(dry), methods=["POST"]),
        Route("/app/choices/acknowledge", handler(acknowledge, True), methods=["POST"]),
        Route("/app/choices/proposals", handler(proposals), methods=["GET"]),
        Route("/app/choices/proposals/{pid}/accept", handler(decide(True), True), methods=["POST"]),
        Route("/app/choices/proposals/{pid}/decline", handler(decide(False), True), methods=["POST"]),
        Route("/app/choices/{purpose}", handler(one), methods=["GET"]),
        Route("/app/choices/{purpose}", handler(put, True), methods=["PUT"]),
        Route("/app/choices/{purpose}", handler(delete, True), methods=["DELETE"]),
    ]
