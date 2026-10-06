"""The Asset Vault's REST routes (specs/asset_library/asset_query.md section 6.9, under ``/api/v1/library/``), for the Client's Vault editor and Blender-side tools. Every route
needs the local bearer; the bearer is the user, so the user-only verbs (import, rating as the user) are served here and never through the agent tools."""
from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from . import curate as CU
from . import query as Q
from . import similar as SIM
from .store import LibraryError
from ..rest import envelope


def routes(vault, bearer_ok) -> list:
    def guarded(fn):
        async def handler(request: Request):
            if not bearer_ok(request):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            try:
                return await fn(request)
            except LibraryError as exc:
                msg = str(exc)
                return JSONResponse({"detail": msg}, status_code=404 if msg.startswith("no asset") else 422)
        return handler

    async def body(request) -> dict:
        try:
            b = await request.json()
        except ValueError:
            return {}
        return b if isinstance(b, dict) else {}

    def run(fn, *a, **kw):
        return asyncio.to_thread(fn, *a, **kw)

    async def status(request):
        return JSONResponse(envelope(await run(vault.lib.status)))

    async def query(request):
        return JSONResponse(envelope(await run(vault.query, await body(request))))

    async def asset(request):
        v = request.query_params.get("version")
        include = [x for x in (request.query_params.get("include") or "").split(",") if x]
        rec = await run(vault.get_record, request.path_params["asset_id"], int(v) if v else None, include)
        return JSONResponse(envelope(rec))

    async def version(request):
        rec = await run(vault.get_record, request.path_params["asset_id"], int(request.path_params["n"]))
        return JSONResponse(envelope(rec))

    async def file(request):
        path = await run(vault.file_path, request.path_params["sha256"])
        return FileResponse(path)

    async def sql(request):
        b = await body(request)
        return JSONResponse(envelope(await run(Q.readonly_sql, vault.lib, str(b.get("sql") or ""), b.get("params"), int(b.get("limit") or 1000))))

    async def event(request):
        b = await body(request)
        detail = {k: v for k, v in b.items() if k not in ("verb", "asset_id")}
        return JSONResponse(envelope(await run(vault.record_event, str(b.get("verb") or ""), str(b.get("asset_id") or ""), detail, "user")))

    async def scan(request):
        b = await body(request)
        return JSONResponse(envelope(await run(vault.ingest.scan, list(b.get("paths") or []), b.get("label"))))

    async def import_(request):
        b = await body(request)
        return JSONResponse(envelope(await run(vault.ingest.import_, str(b.get("scan_id") or ""), "captain")))

    async def rate(request):
        b = await body(request)
        res = await run(vault.rate, request.path_params["asset_id"], "captain", "user", stars=b.get("stars"), flag=b.get("flag"), verdict=b.get("verdict"), note=b.get("note"))
        return JSONResponse(envelope(res))

    async def similar(request):
        b = await body(request)
        sel = {"asset_ids": list(b.get("asset_ids") or []), "text": b.get("text")}
        kw = {k: b[k] for k in ("axes", "kinds", "k") if b.get(k)}
        return JSONResponse(envelope(await run(SIM.similar, vault.lib, sel, **kw)))

    async def collect(request):
        b = await body(request)
        res = await run(CU.collect, vault.lib, str(b.get("action") or ""), b.get("collection"), b.get("name"), b.get("kind") or "board", b.get("asset_ids") or (), b.get("query"))
        return JSONResponse(envelope(res))

    async def embed(request):
        b = await body(request)
        if b.get("action") == "plan":
            return JSONResponse(envelope(await run(vault.embed.plan, str(b.get("space") or ""), b.get("asset_ids") or None, True, b.get("model"))))
        if b.get("action") == "run":
            return JSONResponse(envelope(await run(vault.embed.run, str(b.get("plan_id") or ""), "captain")))
        raise LibraryError("action is plan or run")

    p = "/api/v1/library"
    return [Route(f"{p}/status", guarded(status), methods=["GET"]), Route(f"{p}/query", guarded(query), methods=["POST"]),
            Route(f"{p}/assets/{{asset_id}}", guarded(asset), methods=["GET"]), Route(f"{p}/assets/{{asset_id}}/versions/{{n:int}}", guarded(version), methods=["GET"]),
            Route(f"{p}/assets/{{asset_id}}/rate", guarded(rate), methods=["POST"]), Route(f"{p}/files/{{sha256}}", guarded(file), methods=["GET"]),
            Route(f"{p}/sql", guarded(sql), methods=["POST"]), Route(f"{p}/events", guarded(event), methods=["POST"]),
            Route(f"{p}/ingest/scan", guarded(scan), methods=["POST"]), Route(f"{p}/ingest/import", guarded(import_), methods=["POST"]),
            Route(f"{p}/similar", guarded(similar), methods=["POST"]), Route(f"{p}/collect", guarded(collect), methods=["POST"]),
            Route(f"{p}/embed", guarded(embed), methods=["POST"])]
