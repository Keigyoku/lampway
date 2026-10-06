# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hyper3D's MCP in Lampway (specs/studios/hyper3d.md, "integrate both REST and MCP"; the captain's C4 change): its seven tools are Studio
actions next to the REST drivers, behind the same spend gate (a paid generation is planned, waits for the user's click, its receipt is
written first, and it leaves through the studio:hyper3d route); and its Connections row signs in, checks liveness (initialize +
tools/list, no tool: the MCP has no balance tool), signs out and signs in again. A fake server stands in for Hyper3D."""

import asyncio
import io
import json
from contextlib import redirect_stdout
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from lampway_server import egress as E
from lampway_server import jobreceipts as JR
from lampway_server import mcp_oauth as MO
from lampway_server.connections import hub as H
from lampway_server.connections import store as CS
from lampway_server.studios import actions as A
from lampway_server.studios import mcp_driver as D
from lampway_server.studios import toon
from lampway_server.studios.service import StudioService

from .fake_mcp_oauth import FakeMcpOAuth

GLB = b"glTF-FAKE-BYTES"


@pytest.fixture
def server():
    s = FakeMcpOAuth()
    real = s.handler

    def handler(request):
        if request.url.host == "files.hyper3d.com":
            s.requests.append((request.method, str(request.url)))
            return httpx.Response(200, content=GLB)
        if request.url.host == "uploads.hyper3d.com":
            s.requests.append((request.method, str(request.url)))
            return httpx.Response(200)
        return real(request)
    s.handler = handler
    return s


@pytest.fixture
def hub(tmp_path, server):
    store = CS.FileStore(tmp_path / "secrets")
    auth = MO.for_store(MO.HYPER3D, lambda: store, tmp_path / "secrets", http=httpx.Client(transport=server.transport()))
    from lampway_server.mcp_client import McpClient
    h = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={}, store=store, which=lambda b: None, home=tmp_path / "home",
              route_on=lambda r: True, oauth={"mcp:hyper3d": auth},
              mcp_clients={"mcp:hyper3d": lambda: McpClient(auth, url=MO.HYPER3D.mcp_url, label="Hyper3D", transport=server.transport())})
    return h


def _sign_in(hub, server):
    url = hub.signin("mcp:hyper3d", by="user")["url"]
    hub.oauth["mcp:hyper3d"].complete_login(server.authorize(url))


def _driver(argv, tmp_path, server, armed=False):
    env = {"LAMPWAY_STATE_DIR": str(tmp_path / "state"), "LAMPWAY_SECRETS_DIR": str(tmp_path / "secrets"), "LAMPWAY_STUDIO_POLL_S": "0"}
    if armed:
        env["LAMPWAY_STUDIO_ARMED"] = "1"
    out = io.StringIO()
    with redirect_stdout(out):
        rc = D.main(argv, env=env, transport=server.transport(), store=CS.FileStore(tmp_path / "secrets"))
    return rc, toon.parse(out.getvalue())


# ------------------------------------------------------------------------------------------------ the Connections row
def test_the_row_signs_in_checks_liveness_with_no_tool_call_signs_out_and_signs_in_again(hub, server):
    assert hub.view(["mcp:hyper3d"])[0]["state"] == "missing"
    url = hub.signin("mcp:hyper3d", by="user")["url"]
    assert parse_qs(urlparse(url).query)["scope"] == ["rodin:generate rodin:read"]
    hub.oauth["mcp:hyper3d"].complete_login(server.authorize(url))
    v = hub.view(["mcp:hyper3d"])[0]
    assert v["state"] == "connected" and v["active_source"]["mode"] == "signin"
    v = hub.test("mcp:hyper3d", by="user")
    assert v["state"] == "connected" and v["check_kind"] == "remote" and v["identity"]["balance"] is None
    assert server.calls == [] and "tools/list" in server.methods, "liveness only: initialize + tools/list, never a tool"
    v = hub.signout("mcp:hyper3d", by="user")
    assert v["state"] == "signed_out"
    _sign_in(hub, server)
    assert hub.view(["mcp:hyper3d"])[0]["state"] == "connected" and len(server.registered) == 1


# ------------------------------------------------------------------------------------------------ the Studio actions
def test_the_seven_tools_are_studio_actions_and_the_paid_ones_need_the_users_click():
    ids = {a.id for a in A.ACTIONS.values() if a.driver == "mcp.hyper3d"}
    assert ids == {"hyper3d.mcp.create_uploads", "hyper3d.mcp.import_images", "hyper3d.mcp.generate", "hyper3d.mcp.generate_bang",
                   "hyper3d.mcp.get_status", "hyper3d.mcp.wait", "hyper3d.mcp.get_result"}
    paid = {a.id for a in A.ACTIONS.values() if a.driver == "mcp.hyper3d" and a.needs_approval}
    assert paid == {"hyper3d.mcp.generate", "hyper3d.mcp.generate_bang"}
    with pytest.raises(A.ActionError, match="ChatGPT"):
        A.ACTIONS["hyper3d.mcp.import_images"].validate({"images": ["x"]}, lambda p: p)


def test_the_plan_calls_no_tool_and_an_unpublished_price_needs_a_ceiling(hub, server, tmp_path):
    _sign_in(hub, server)
    rc, out = _driver(["hyper3d.generate", "--plan", "--args", json.dumps({"prompt": "a bronze helmet"})], tmp_path, server)
    assert rc == 1 and "accept_up_to_credits" in out.error
    rc, out = _driver(["hyper3d.generate", "--plan", "--args", json.dumps({"prompt": "a bronze helmet", "accept_up_to_credits": 2})], tmp_path, server)
    assert rc == 0 and out.kv["dry_run"] == "verified" and out.kv["price_effective_credits"] == 2
    assert server.calls == [], "a plan spends nothing: no tools/call"


def test_an_unarmed_run_is_refused_and_calls_no_tool(hub, server, tmp_path):
    _sign_in(hub, server)
    rc, out = _driver(["hyper3d.generate", "--run", "--out", str(tmp_path / "out"), "--args", json.dumps({"prompt": "x", "accept_up_to_credits": 2})],
                      tmp_path, server)
    assert rc == 1 and "not armed" in out.error and server.calls == []


def test_an_armed_run_uploads_generates_once_waits_and_downloads(hub, server, tmp_path):
    _sign_in(hub, server)
    img = tmp_path / "front.png"
    img.write_bytes(b"\x89PNG-FAKE")
    rc, out = _driver(["hyper3d.generate", "--run", "--out", str(tmp_path / "out"), "--args",
                       json.dumps({"images": [str(img)], "prompt": "helmet", "accept_up_to_credits": 2})], tmp_path, server, armed=True)
    assert rc == 0, out.error
    names = [c[0] for c in server.calls]
    assert names.count("rodin_generate") == 1 and names[0] == "rodin_create_uploads" and "rodin_get_result" in names
    assert out.kv["generation_id"] == "gen-1" and (tmp_path / "out" / "m.glb").read_bytes() == GLB
    assert ("PUT", "https://uploads.hyper3d.com/put/0?sig=x") in server.requests


def test_a_generate_whose_answer_never_came_is_never_resent(hub, server, tmp_path):
    _sign_in(hub, server)
    real = server.handler

    def timeout_on_generate(request):
        if request.url.host == "api.hyper3d.com" and b'"rodin_generate"' in request.content:
            server.calls.append(("rodin_generate", {}))
            raise httpx.ReadTimeout("slow")
        return real(request)
    server.handler = timeout_on_generate
    rc, out = _driver(["hyper3d.generate", "--run", "--out", str(tmp_path / "out"), "--args", json.dumps({"prompt": "x", "accept_up_to_credits": 2})],
                      tmp_path, server, armed=True)
    assert rc == 1 and "HUNG" in out.error and [c[0] for c in server.calls].count("rodin_generate") == 1


def test_the_service_gates_a_paid_generation_writes_the_receipt_first_and_uses_the_studio_route(hub, server, tmp_path):
    _sign_in(hub, server)
    E.set_active(E.Egress(tmp_path / "egress"))
    E.ACTIVE.set_route("studio:hyper3d", True)
    seen_pending = []
    receipts = JR.JobReceipts(tmp_path / "project")

    def execute(argv, env, timeout):
        if "--run" in argv:
            seen_pending.extend(r["state"] for r in receipts.list())
        i = argv.index("-m") + 2
        out = io.StringIO()
        with redirect_stdout(out):
            rc = D.main(argv[i:], env={**env, "LAMPWAY_STUDIO_POLL_S": "0"}, transport=server.transport(), store=CS.FileStore(tmp_path / "secrets"))
        return rc, out.getvalue()
    svc = StudioService(tmp_path / "project", execute, receipts=receipts)

    async def go():
        planned = await svc.plan("hyper3d.mcp.generate", {"prompt": "helmet", "accept_up_to_credits": 2}, by="agent")
        assert planned["state"] == "needs_approval" and server.calls == []
        job = await svc.confirm(planned["approval"]["id"], planned["approval"]["price"], by="captain")
        return await svc.wait(job["id"])
    done = asyncio.run(go())
    assert done["state"] == "done", done
    assert seen_pending == ["submission_pending"], "the receipt is on disk, pending, before the driver runs"
    assert receipts.list()[0]["state"] == "downloaded"
    assert any(r.get("route") == "studio:hyper3d" and r.get("event") == "send" for r in E.ACTIVE.log())


def test_the_app_signs_in_from_connections_and_finishes_on_its_own_loopback_callback(settings, provider, server, tmp_path):
    from starlette.testclient import TestClient
    from lampway_server.app import create_app
    from .fake_client import FakeMixarClient
    app = create_app(settings, provider=provider, connections_transport=server.transport())
    with TestClient(app, base_url="http://127.0.0.1:8787", follow_redirects=False) as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        auth = fake.rest_headers()
        url = http.post("/app/connections/mcp:hyper3d/signin", json={}, headers=auth).json()["url"]
        assert parse_qs(urlparse(url).query)["redirect_uri"] == ["http://127.0.0.1:8787/auth/hyper3d/callback"]
        cb = http.get("/auth/hyper3d/callback", params=server.authorize(url))
        assert cb.status_code == 200 and "Signed in to Hyper3D" in cb.text
        row = http.get("/app/connections/mcp:hyper3d", headers=auth).json()
        assert row["state"] == "connected" and row["active_source"]["mode"] == "signin"
        assert not any("h3d-access" in f.read_text(errors="replace") for f in settings.state_dir.rglob("*") if f.is_file())
