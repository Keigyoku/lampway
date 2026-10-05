"""The agent WebSocket: JSON-RPC 2.0 text frames at /api/agent/ws/{instance_id}.

One ``AgentSocket`` per connected client instance. It owns the read loop, the
system/notification/job handlers, and the correlation of server->client
requests (blender.execute_script) with the client's replies. Turn traffic
(agent.*) is delegated to the agent hub in agent/turns.py.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from starlette.websockets import WebSocket, WebSocketDisconnect

log = logging.getLogger("lampway.ws")

WS_CLOSE_AUTH_FAILED = 4001
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
NOT_AUTHENTICATED = -32004

SERVER_CAPABILITIES = ["agent_history_v1", "agent_history_v2"]


def bearer_from(websocket: WebSocket) -> Optional[str]:
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


class ConnectionHub:
    """Live sockets by instance id."""

    def __init__(self):
        self.sockets: dict[str, "AgentSocket"] = {}

    def register(self, socket: "AgentSocket"):
        self.sockets[socket.instance_id] = socket

    def unregister(self, socket: "AgentSocket"):
        if self.sockets.get(socket.instance_id) is socket:
            del self.sockets[socket.instance_id]


class AgentSocket:
    def __init__(self, websocket: WebSocket, instance_id: str, auth, hub: ConnectionHub, agent=None):
        self.ws = websocket
        self.instance_id = instance_id
        self.auth = auth
        self.hub = hub
        self.agent = agent
        self.client_capabilities: list[str] = []
        self.handshake_done = False
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._request_seq = 0
        self._tasks: set[asyncio.Task] = set()
        self._handlers = {
            "system.handshake": self._handshake,
            "system.ping": self._ping,
            "system.reauth": self._reauth,
            "system.set_context": self._empty,
            "notifications.sync": self._notifications_sync,
            "notifications.mark_read": self._empty,
            "notifications.get_unread": self._notifications_sync,
            "job.sync": self._job_sync,
            "job.get": self._job_get,
        }

    # ------------------------------------------------------------------ run
    async def run(self):
        token = bearer_from(self.ws)
        if not token or self.auth.verify_access(token) is None:
            await self.ws.accept()
            await self.ws.close(code=WS_CLOSE_AUTH_FAILED)
            return
        await self.ws.accept()
        self.hub.register(self)
        try:
            while True:
                raw = await self.ws.receive_text()
                await self._dispatch(raw)
        except WebSocketDisconnect:
            pass
        finally:
            self.hub.unregister(self)
            for task in list(self._tasks):
                task.cancel()
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("client disconnected"))
            if self.agent is not None:
                self.agent.socket_closed(self)

    async def _dispatch(self, raw: str):
        try:
            frame = json.loads(raw)
        except ValueError:
            await self._send_error(None, PARSE_ERROR, "Parse error")
            return
        if not isinstance(frame, dict):
            return
        if "result" in frame or "error" in frame:
            self._resolve(frame)
            return
        method = frame.get("method")
        request_id = frame.get("id")
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        log.debug("<- %s id=%s", method, request_id)
        if request_id is None:
            return  # a notification; nothing to answer
        if isinstance(method, str) and method.startswith("agent.") and self.agent is not None:
            self.spawn(self._guarded(self.agent.handle(self, method, request_id, params), method, request_id))
            return
        handler = self._handlers.get(method)
        if handler is None:
            await self._send_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
            return
        try:
            result = await handler(params)
        except Exception as exc:  # noqa: BLE001 - the socket must stay up
            log.exception("handler %s failed", method)
            await self._send_error(request_id, INTERNAL_ERROR, str(exc))
            return
        await self.reply(request_id, result)

    async def _guarded(self, coro, method, request_id):
        """A handler that raises still answers: an error reply instead of a
        swallowed task exception and a client waiting forever."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("handler %s failed", method)
            try:
                await self._send_error(request_id, INTERNAL_ERROR, str(exc))
            except Exception:  # noqa: BLE001
                pass

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------- sending
    async def send_frame(self, frame: dict):
        async with self._send_lock:
            await self.ws.send_text(json.dumps(frame))
        log.debug("-> %s id=%s", frame.get("method"), frame.get("id"))

    async def reply(self, request_id, result):
        await self.send_frame({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def send_error(self, request_id, code: int, message: str, data: Any = None):
        await self._send_error(request_id, code, message, data)

    async def _send_error(self, request_id, code: int, message: str, data: Any = None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        await self.send_frame({"jsonrpc": "2.0", "id": request_id, "error": error})

    async def notify(self, method: str, params: dict):
        await self.send_frame({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict, timeout: Optional[float] = None) -> Any:
        """Server -> client request; resolves with the client's result (or raises
        on an error reply, a disconnect, or the timeout)."""
        self._request_seq += 1
        request_id = f"srv_{self._request_seq}"
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self.send_frame({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)

    def _resolve(self, frame: dict):
        future = self._pending.get(frame.get("id"))
        if future is None or future.done():
            return
        if "error" in frame:
            future.set_exception(ClientRpcError(frame["error"]))
        else:
            future.set_result(frame.get("result"))

    # ------------------------------------------------------------ handlers
    async def _handshake(self, params):
        self.client_capabilities = list(params.get("capabilities") or [])
        self.handshake_done = True
        return {"success": True, "agent_ws_v1": True, "server_capabilities": list(SERVER_CAPABILITIES)}

    async def _ping(self, params):
        return {}

    async def _reauth(self, params):
        token = params.get("token")
        return {"authenticated": bool(token) and self.auth.verify_access(token) is not None}

    async def _empty(self, params):
        return {}

    async def _notifications_sync(self, params):
        return {"notifications": []}

    async def _job_sync(self, params):
        return {"jobs": []}

    async def _job_get(self, params):
        return {"job": None}


class ClientRpcError(Exception):
    def __init__(self, error: dict):
        super().__init__(error.get("message", "client error"))
        self.error = error
