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
from . import views as VW
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
        if b.get("action") == "get" and res.get("items"):
            thumbs = await run(vault.thumbs, [i["id"] for i in res["items"]])
            for i in res["items"]:
                i.setdefault("thumb", thumbs.get(i["id"]))
        return JSONResponse(envelope(res))

    async def embed(request):
        b = await body(request)
        if b.get("action") == "plan":
            return JSONResponse(envelope(await run(vault.embed.plan, str(b.get("space") or ""), b.get("asset_ids") or None, True, b.get("model"))))
        if b.get("action") == "run":
            return JSONResponse(envelope(await run(vault.embed.run, str(b.get("plan_id") or ""), "captain")))
        raise LibraryError("action is plan or run")

    async def relate(request):
        b = await body(request)
        return JSONResponse(envelope(await run(CU.relate, vault.lib, str(b.get("src") or ""), str(b.get("type") or ""), str(b.get("dst") or ""), "captain",
                                               str(b.get("role") or ""), b.get("attrs"), bool(b.get("remove")))))

    def _lineage(aid, depth):
        lay = VW.lineage_layout(vault.lib, aid, depth=depth)
        lay["png"] = VW.render_lineage(lay, vault.root / "derived" / f"lineage_{aid}.png")
        return lay

    async def lineage(request):
        return JSONResponse(envelope(await run(_lineage, request.path_params["asset_id"], int(request.query_params.get("depth") or 6))))

    async def views(request):
        return JSONResponse(envelope(await run(VW.view_products, vault.lib, request.path_params["asset_id"])))

    def _diff(a, b):
        recs = [vault.get_record(x) for x in (a, b)]
        if any(r["kind"] not in ("image", "hdri", "map") for r in recs):
            raise LibraryError("diff compares two pictures (image, hdri or map); use the compare view for other kinds")
        paths = [vault.file_path(next(f["sha256"] for f in r["files"] if f["role"] == "main")) for r in recs]
        return VW.image_diff(paths[0], paths[1], vault.root / "derived" / f"diff_{a}_{b}.png")

    async def diff(request):
        b = await body(request)
        return JSONResponse(envelope(await run(_diff, str(b.get("a") or ""), str(b.get("b") or ""))))

    PROXY_FPS = 8.0                              # asset_video's proxy rate (asset_video.md section 5: "the 8 fps 256-px JPEG proxy")

    def _align(a, b, mode):
        frames = []
        for aid in (a, b):
            proxy = VW.view_products(vault.lib, aid)["proxy"]
            if not proxy:
                raise LibraryError(f"{aid}: no proxy frames yet: queued (asset_video)")
            frames.append(proxy)
        try:
            return VW.clip_align(frames[0], frames[1], mode, PROXY_FPS, PROXY_FPS)
        except ValueError as exc:
            raise LibraryError(str(exc)) from None

    async def align(request):
        b = await body(request)
        return JSONResponse(envelope(await run(_align, str(b.get("a") or ""), str(b.get("b") or ""), str(b.get("mode") or "start"))))

    async def board_move(request):
        b = await body(request)
        return JSONResponse(envelope(await run(vault.board_move, request.path_params["board"], request.path_params["asset_id"], float(b.get("x") or 0), float(b.get("y") or 0))))

    p = "/api/v1/library"
    return [Route(f"{p}/status", guarded(status), methods=["GET"]), Route(f"{p}/query", guarded(query), methods=["POST"]),
            Route(f"{p}/assets/{{asset_id}}", guarded(asset), methods=["GET"]), Route(f"{p}/assets/{{asset_id}}/versions/{{n:int}}", guarded(version), methods=["GET"]),
            Route(f"{p}/assets/{{asset_id}}/rate", guarded(rate), methods=["POST"]), Route(f"{p}/files/{{sha256}}", guarded(file), methods=["GET"]),
            Route(f"{p}/sql", guarded(sql), methods=["POST"]), Route(f"{p}/events", guarded(event), methods=["POST"]),
            Route(f"{p}/ingest/scan", guarded(scan), methods=["POST"]), Route(f"{p}/ingest/import", guarded(import_), methods=["POST"]),
            Route(f"{p}/similar", guarded(similar), methods=["POST"]), Route(f"{p}/collect", guarded(collect), methods=["POST"]),
            Route(f"{p}/embed", guarded(embed), methods=["POST"]), Route(f"{p}/relate", guarded(relate), methods=["POST"]),
            Route(f"{p}/assets/{{asset_id}}/lineage", guarded(lineage), methods=["GET"]), Route(f"{p}/assets/{{asset_id}}/views", guarded(views), methods=["GET"]),
            Route(f"{p}/diff", guarded(diff), methods=["POST"]), Route(f"{p}/clip_align", guarded(align), methods=["POST"]),
            Route(f"{p}/boards/{{board}}/items/{{asset_id}}", guarded(board_move), methods=["POST"])]
