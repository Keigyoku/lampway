# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's egress proxy (docs/reports/agent-modes-spec.md E1.5): a loopback HTTP forward proxy (``CONNECT`` tunnelling for HTTPS,
absolute-URI forwarding for plain HTTP) that the engine child is pointed at through ``HTTPS_PROXY`` / ``HTTP_PROXY`` / ``ALL_PROXY``
(``child_env``). Everything the child sends to the network passes the one decision below, in Lampway's process, or does not leave.

What it allows, and nothing else:

1. the gateway's own loopback port (``gateway_ports``): never logged, as every loopback call is exempt in ``egress.py``;
2. a host whose egress route is ON and which a capability names (``capabilities.CATALOGUE`` ``routes``) that is in force;
3. any other host while the ``web:any`` route is on AND ``web.browse`` is in force; each host it reaches is a log row of its own.

A route that is on but that no capability names is NOT reachable by the engine (the spec's wording: "the hosts of the routes the enabled
capabilities need"). Literal private, loopback and link-local addresses are never reachable under ``web:any`` (the engine's browser
must not be a way to this computer's own services or a cloud metadata address); a name that resolves to one is refused by the default
connector, which connects to the address it checked. Every refusal is one ``egress`` log row written BEFORE any connection is attempted
(host, route, method, reason: no path, query, header or content) and is answered ``403``; an allowed connection goes through
``Egress.begin`` (the row is written before the bytes leave, the "over the wire" indicator is lit until the tunnel closes).

This module is the one place in the server that opens an outbound stream outside the httpx hook; it does so only after ``decide``
(``tests/test_engine_proxy.py`` holds that no other module does).

[UNVERIFIED] that the pinned Hermes honours ``HTTPS_PROXY`` for every library it uses (the coordinator measured ``requests`` and its
CONNECTs to pypi.org and models.dev being refused with the turn still completing; a browser tool's Chromium and any Node helper are
untested). The proxy is an open relay for any local process that finds its port, under the same policy: it has no credential of its own.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

from .. import capabilities as CAP
from .. import egress as EG

log = logging.getLogger("lampway.engine.proxy")

WEB_ANY = "web:any"
BROWSE = "web.browse"
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
HEAD_LIMIT = 65536
HEAD_TIMEOUT = 15.0
CONNECT_TIMEOUT = 15.0
HOP_BY_HOP = {"proxy-connection", "proxy-authorization", "proxy-authenticate", "connection", "keep-alive"}
PRIVATE_REASON = "private address: only the gateway's port on this computer is reachable"


class PrivateAddress(OSError):
    pass


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str = ""
    route: Optional[str] = None
    capability: Optional[str] = None
    local: bool = False                 # the gateway's own address: no log row, no indicator


def _addr(host: str):
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_loopback_host(host: str) -> bool:
    ip = _addr(host)
    return host in LOOPBACK_NAMES or host.endswith(".localhost") or (ip is not None and ip.is_loopback)


def _not_global(host: str) -> bool:
    ip = _addr(host)
    return _is_loopback_host(host) or (ip is not None and not ip.is_global)


def capabilities_for_route(route: str) -> list:
    """The capability ids that name ``route``: ``web.browse`` for ``web:any``; a family row's wildcard route (``msg:*``) names its member's
    (``msg:telegram`` -> ``messaging.telegram``)."""
    out = []
    for cap in CAP.CATALOGUE:
        for pattern in cap.routes:
            if pattern == route:
                out.append(cap.id)
            elif "*" in pattern and fnmatchcase(route, pattern) and cap.id.endswith("*"):
                out.append(cap.id[:-1] + route[len(pattern.split("*")[0]):])
    return out


async def resolve_global(host: str, port: int):
    """Connect to ``host`` only at a globally routable address, the one that was checked (no second lookup to rebind)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port)
    for info in infos:
        ip = info[4][0]
        if not _not_global(ip):
            return await asyncio.open_connection(ip, port)
    raise PrivateAddress(f"{host} resolves only to private addresses")


class EngineProxy:
    def __init__(self, *, connect: Optional[Callable[[str, int], Awaitable[tuple]]] = None, gateway_ports=(), egress=None, capabilities=None):
        self.connect = connect                                   # injected by tests; the default resolves, checks and connects
        self.gateway_ports = {int(p) for p in gateway_ports}
        self._egress = egress
        self._capabilities = capabilities
        self._server = None
        self._tasks: set = set()
        self._writers: set = set()

    @property
    def egress(self):
        return self._egress if self._egress is not None else EG.ACTIVE

    @property
    def capabilities(self):
        return self._capabilities if self._capabilities is not None else CAP.ACTIVE

    # ------------------------------------------------------------------------------------------------ the decision
    def _in_force(self, cid: str, eg) -> tuple:
        store = self.capabilities
        if store is None:
            return False, f"{cid} is off"
        return store.effective(cid, CAP.project(), routes_on=eg.enabled)

    def decide(self, host: str, port: int) -> Decision:
        host = host.lower().strip("[]").rstrip(".")
        if _is_loopback_host(host):
            if port in self.gateway_ports:
                return Decision(True, local=True)
            return Decision(False, PRIVATE_REASON)
        if _not_global(host):
            return Decision(False, PRIVATE_REASON)
        eg = self.egress
        if eg is None:
            return Decision(False, "egress is not available: nothing leaves")
        specific = None
        route = eg.route_for_host(host)
        if route and route != WEB_ANY:
            caps = capabilities_for_route(route)
            if not caps:
                specific = Decision(False, "no capability names this route: the engine may not use it", route)
            elif not eg.enabled(route):
                specific = Decision(False, "route off", route)
            else:
                states = [(cid, self._in_force(cid, eg)) for cid in caps]
                live = next((cid for cid, (on, _) in states if on), None)
                if live:
                    return Decision(True, route=route, capability=live)
                specific = Decision(False, states[0][1][1] or f"{states[0][0]} is off", route, states[0][0])
        browse_chosen = self.capabilities is not None and bool(self.capabilities.setting(BROWSE, CAP.project())["enabled"])
        if eg.enabled(WEB_ANY) and self._in_force(BROWSE, eg)[0]:
            return Decision(True, route=WEB_ANY, capability=BROWSE)
        if specific is not None:
            return specific
        if browse_chosen:
            if not eg.enabled(WEB_ANY):
                return Decision(False, "route off", WEB_ANY, BROWSE)
        return Decision(False, "no capability lets the engine reach this host")

    # ------------------------------------------------------------------------------------------------ serving
    async def start(self, host: str = "127.0.0.1", port: int = 0) -> tuple:
        if not _is_loopback_host(host.lower().strip("[]")):
            raise ValueError("the engine proxy binds loopback only: it has no credential of its own")
        self._server = await asyncio.start_server(self._handle, host, port, limit=HEAD_LIMIT)
        return self._server, self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        for w in list(self._writers):
            w.close()
        tasks = list(self._tasks)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), 5)
            except asyncio.TimeoutError:
                pass

    async def _handle(self, reader, writer) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        self._writers.add(writer)
        try:
            await self._serve(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:  # noqa: BLE001 - one bad connection never stops the proxy
            log.debug("engine proxy: a connection failed", exc_info=True)
        finally:
            self._tasks.discard(task)
            self._writers.discard(writer)
            writer.close()

    @staticmethod
    async def _reply(writer, status: int, reason: str, body: str = "") -> None:
        data = body.encode("utf-8")
        writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {len(data)}\r\n"
                     "Connection: close\r\n\r\n".encode("latin-1") + data)
        try:
            await writer.drain()
        except ConnectionError:
            pass

    @staticmethod
    def _split_target(target: str) -> tuple:
        host, _, port = target.rpartition(":")
        host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        if not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(target)
        return host, int(port)

    async def _serve(self, reader, writer) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT)
        except asyncio.LimitOverrunError:
            return await self._reply(writer, 431, "Request Header Fields Too Large", "request head too large")
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
            return await self._reply(writer, 400, "Bad Request", "this is an HTTP proxy")
        method, target, version = parts[0].upper(), parts[1], parts[2]
        try:
            if method == "CONNECT":
                host, port = self._split_target(target)
                rewritten = None
            else:
                url = urlsplit(target)
                if url.scheme.lower() != "http" or not url.hostname:
                    return await self._reply(writer, 400, "Bad Request", "this is an HTTP proxy: send an absolute http:// URI or CONNECT")
                host, port = url.hostname, url.port or 80
                headers = [ln for ln in lines[1:] if ln and ln.split(":", 1)[0].strip().lower() not in HOP_BY_HOP]
                path = (url.path or "/") + (f"?{url.query}" if url.query else "")
                rewritten = (f"{method} {path} {version}\r\n" + "".join(h + "\r\n" for h in headers) + "Connection: close\r\n\r\n").encode("latin-1")
        except ValueError:
            return await self._reply(writer, 400, "Bad Request", "malformed target")
        verdict = self.decide(host, port)
        route = None
        if not verdict.allow:                                    # written BEFORE any connection is attempted
            if self.egress is not None:
                extra = {"capability": verdict.capability} if verdict.capability else {}
                self.egress.note_refused(host, method, verdict.reason, verdict.route, via="engine_proxy", **extra)
            return await self._reply(writer, 403, "Forbidden", f"Lampway refused this connection: {verdict.reason}")
        if not verdict.local:
            try:
                route = self.egress.begin(host, method, 0, explicit_route=verdict.route)    # the send row, before the bytes; may refuse on a race
            except EG.EgressRefused as exc:
                return await self._reply(writer, 403, "Forbidden", f"Lampway refused this connection: {exc}")
        try:
            try:
                connect = asyncio.open_connection if verdict.local else (self.connect or resolve_global)
                up_r, up_w = await asyncio.wait_for(connect(host, port), CONNECT_TIMEOUT)
            except (OSError, asyncio.TimeoutError) as exc:
                return await self._reply(writer, 502, "Bad Gateway", f"could not connect: {type(exc).__name__}")
            self._writers.add(up_w)
            try:
                if rewritten is None:
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                else:
                    up_w.write(rewritten)
                await writer.drain()
                await asyncio.gather(self._pipe(reader, up_w), self._pipe(up_r, writer))
            finally:
                self._writers.discard(up_w)
                up_w.close()
        finally:
            if route is not None:
                self.egress.end(route)

    @staticmethod
    async def _pipe(src, dst) -> None:
        """Copy until EOF, then half-close ``dst``; an error closes it outright."""
        try:
            while data := await src.read(65536):
                dst.write(data)
                await dst.drain()
            if dst.can_write_eof():
                dst.write_eof()
        except (ConnectionError, OSError):
            dst.close()


_DEFAULT: Optional[EngineProxy] = None


async def start(host: str = "127.0.0.1", port: int = 0, *, gateway_port: Optional[int] = None, gateway_ports=()) -> tuple:
    """Start the process-wide proxy on loopback; ``(server, port)``. ``gateway_port`` is the Lampway server's own port (the gateway is
    mounted on it). A proxy already running is stopped first."""
    global _DEFAULT
    await stop()
    ports = set(gateway_ports) | ({gateway_port} if gateway_port else set())
    proxy = EngineProxy(gateway_ports=ports)
    result = await proxy.start(host, port)
    _DEFAULT = proxy
    return result


async def stop() -> None:
    global _DEFAULT
    proxy, _DEFAULT = _DEFAULT, None
    if proxy is not None:
        await proxy.stop()


PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def proxy_vars(proxy_url: Optional[str], gateway_host: str = "127.0.0.1") -> dict:
    """The engine child's proxy variables, the ONE source of truth (a Mode 1 pane's ``pane.json`` carries it, spec A1): every library that honours one is
    pointed at the proxy, and ``NO_PROXY`` names only the gateway's loopback host, so the gateway and the session's MCP endpoint (both
    on Lampway's own server) are reached directly (measured with the pinned Hermes: with NO_PROXY=127.0.0.1,localhost it reached the
    model directly). Without a proxy URL only ``NO_PROXY`` is set."""
    if not _is_loopback_host(str(gateway_host).lower().strip("[]")):
        raise ValueError("NO_PROXY names the gateway's loopback host only")
    env = {}
    if proxy_url:
        for name in PROXY_VARS[:3]:
            env[name] = env[name.lower()] = str(proxy_url)
    env["NO_PROXY"] = env["no_proxy"] = str(gateway_host)
    return env


def child_env(proxy_port: int, gateway_host: str = "127.0.0.1", proxy_host: str = "127.0.0.1") -> dict:
    """``proxy_vars`` for a proxy on ``proxy_host:proxy_port``."""
    return proxy_vars(f"http://{proxy_host}:{int(proxy_port)}", gateway_host)
