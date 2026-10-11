# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""User-installed symbolic MCP connector. Only a pane-owned file supplies authority.

No user Hermes configuration, provider or login file is read or changed here.
Unbound discovery is empty, including during explicit native MCP installation.
"""
import asyncio
import json
import os
import stat
import sys
from pathlib import Path

CONFIG_ENV = "LAMPWAY_HERMES_CONNECTOR_CONFIG"
ROOT_ENV = "LAMPWAY_HERMES_CONNECTOR_ROOT"
SERVER_NAME = "lampway_pane"
# Pinned Hermes tools/mcp_tool_errors.py uses this wire-body budget. The
# desktop's 8 MiB body cap fits with JSON wrapping; native 50 MiB resources
# are a separate scope and are not promised by this desktop relay.
STDIO_FRAME_LIMIT = 10 * 1024 * 1024


def read_config(path, root=None):
    """Fail closed on unbound, stale or unsafe files; never expand HOME paths."""
    if not path or not os.path.isabs(path):
        return None
    root = root or os.environ.get(ROOT_ENV)
    if not root or not os.path.isabs(root):
        return None
    try:
        owned = Path(root).resolve() / "panes"
        target = Path(path)
        parent = target.parent.resolve()
        if parent.parent != owned or target.name != "mcp.json":
            return None
        directory = parent.stat()
        if (directory.st_mode & 0o777 != 0o700
                or hasattr(os, "getuid") and directory.st_uid != os.getuid()):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o777 != 0o600
                    or hasattr(os, "getuid") and info.st_uid != os.getuid()):
                return None
            value = json.load(stream)
        if (not isinstance(value, dict) or value.get("version") != 1
                or not isinstance(value.get("binding"), str) or not value["binding"]):
            return None
        desktop, direct = value.get("desktop"), value.get("direct", [])
        if not isinstance(direct, list):
            return None
        if desktop is not None and (not isinstance(desktop, dict)
                or not isinstance(desktop.get("command"), str) or not os.path.isabs(desktop["command"])
                or not isinstance(desktop.get("args", []), list)
                or not all(isinstance(x, str) for x in desktop.get("args", []))):
            return None
        from urllib.parse import urlsplit
        for entry in direct:
            url = urlsplit(entry.get("url", ""))
            headers = entry.get("headers")
            if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
                    or url.username or url.password or url.query or url.fragment or url.path != "/api/v1/mcp/pane"
                    or not isinstance(headers, dict)
                    or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items())
                    or not headers.get("Authorization", "").startswith("Bearer ")
                    or headers.get("X-Mixar-Session-Id") not in {None, value["binding"]}
                    or value["binding"].startswith("swarm:")
                    and headers.get("X-Mixar-Session-Id") != value["binding"]):
                return None
        if value["binding"].startswith("swarm:") and desktop is not None:
            return None
        return value
    except (OSError, ValueError, TypeError, AttributeError):
        return None


class Connector:
    def __init__(self, path=None, root=None):
        self.path, self.root = path, root
        self.lock = asyncio.Lock()
        self.config = None
        self.process = None
        self.sequence = 0
        self.client = None

    async def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 2)
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 2)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        if self.client is not None:
            client, self.client = self.client, None
            await client.aclose()

    async def refresh(self):
        current = read_config(self.path, self.root)
        if current != self.config:
            await self.close()
            self.config = current
        return current

    async def stdio_request(self, method, params):
        if self.process is None:
            entry = self.config["desktop"]
            # No provider keys, bearer or vendor login environment forwarded.
            env = {key: value for key, value in os.environ.items() if key in {
                "PATH", "SYSTEMROOT", "WINDIR", "XDG_RUNTIME_DIR", "LAMPWAY_MCP_DISCOVERY_DIR",
                "MIXAR_MCP_DISCOVERY_DIR", "LAMPWAY_HOME"}}
            env["LAMPWAY_BOUND_SESSION"] = self.config["binding"]
            self.process = await asyncio.create_subprocess_exec(entry["command"], *entry.get("args", []),
                env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=STDIO_FRAME_LIMIT)
            await self.stdio_request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "lampway-hermes-pane", "version": "1"}})
            self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await self.process.stdin.drain()
        self.sequence += 1
        rid = self.sequence
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
            "params": params or {}}) + "\n").encode())
        await self.process.stdin.drain()
        while True:
            try:
                line = await self.process.stdout.readline() if method == "tools/call" else await asyncio.wait_for(
                    self.process.stdout.readline(), 30)
            except ValueError as exc:
                # asyncio reports an over-limit newline frame as ValueError.
                # Reap this owned transport; never replay a dispatched call.
                await self.close()
                raise RuntimeError("MCP stdio frame exceeds the wire-body limit; no automatic tool retry occurred.") from exc
            except asyncio.CancelledError:
                if self.process and self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                        "params": {"requestId": rid}}) + "\n").encode())
                    await self.process.stdin.drain()
                raise
            if len(line) > STDIO_FRAME_LIMIT:
                await self.close()
                raise RuntimeError("MCP stdio frame exceeds the wire-body limit; no automatic tool retry occurred.")
            if not line:
                raise RuntimeError("Pane desktop connector closed; no automatic tool retry occurred.")
            response = json.loads(line)
            if response.get("id") != rid:
                continue
            if "error" in response:
                raise RuntimeError("Pane desktop connector refused the request.")
            return response.get("result", {})

    async def http_request(self, entry, method, params):
        if self.client is None:
            import httpx
            self.client = httpx.AsyncClient(trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(connect=30, read=None, write=30, pool=30))
        self.sequence += 1
        rid = self.sequence
        try:
            options = {"timeout": 30} if method != "tools/call" else {}
            response = await self.client.post(entry["url"], headers=entry["headers"], json={
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, **options)
        except asyncio.CancelledError:
            await self.client.post(entry["url"], headers=entry["headers"], timeout=5, json={
                "jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": rid}})
            raise
        response.raise_for_status()
        value = response.json()
        if "error" in value:
            raise RuntimeError("Pane direct endpoint refused the request.")
        return value.get("result", {})

    async def inventory(self):
        tools, routes = [], {}
        entries = ([None] if self.config["desktop"] is not None else []) + self.config.get("direct", [])
        for entry in entries:
            result = await (self.stdio_request("tools/list", {}) if entry is None else
                            self.http_request(entry, "tools/list", {}))
            for tool in result.get("tools", []):
                name = tool["name"]
                if name in routes:
                    raise PermissionError("Ambiguous pane tool name; call refused.")
                tools.append(tool)
                routes[name] = entry
        return tools, routes

    async def _request(self, method, params=None):
        if method == "initialize":
            return {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": "1"}}
        if method == "ping":
            return {}
        if method not in {"tools/list", "tools/call"}:
            raise ValueError("Unsupported MCP method.")
        if await self.refresh() is None:
            if method == "tools/list":
                return {"tools": []}
            raise PermissionError("No current owned pane binding; tool call refused.")
        tools, routes = await self.inventory()
        if method == "tools/list":
            return {"tools": tools}
        params = params or {}
        if params.get("name") not in routes:
            raise PermissionError("Tool is not offered by this pane binding.")
        entry = routes[params["name"]]
        return await (self.stdio_request(method, params) if entry is None else self.http_request(entry, method, params))


    async def request(self, method, params=None):
        if method in {"initialize", "ping"}:
            return await self._request(method, params)
        async with self.lock:
            try:
                return await self._request(method, params)
            except asyncio.CancelledError:
                await self.close()
                raise


async def serve():
    connector = Connector(os.environ.get(CONFIG_ENV), os.environ.get(ROOT_ENV))
    pending = {}

    async def handle(request):
        try:
            result = await connector.request(request.get("method"), request.get("params"))
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except asyncio.CancelledError:
            return
        except Exception:
            # No paths, bearer values or downstream exception bodies in responses.
            response = {"jsonrpc": "2.0", "id": request["id"],
                        "error": {"code": -32000, "message": "Pane connector refused or could not complete the request."}}
        print(json.dumps(response), flush=True)

    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    continue
                if request.get("method") == "notifications/cancelled":
                    task = pending.get(request.get("params", {}).get("requestId"))
                    if task is not None and not task.done() and not task.cancelling():
                        task.cancel()
                elif "id" in request:
                    rid = request["id"]
                    if rid in pending and not pending[rid].done():
                        continue
                    task = asyncio.create_task(handle(request))
                    pending[rid] = task
                    task.add_done_callback(lambda done, key=rid: pending.pop(key, None)
                                           if pending.get(key) is done else None)
            except (ValueError, TypeError, AttributeError):
                print(json.dumps({"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Invalid MCP request."}}), flush=True)
    finally:
        tasks = list(pending.values())
        for task in tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await connector.close()


def main():
    asyncio.run(serve())


if __name__ == "__main__":
    main()
