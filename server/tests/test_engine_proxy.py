# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's egress proxy (docs/reports/agent-modes-spec.md E1.5): a loopback forward proxy that lets the engine child reach the
gateway and the hosts its enabled capabilities need, and nothing else, with a log row per refusal. Local sockets only: nothing here
touches the internet (a name outside is mapped to a local echo server by an injected connector)."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from lampway_server import capabilities as CAP
from lampway_server import egress as E
from lampway_server.engine import proxy as P

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Echo:
    """A TCP echo server standing in for the gateway and for 'the internet'; counts the connections it was given."""

    def __init__(self):
        self.connections = 0
        self.seen = []

    async def _handle(self, reader, writer):
        self.connections += 1
        try:
            while data := await reader.read(4096):
                self.seen.append(data)
                writer.write(data)
                await writer.drain()
            if writer.can_write_eof():
                writer.write_eof()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


class Origin(Echo):
    """A plain HTTP server that answers one request and remembers what it was sent."""

    async def _handle(self, reader, writer):
        self.connections += 1
        head = await reader.readuntil(b"\r\n\r\n")
        self.seen.append(head)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        await writer.drain()
        writer.close()


@pytest.fixture
async def world(tmp_path, monkeypatch):
    mgr = E.Egress(tmp_path / "egress-state")
    E.set_active(mgr)
    store = CAP.Store(tmp_path / "cap-state")
    CAP.set_active(store)
    echo = await Echo().start()
    attempts = []

    async def connect(host, port):
        attempts.append((host, port))
        return await asyncio.open_connection("127.0.0.1", echo.port)        # any name 'resolves' to the local echo server

    proxy = P.EngineProxy(connect=connect, gateway_ports={echo.port})
    _, port = await proxy.start()
    yield SimpleNamespace(mgr=mgr, store=store, echo=echo, attempts=attempts, proxy=proxy, port=port)
    await proxy.stop()
    await echo.stop()
    CAP.set_active(None)


async def raw(port, data: bytes, read=True) -> tuple:
    r, w = await asyncio.open_connection("127.0.0.1", port)
    w.write(data)
    await w.drain()
    head = b""
    if read:
        head = await asyncio.wait_for(r.readuntil(b"\r\n\r\n"), 5)
    return r, w, head.decode("latin-1")


async def connect_via(port, target):
    return await raw(port, f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())


async def tunnel_echoes(r, w, payload=b"ping"):
    w.write(payload)
    await w.drain()
    got = await asyncio.wait_for(r.readexactly(len(payload)), 5)
    w.close()
    return got == payload


def refusals(mgr):
    return [x for x in mgr.log() if x["event"] == "refused"]


def browse_on(w):
    w.mgr.set_route("web:any", True)
    w.store.set("web.browse", enabled=True, by="user")


# ------------------------------------------------------------------------------------------------ the gateway's own address
async def test_a_connect_to_the_gateways_loopback_port_tunnels(world):
    r, w, head = await connect_via(world.port, f"127.0.0.1:{world.echo.port}")
    assert head.startswith("HTTP/1.1 200") and await tunnel_echoes(r, w)
    assert world.mgr.log() == [] and world.attempts == []                    # loopback is never gated or logged (egress.py), and not resolved


async def test_another_loopback_port_is_refused_and_logged_and_never_connected(world):
    other = await Echo().start()
    try:
        _, w, head = await connect_via(world.port, f"127.0.0.1:{other.port}")
        w.close()
        assert head.startswith("HTTP/1.1 403") and other.connections == 0
        row = refusals(world.mgr)[-1]
        assert row["provider"] == "127.0.0.1" and "gateway" in row["reason"]
    finally:
        await other.stop()


# ------------------------------------------------------------------------------------------------ everything else is refused
@pytest.mark.parametrize("host", ["pypi.org", "models.dev", "hermes-agent.nousresearch.com", "raw.githubusercontent.com"])
async def test_a_host_the_engine_has_no_right_to_is_refused_and_logged_before_any_connection(world, host):
    """The four hosts the pinned Hermes was measured asking for with the proxy refusing: the turn still completed."""
    _, w, head = await connect_via(world.port, f"{host}:443")
    w.close()
    assert head.startswith("HTTP/1.1 403") and world.attempts == [] and world.echo.connections == 0
    row = refusals(world.mgr)[-1]
    assert row["provider"] == host and row["method"] == "CONNECT" and row["route"] is None and row["reason"] and row["bytes"] == 0
    assert set(row) <= {"t", "event", "route", "provider", "method", "kind", "bytes", "asset_ids", "content_class", "reason",
                        "retention", "training", "privacy_class", "capability", "via"}


async def test_a_route_that_is_on_but_that_no_capability_names_is_still_refused(world):
    world.mgr.set_route("fal", True)
    _, w, head = await connect_via(world.port, "queue.fal.run:443")
    w.close()
    assert head.startswith("HTTP/1.1 403") and world.attempts == []
    assert refusals(world.mgr)[-1]["route"] == "fal" and "no capability" in refusals(world.mgr)[-1]["reason"]


@pytest.fixture
def fetch_capability(monkeypatch):
    """A capability that names a route with hosts, which the first catalogue does not have yet (web:any has none)."""
    cap = CAP.Capability("test.fetch", "Fetch", "Fetch from a service.", "reaches_internet", routes=("heygen",))
    monkeypatch.setattr(CAP, "CATALOGUE", CAP.CATALOGUE + (cap,))
    monkeypatch.setitem(CAP._BY_ID, "test.fetch", cap)


async def test_a_host_of_an_on_route_whose_capability_is_in_force_tunnels_and_each_gate_refuses_when_it_closes(world, fetch_capability):
    world.mgr.set_route("heygen", True)
    world.store.set("test.fetch", enabled=True, by="user")
    r, w, head = await connect_via(world.port, "api.heygen.com:443")
    assert head.startswith("HTTP/1.1 200") and await tunnel_echoes(r, w) and world.attempts == [("api.heygen.com", 443)]
    sends = [x for x in world.mgr.log() if x["event"] == "send"]
    assert sends[-1]["route"] == "heygen" and sends[-1]["provider"] == "api.heygen.com" and sends[-1]["method"] == "CONNECT"

    world.store.set("test.fetch", enabled=False, by="user")                  # the capability off: refused, naming it
    _, w, head = await connect_via(world.port, "api.heygen.com:443")
    w.close()
    assert head.startswith("HTTP/1.1 403") and refusals(world.mgr)[-1]["capability"] == "test.fetch" and len(world.attempts) == 1

    world.store.set("test.fetch", enabled=True, by="user")
    world.mgr.set_route("heygen", False)                                     # the route off: the next CONNECT is refused
    _, w, head = await connect_via(world.port, "api.heygen.com:443")
    w.close()
    assert head.startswith("HTTP/1.1 403") and refusals(world.mgr)[-1]["reason"] == "route off" and len(world.attempts) == 1


# ------------------------------------------------------------------------------------------------ web:any
async def test_web_any_needs_both_its_route_and_web_browse(world):
    for chosen in ("none", "route", "capability"):
        if chosen == "route":
            world.mgr.set_route("web:any", True)
        elif chosen == "capability":
            world.mgr.set_route("web:any", False)
            world.store.set("web.browse", enabled=True, by="user")
        _, w, head = await connect_via(world.port, "news.example:443")
        w.close()
        assert head.startswith("HTTP/1.1 403"), chosen
    assert world.attempts == [] and all(x["event"] == "refused" for x in world.mgr.log())


async def test_web_any_with_web_browse_allows_any_host_and_logs_each_one_then_turning_the_route_off_refuses_the_next(world):
    browse_on(world)
    for host in ("news.example", "docs.example"):
        r, w, head = await connect_via(world.port, f"{host}:443")
        assert head.startswith("HTTP/1.1 200") and await tunnel_echoes(r, w)
    sends = [x for x in world.mgr.log() if x["event"] == "send"]
    assert [(x["route"], x["provider"]) for x in sends] == [("web:any", "news.example"), ("web:any", "docs.example")]
    assert world.attempts == [("news.example", 443), ("docs.example", 443)]
    world.mgr.set_route("web:any", False)
    _, w, head = await connect_via(world.port, "news.example:443")
    w.close()
    assert head.startswith("HTTP/1.1 403") and refusals(world.mgr)[-1]["reason"] == "route off" and len(world.attempts) == 2


async def test_the_wire_indicator_is_lit_while_a_tunnel_is_open_and_dark_after(world):
    browse_on(world)
    r, w, head = await connect_via(world.port, "news.example:443")
    assert world.mgr.indicator()["over_the_wire"] is True
    w.close()
    for _ in range(100):
        if not world.mgr.indicator()["over_the_wire"]:
            break
        await asyncio.sleep(0.02)
    assert world.mgr.indicator()["over_the_wire"] is False


@pytest.mark.parametrize("target", ["127.0.0.1:22", "localhost:8080", "10.0.0.5:80", "192.168.1.1:443", "169.254.169.254:80", "[::1]:80", "[fe80::1]:80"])
async def test_web_any_does_not_reach_this_computers_own_or_private_addresses(world, target):
    browse_on(world)
    _, w, head = await connect_via(world.port, target)
    w.close()
    assert head.startswith("HTTP/1.1 403") and world.attempts == [] and "private" in refusals(world.mgr)[-1]["reason"]


# ------------------------------------------------------------------------------------------------ plain HTTP
async def test_plain_http_to_the_gateway_is_forwarded_in_origin_form_without_proxy_headers(world):
    origin = await Origin().start()
    proxy = P.EngineProxy(gateway_ports={origin.port})
    _, port = await proxy.start()
    try:
        req = (f"GET http://127.0.0.1:{origin.port}/engine/v1/models?x=1 HTTP/1.1\r\nHost: 127.0.0.1:{origin.port}\r\n"
               "Proxy-Connection: keep-alive\r\nProxy-Authorization: Basic abc\r\nAuthorization: Bearer t\r\n\r\n").encode()
        r, w, _ = await raw(port, req, read=False)
        body = await asyncio.wait_for(r.read(), 5)
        w.close()
        assert body.startswith(b"HTTP/1.1 200") and body.endswith(b"hello")
        sent = origin.seen[0].decode("latin-1").lower()
        assert sent.startswith("get /engine/v1/models?x=1 http/1.1") and "proxy-" not in sent and "authorization: bearer t" in sent
        assert "connection: close" in sent
    finally:
        await proxy.stop()
        await origin.stop()


async def test_plain_http_to_a_refused_host_is_403_and_the_log_has_no_query_header_or_path(world):
    req = (b"GET http://tracker.example/a/secret/path?token=QUERYSECRET HTTP/1.1\r\nHost: tracker.example\r\n"
           b"Authorization: Bearer HEADERSECRET\r\n\r\n")
    _, w, head = await raw(world.port, req)
    w.close()
    assert head.startswith("HTTP/1.1 403") and world.attempts == []
    text = world.mgr.export_text()
    assert "tracker.example" in text and not any(s in text for s in ("QUERYSECRET", "HEADERSECRET", "secret/path"))


@pytest.mark.parametrize("data,status", [
    (b"GET /engine/v1/models HTTP/1.1\r\nHost: x\r\n\r\n", "400"),            # origin-form: this is a proxy, not the gateway
    (b"BREW coffee\r\n\r\n", "400"),
    (b"CONNECT nonsense HTTP/1.1\r\n\r\n", "400"),
    (b"CONNECT host:99999 HTTP/1.1\r\n\r\n", "400"),
    (b"GET https://secure.example/ HTTP/1.1\r\n\r\n", "400"),
    (b"GET http://x/ HTTP/1.1\r\n" + b"X: " + b"a" * 70000 + b"\r\n\r\n", "431"),
])
async def test_a_malformed_request_is_answered_and_nothing_is_forwarded(world, data, status):
    _, w, head = await raw(world.port, data)
    w.close()
    assert head.startswith(f"HTTP/1.1 {status}") and world.attempts == [] and world.echo.connections == 0


async def test_a_connector_that_fails_is_502_and_the_wire_indicator_goes_dark(world):
    browse_on(world)

    async def down(host, port):
        raise OSError("unreachable")
    world.proxy.connect = down
    _, w, head = await connect_via(world.port, "news.example:443")
    w.close()
    assert head.startswith("HTTP/1.1 502") and world.mgr.indicator()["over_the_wire"] is False


# ------------------------------------------------------------------------------------------------ lifecycle and the module door
async def test_start_refuses_a_host_that_is_not_loopback_and_stop_closes_the_port_and_open_tunnels(world):
    with pytest.raises(ValueError, match="loopback"):
        await P.EngineProxy().start(host="0.0.0.0")
    r, w, head = await connect_via(world.port, f"127.0.0.1:{world.echo.port}")
    await world.proxy.stop()
    assert await asyncio.wait_for(r.read(10), 5) == b""                       # the open tunnel was closed
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", world.port)
    w.close()


async def test_the_module_start_and_stop_serve_a_default_proxy(tmp_path):
    E.set_active(E.Egress(tmp_path / "e"))
    CAP.set_active(CAP.Store(tmp_path / "c"))
    echo = await Echo().start()
    try:
        server, port = await P.start(gateway_port=echo.port)
        assert port > 0 and server is not None
        r, w, head = await connect_via(port, f"localhost:{echo.port}")
        assert head.startswith("HTTP/1.1 200") and await tunnel_echoes(r, w)
        await P.stop()
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)
    finally:
        await echo.stop()
        CAP.set_active(None)


@pytest.mark.parametrize("name", ["2130706433", "localhost", "127.1"])
async def test_the_default_connector_refuses_a_name_that_resolves_only_to_a_private_address(name):
    """A decimal or short form of 127.0.0.1 is not a literal the decision can see; the connector checks what the name resolves to."""
    with pytest.raises(OSError):
        await P.resolve_global(name, 9)


def test_the_child_env_points_every_library_at_the_proxy_and_exempts_only_the_gateway_host():
    env = P.child_env(4321)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert env[name] == "http://127.0.0.1:4321"
    assert env["NO_PROXY"] == env["no_proxy"] == "127.0.0.1"


def _outbound_openers(root: Path) -> set:
    found = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and node.attr in ("open_connection", "create_connection", "create_unix_connection") or (
                    isinstance(node, ast.Name) and node.id in ("open_connection",)):
                found.add(str(path.relative_to(root)))
    return found


def test_only_the_proxy_opens_outbound_streams_outside_the_httpx_hook_and_the_gate_fires_on_a_plant(tmp_path):
    root = Path(__file__).resolve().parents[1] / "lampway_server"
    assert _outbound_openers(root) == {"engine/proxy.py"}
    (tmp_path / "rogue.py").write_text("import asyncio\nasync def f():\n    return await asyncio.open_connection('x', 1)\n")
    assert _outbound_openers(tmp_path) == {"rogue.py"}
