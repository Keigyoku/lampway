# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A JSON-RPC client of one ``hermes serve`` (docs/reports/agent-modes-spec.md A2): ``ws://127.0.0.1:<port>/api/ws?token=<token>``.

The contract, measured on the pinned build (2026-10-07):

* the first frame is the event ``gateway.ready`` (its ``replay_epoch`` changes when serve restarts);
* ``client.capabilities {server_requests: true}`` makes this client one that questions and approvals are sent to;
* requests are ``{"jsonrpc": "2.0", "id": n, "method", "params"}``; answers carry ``result`` or ``error {code, message}``
  (``4001 session not found`` for a closed session);
* events are ``{"method": "event", "params": {type, session_id, payload, seq}}``, fanned out to every attached client;
* server requests are ``{"id": "srq-...", "method": "clarify" | "approval" | ..., "params"}``, answered with
  ``{"id", "result": {...}}``; every client gets them and the first answer wins; the others are sent NO ``request.cancel``.

Loopback only: the connection never goes through a proxy (``proxy=None``), whatever the environment says. The token is never
logged (the URL is not logged at all).
"""

import asyncio
import itertools
import json
import logging
from typing import Awaitable, Callable, Optional

log = logging.getLogger("lampway.engine.serve")

CONNECT_TIMEOUT_S = 10.0
CALL_TIMEOUT_S = 60.0
SESSION_NOT_FOUND = 4001


class ServeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(f"{message} ({code})")
        self.code = code
        self.message = message


class ServeClosed(ConnectionError):
    pass


class ServeClient:
    """One connection. ``on_event(params)`` and ``on_request(frame)`` are awaited in arrival order from one reader task, so a
    question is seen after every event that came before it."""

    def __init__(self, port: int, token: str, *, on_event: Optional[Callable[[dict], Awaitable]] = None,
                 on_request: Optional[Callable[[dict], Awaitable]] = None, host: str = "127.0.0.1"):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("hermes serve is reached on loopback only")
        self.url = f"ws://{host}:{int(port)}/api/ws?token={token}"
        self.on_event = on_event
        self.on_request = on_request
        self.ws = None
        self.ready: dict = {}
        self._ids = itertools.count(1)
        self._pending: dict = {}
        self._reader: Optional[asyncio.Task] = None
        self.closed = asyncio.Event()

    def __repr__(self) -> str:                 # never the URL: it carries the token
        return f"ServeClient(open={self.ws is not None and not self.closed.is_set()})"

    @property
    def epoch(self) -> str:
        return str((self.ready.get("payload") or {}).get("replay_epoch") or "")

    async def connect(self, timeout: float = CONNECT_TIMEOUT_S) -> dict:
        import websockets
        self.ws = await asyncio.wait_for(websockets.connect(self.url, max_size=None, proxy=None, open_timeout=timeout), timeout)
        first = asyncio.get_running_loop().create_future()
        self._reader = asyncio.create_task(self._read(first))
        self.ready = await asyncio.wait_for(first, timeout)
        await self.call("client.capabilities", {"server_requests": True})
        return self.ready

    async def _read(self, first: asyncio.Future) -> None:
        try:
            async for raw in self.ws:
                for line in str(raw).splitlines():
                    if not line.strip():
                        continue
                    try:
                        frame = json.loads(line)
                    except ValueError:
                        continue
                    await self._dispatch(frame, first)
        except Exception:  # noqa: BLE001 - a dropped connection ends the reader; the owner reconnects
            log.debug("hermes serve connection ended", exc_info=True)
        finally:
            self.closed.set()
            if not first.done():
                first.set_exception(ServeClosed("hermes serve closed the connection before gateway.ready"))
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ServeClosed("hermes serve closed the connection"))
            self._pending.clear()

    async def _dispatch(self, frame: dict, first: asyncio.Future) -> None:
        method = frame.get("method")
        if method is None:
            fut = self._pending.pop(frame.get("id"), None)
            if fut is not None and not fut.done():
                fut.set_result(frame)
            return
        if method == "event":
            params = frame.get("params") or {}
            if params.get("type") == "gateway.ready" and not first.done():
                first.set_result(params)
                return
            if self.on_event is not None:
                try:
                    await self.on_event(params)
                except Exception:  # noqa: BLE001 - one bad event never ends the connection
                    log.warning("an event from hermes serve could not be handled", exc_info=True)
            return
        if "id" in frame and self.on_request is not None:
            try:
                await self.on_request(frame)
            except Exception:  # noqa: BLE001
                log.warning("a request from hermes serve could not be handled", exc_info=True)

    async def call(self, method: str, params: Optional[dict] = None, timeout: float = CALL_TIMEOUT_S) -> dict:
        if self.ws is None or self.closed.is_set():
            raise ServeClosed("not connected to hermes serve")
        rid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        try:
            await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}))
            frame = await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)
        if "error" in frame:
            err = frame.get("error") or {}
            raise ServeError(err.get("code"), str(err.get("message") or "error"))
        return frame.get("result") or {}

    async def respond(self, request_id, result: dict) -> None:
        if self.ws is None or self.closed.is_set():
            raise ServeClosed("not connected to hermes serve")
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}))

    async def close(self) -> None:
        ws, self.ws = self.ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._reader is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._reader), 5)
            except Exception:  # noqa: BLE001
                self._reader.cancel()
        self.closed.set()
