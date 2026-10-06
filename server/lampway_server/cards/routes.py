"""The /app/cards routes (specs/mrmak/09-report-cards.md section 4), behind the local bearer, over the same service as the lampway_cards agent tool."""
from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from ..rest import envelope
from .registry import CardError
from .service import Cards


def routes(bearer_ok, api_port: int = 8787, cards: Cards = None) -> list:
    svc = cards or Cards(api_port=api_port)

    def guarded(fn):
        async def handler(request: Request):
            if not bearer_ok(request):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            try:
                return JSONResponse(envelope(await asyncio.to_thread(fn, request, await _body(request))))
            except CardError as exc:
                return JSONResponse({"detail": str(exc)}, status_code=404 if str(exc).startswith("no card") else 422)
        return handler

    async def _body(request) -> dict:
        if request.method != "POST":
            return {}
        try:
            b = await request.json()
        except ValueError:
            return {}
        return b if isinstance(b, dict) else {}

    q = lambda r, k, d="": r.query_params.get(k) or d  # noqa: E731

    async def frame(request: Request):
        """The page the Workbench window mounts: the card in a sandboxed iframe on the cards' own origin."""
        if not bearer_ok(request):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        try:
            text = await asyncio.to_thread(svc.frame, request.path_params["card_id"], int(q(request, "step", "0")), q(request, "theme", "dark"))
        except CardError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404 if str(exc).startswith("no card") else 422)
        return HTMLResponse(text)
    return [
        Route("/app/cards", guarded(lambda r, b: svc.list(q(r, "query"), q(r, "status"), q(r, "category"))), methods=["GET"]),
        Route("/app/cards/activity", guarded(lambda r, b: svc.activity(q(r, "date"))), methods=["GET"]),
        Route("/app/cards/build", guarded(lambda r, b: svc.build(str(b.get("card") or b.get("piece") or ""), str(b.get("kind") or ""), str(b.get("piece") or ""),
                                                                 b.get("round") or "auto", b.get("title"))), methods=["POST"]),
        Route("/app/cards/{card_id}", guarded(lambda r, b: svc.read(r.path_params["card_id"], int(q(r, "step", "0")))), methods=["GET"]),
        Route("/app/cards/{card_id}", guarded(lambda r, b: svc.update(r.path_params["card_id"], **{k: b[k] for k in ("status", "pinned") if k in b})), methods=["POST"]),
        Route("/app/cards/{card_id}/open", guarded(lambda r, b: svc.open(r.path_params["card_id"], int(q(r, "step", "0")), q(r, "theme", "dark"))), methods=["GET"]),
        Route("/app/cards/{card_id}/frame", frame, methods=["GET"]),
    ]
