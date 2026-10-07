"""egress_consent (specs/cloud/egress_consent.md): every outbound route is OFF until the user opts in, one choke point at the transport, a visible 'over the wire' indicator, a content-free local log, and the
private-content rule. Fake transports only: nothing here touches the network."""
import asyncio
import json
import re
import threading
from pathlib import Path

import httpx
import pytest

from lampway_server import egress as E

HOST = "https://openrouter.ai/api/v1/chat"


@pytest.fixture
def mgr(tmp_path):
    m = E.Egress(tmp_path / "state")
    E.install()
    E.set_active(m)
    return m


def client(handler=None, seen=None):
    def h(request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json={"ok": True}) if handler is None else handler(request)
    return httpx.Client(transport=httpx.MockTransport(h))


def test_a_route_that_is_not_opted_in_refuses_and_nothing_is_sent(mgr):
    seen = []
    with pytest.raises(E.EgressRefused, match="openrouter is off: switch it on in Privacy"):
        client(seen=seen).post(HOST, json={"prompt": "hi"})
    assert seen == []
    rows = mgr.log()
    assert rows[-1]["event"] == "refused" and rows[-1]["route"] == "openrouter"
    assert E.Egress(mgr.state_dir).enabled("openrouter") is False                          # a fresh install: everything off


def test_opting_in_lets_it_through_persists_and_is_logged(mgr):
    mgr.set_route("openrouter", True)
    assert client().post(HOST, json={"prompt": "hi"}).status_code == 200
    assert E.Egress(mgr.state_dir).enabled("openrouter") is True
    row = mgr.log()[-1]
    assert row["event"] == "send" and row["route"] == "openrouter" and row["provider"] == "openrouter.ai" and row["bytes"] > 0 and row["retention"]


def test_the_indicator_is_lit_during_the_call_and_dark_after_even_on_error_and_with_two_calls(mgr):
    mgr.set_route("openrouter", True)
    states = []
    def h(request):
        states.append(mgr.indicator())
        if request.url.path.endswith("boom"):
            raise httpx.ConnectError("down")
        return httpx.Response(200)
    c = client(h)
    c.get(HOST)
    assert states[0]["over_the_wire"] is True and states[0]["active"] == ["openrouter"] and mgr.indicator()["over_the_wire"] is False and mgr.indicator()["last"]["route"] == "openrouter"
    with pytest.raises(httpx.ConnectError):
        c.get("https://openrouter.ai/boom")
    assert mgr.indicator()["over_the_wire"] is False
    gate, inside = threading.Event(), threading.Event()
    def slow(request):
        inside.set(); gate.wait(5); return httpx.Response(200)
    t = threading.Thread(target=lambda: client(slow).get(HOST)); t.start(); inside.wait(5)
    client().get(HOST)                                                                       # a second call finishes while the first is in flight
    assert mgr.indicator()["over_the_wire"] is True                                          # the counter keeps it lit
    gate.set(); t.join()
    assert mgr.indicator()["over_the_wire"] is False


def test_the_indicator_is_lit_for_an_async_call_too(mgr):
    mgr.set_route("openrouter", True)
    seen = []
    async def go():
        async def h(request):
            seen.append(mgr.indicator()["over_the_wire"]); return httpx.Response(200)
        async with httpx.AsyncClient(transport=httpx.MockTransport(h)) as c:
            await c.get(HOST)
    asyncio.run(go())
    assert seen == [True] and mgr.indicator()["over_the_wire"] is False


def test_the_log_row_has_what_kind_bytes_and_asset_ids_but_no_content_no_query_no_header(mgr):
    mgr.set_route("fal", True)
    with E.context(kind="image", asset_ids=["a1b2"], content_class="public"):
        client().post("https://queue.fal.run/fal-ai/x?token=QUERYSECRET", content=b"BODYSECRET" * 100, headers={"authorization": "Key HEADERSECRET"})
    text = (mgr.state_dir / "egress" / "log.jsonl").read_text()
    for s in ("QUERYSECRET", "BODYSECRET", "HEADERSECRET"):
        assert s not in text
    row = json.loads(text.splitlines()[-1])
    assert row["kind"] == "image" and row["asset_ids"] == ["a1b2"] and row["bytes"] == 1000 and row["route"] == "fal" and row["content_class"] == "public"
    assert oct((mgr.state_dir / "egress" / "log.jsonl").stat().st_mode & 0o777) == "0o600"


def test_a_private_asset_is_refused_on_a_retaining_or_unknown_route_even_when_opted_in(mgr):
    for route, url in (("fal", "https://queue.fal.run/x"), ("studio:meshy", "https://api.meshy.ai/x")):
        mgr.set_route(route, True)
        seen = []
        with E.context(kind="image", asset_ids=["p1"], content_class="private"):
            with pytest.raises(E.EgressRefused, match="this asset is private"):
                client(seen=seen).post(url, content=b"x")
        assert seen == []


def test_a_private_asset_goes_to_openrouter_only_with_zdr_and_data_collection_deny(mgr):
    mgr.set_route("openrouter", True)
    with E.context(kind="image", asset_ids=["p1"], content_class="private"):
        with pytest.raises(E.EgressRefused, match="zdr"):
            client().post(HOST, content=b"x")
    with E.context(kind="image", asset_ids=["p1"], content_class="private", constraints={"zdr": True, "data_collection": "deny"}):
        assert client().post(HOST, content=b"x").status_code == 200
    with E.context(kind="image", asset_ids=["p1"], content_class="private", constraints={"zdr": True, "data_collection": "allow"}):
        with pytest.raises(E.EgressRefused):
            client().post(HOST, content=b"x")


def test_the_per_asset_override_is_loud_logged_and_scoped_to_that_asset_and_route(mgr):
    mgr.set_route("fal", True)
    mgr.override("p1", "fal")
    assert [r for r in mgr.log() if r["event"] == "override"][-1]["asset_id"] == "p1"
    with E.context(kind="image", asset_ids=["p1"], content_class="private"):
        assert client().post("https://queue.fal.run/x", content=b"x").status_code == 200
    assert mgr.log()[-1]["override"] is True
    with E.context(kind="image", asset_ids=["p2"], content_class="private"):
        with pytest.raises(E.EgressRefused):
            client().post("https://queue.fal.run/x", content=b"x")
    mgr.clear_override("p1", "fal")
    with E.context(kind="image", asset_ids=["p1"], content_class="private"):
        with pytest.raises(E.EgressRefused):
            client().post("https://queue.fal.run/x", content=b"x")


def test_an_unmapped_host_is_refused_and_loopback_is_never_gated_or_logged(mgr):
    with pytest.raises(E.EgressRefused, match="host evil.example is not a known route"):
        client().post("https://evil.example/x", content=b"x")
    n = len(mgr.log())
    assert client().get("http://127.0.0.1:8787/x").status_code == 200 and client().get("http://localhost/x").status_code == 200
    assert len(mgr.log()) == n


def test_an_explicit_route_context_covers_a_cdn_host_no_table_lists(mgr):
    mgr.set_route("higgsfield", True)
    with E.context(route="higgsfield", kind="file"):
        assert client().get("https://some-cdn.example/out.mp4").status_code == 200
    assert mgr.log()[-1]["route"] == "higgsfield"


@pytest.mark.parametrize("route", sorted(E.ROUTES))
def test_audit_every_route_host_is_gated_off_refuses_on_sends_one_row(mgr, route):
    r = E.ROUTES[route]
    host = r.hosts[0] if r.hosts else "llm.example"
    url = f"https://{host.lstrip('.')}/x"
    if not r.hosts:                                            # a route whose hosts are configured, not fixed (the custom LLM endpoint, the MCP probe's servers)
        mgr.register_host(route, "llm.example")
    with pytest.raises(E.EgressRefused):
        client().get(url)
    mgr.set_route(route, True)
    n = len([x for x in mgr.log() if x["event"] == "send"])
    client().get(url)
    assert len([x for x in mgr.log() if x["event"] == "send"]) == n + 1 and r.retention and r.training


def test_every_policy_is_a_text_or_unknown_never_blank(mgr):
    for r in E.ROUTES.values():
        assert r.retention.strip() and r.training.strip() and r.privacy_class in ("ok", "conditional", "retains", "unknown")


def test_guard_gates_a_subprocess_side_route_the_same_way(mgr):
    with pytest.raises(E.EgressRefused, match="studio:tripo is off"):
        with E.guard("studio:tripo", kind="request"):
            raise AssertionError("must not run")
    mgr.set_route("studio:tripo", True)
    with E.guard("studio:tripo", kind="request", asset_ids=["m1"]):
        assert mgr.indicator()["over_the_wire"] is True
    assert mgr.indicator()["over_the_wire"] is False and mgr.log()[-1]["route"] == "studio:tripo"


def test_no_server_module_opens_a_network_door_around_the_hook():
    """Every in-process network use is httpx (hooked). Anything else (urllib, sockets, websockets, requests, aiohttp) may exist only in the studio driver scripts, which run as a subprocess behind guard()."""
    root = Path(__file__).resolve().parents[1] / "lampway_server"
    door = re.compile(r"^\s*(import|from)\s+(urllib\.request|urllib3|requests|aiohttp|websockets|websocket|socket)\b|\bsocket\.create_connection\b|\burlopen\(", re.M)
    allowed = {"studios/tripo/relief_gen.py", "studios/tripo/tripo_image.py", "studios/tripo/tripo_mesh.py", "studios/tripo/tripo_texture.py"}
    found = {str(p.relative_to(root)) for p in root.rglob("*.py") if door.search(p.read_text())}
    assert found - allowed - {"egress.py"} - set(LOOPBACK_ONLY) == set(), \
        f"modules with a network door the egress hook cannot see: {sorted(found - allowed - set(LOOPBACK_ONLY))}"
    assert set(LOOPBACK_ONLY) <= found, "a loopback-only entry that opens no door any more must be removed"


#: Spec A1/A2: modules whose door is to Lampway's OWN Mode 1 pane on this computer, never off it. Each is held by its own check below.
LOOPBACK_ONLY = {
    "engine/serve_client.py": "the island's JSON-RPC client of a pane's `hermes serve`: ws://127.0.0.1 only, never through a proxy",
    "engine/units.py": "picks a free port for a pane's serve by binding 127.0.0.1:0, and waits for that serve on loopback",
}


def test_the_loopback_only_doors_reach_loopback_only():
    import asyncio
    from lampway_server.engine import serve_client as SC
    with pytest.raises(ValueError, match="loopback"):
        SC.ServeClient(80, "t", host="example.com")
    assert SC.ServeClient(80, "t").url.startswith("ws://127.0.0.1:80/")
    src = Path(SC.__file__).read_text()
    assert "proxy=None" in src and src.count("websockets.connect(") == 1, "one connect, never through a proxy"
    units = (Path(SC.__file__).parent / "units.py").read_text()
    assert re.findall(r"s\.bind\(\((.*?)\)\)", units) == ['"127.0.0.1", 0'] and "connect(" not in units.replace("connect_when_up", "").replace(".connect()", "")
    assert asyncio.iscoroutinefunction(SC.ServeClient.connect)


# ------------------------------------------------------------------------------------------------ routes
from starlette.testclient import TestClient  # noqa: E402

from lampway_server.app import create_app  # noqa: E402


def test_the_routes_need_the_bearer_switch_persist_override_log_and_export(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    m = E.Egress(tmp_path / "egstate")
    app = create_app(settings, provider=provider, egress=m)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        assert http.get("/app/egress").status_code == 401 and http.post("/app/egress/route", json={}).status_code == 401
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        h = fake.rest_headers()
        st = http.get("/app/egress", headers=h).json()
        assert {r["id"] for r in st["routes"]} == set(E.ROUTES) and all(r["enabled"] is False for r in st["routes"]) and st["indicator"]["over_the_wire"] is False
        assert all(r["retention"] and r["training"] for r in st["routes"])
        assert http.post("/app/egress/route", headers=h, json={"route": "fal", "enabled": True}).json()["enabled"] is True
        assert http.post("/app/egress/route", headers=h, json={"route": "nope", "enabled": True}).status_code == 422
        assert E.Egress(m.state_dir).enabled("fal") is True
        assert http.post("/app/egress/override", headers=h, json={"asset_id": "a1", "route": "fal"}).status_code == 200
        log = http.get("/app/egress/log?limit=5", headers=h).json()["rows"]
        assert any(r["event"] == "override" for r in log)
        exp = http.get("/app/egress/export", headers=h)
        assert exp.status_code == 200 and all(json.loads(l) for l in exp.text.splitlines())


def test_preflight_refuses_without_a_row_for_a_send_and_the_studio_receipt_is_cancelled_not_unknown(mgr):
    with pytest.raises(E.EgressRefused, match="studio:meshy is off"):
        E.preflight("studio:meshy")
    assert mgr.log()[-1]["event"] == "refused" and not [r for r in mgr.log() if r["event"] == "send"]
