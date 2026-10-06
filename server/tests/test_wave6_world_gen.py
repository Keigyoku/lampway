"""splat_world, the generate half (specs/mixar_docs/splat_world.md): a world-model job (text or image to a Gaussian-splat environment) planned and validated with
nothing sent, a needs_key answer when no backend is configured, and, on a fake transport, the confirmed run that writes the SPZ, the GLB collider and the
panorama into the project. Every byte leaves through the egress choke point (route world_labs, off until opted in). The Client's World Labs tab stays hidden
while the service is unbacked (tests/test_job_queue.py pins the 422). The provider's request shapes are [UNVERIFIED]: the live leg is needs_key."""

import base64
import json

import httpx
import pytest

from lampway_server import egress as EG
from lampway_server import world_gen as WG

FILES = {"spz": b"SPZ-BYTES", "glb": b"glTF-collider", "pano": b"\xff\xd8pano"}


def fake_transport(calls):
    polls = {"n": 0}

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path))
        if req.method == "POST" and req.url.path.endswith("/worlds"):
            return httpx.Response(200, json={"id": "w1", "status": "pending"})
        if req.url.path.endswith("/worlds/w1"):
            polls["n"] += 1
            if polls["n"] < 2:
                return httpx.Response(200, json={"id": "w1", "status": "running"})
            return httpx.Response(200, json={"id": "w1", "status": "completed",
                                             "files": {k: f"https://cdn.worldlabs.ai/w1/{k}" for k in FILES}})
        for k, data in FILES.items():
            if req.url.path.endswith(f"/w1/{k}"):
                return httpx.Response(200, content=data)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_plan_validates_and_sends_nothing(tmp_path):
    calls = []
    c = WG.WorldClient(key="k-test", transport=fake_transport(calls), poll_s=0)
    out = c.plan(str(tmp_path), {"mode": "text", "prompt": "a ruined greek temple on a hill", "lod": "medium"})
    assert out["state"] == "needs_approval" and out["service"] == "world_labs" and calls == []
    assert out["price"] is None and "read back" in out["price_note"]
    with pytest.raises(WG.WorldError, match="mode image needs an image"):
        c.plan(str(tmp_path), {"mode": "image", "prompt": "x", "lod": "low"})
    with pytest.raises(WG.WorldError, match="lod is low, medium or high"):
        c.plan(str(tmp_path), {"mode": "text", "prompt": "x", "lod": "ultra"})
    with pytest.raises(WG.WorldError, match="outside the project root"):
        c.plan(str(tmp_path), {"mode": "image", "prompt": "x", "lod": "low", "image": "../a.png"})


def test_no_backend_configured_is_needs_key():
    out = WG.plan_or_needs_key(None, "/tmp/x", {"mode": "text", "prompt": "x", "lod": "low"})
    assert out["state"] == "needs_key" and "no world-model backend configured" in out["error"]


def test_a_confirmed_run_writes_the_three_files_through_the_egress_gate(tmp_path):
    EG.install()
    eg = EG.Egress(tmp_path / "egress")
    eg.set_route("world_labs", True)
    EG.set_active(eg)
    try:
        calls = []
        c = WG.WorldClient(key="k-test", transport=fake_transport(calls), poll_s=0)
        img = tmp_path / "ref.png"
        img.write_bytes(b"\x89PNG fake")
        plan = c.plan(str(tmp_path), {"mode": "image", "prompt": "temple", "lod": "low", "image": "ref.png"})
        out = c.run(str(tmp_path), plan, confirmed_by="user")
        files = {f["kind"]: f for f in out["files"]}
        assert set(files) == {"spz", "glb", "pano"}
        for k, data in FILES.items():
            assert (tmp_path / files[k]["path"]).read_bytes() == data
        assert files["spz"]["path"].startswith("worlds/w1/") and calls[0] == ("POST", "/v1/worlds")
        sent = [r for r in eg.log() if r.get("event") == "send"]
        assert sent and all(r["route"] == "world_labs" for r in sent)
        body = json.loads(c.last_request)                                         # the submitted body, without the key
        assert body.get("params") == {"mode": "image", "lod": "low"} and base64.b64decode(body["image_bytes_b64"]) == b"\x89PNG fake"
    finally:
        EG.set_active(None)


def test_a_route_that_is_off_sends_nothing_and_an_agent_cannot_confirm(tmp_path):
    EG.install()
    eg = EG.Egress(tmp_path / "egress")
    EG.set_active(eg)
    try:
        calls = []
        c = WG.WorldClient(key="k-test", transport=fake_transport(calls), poll_s=0)
        plan = c.plan(str(tmp_path), {"mode": "text", "prompt": "temple", "lod": "low"})
        with pytest.raises(WG.WorldError, match="only the user confirms"):
            c.run(str(tmp_path), plan, confirmed_by="agent")
        with pytest.raises(EG.EgressRefused, match="world_labs is off"):
            c.run(str(tmp_path), plan, confirmed_by="user")
        assert calls == []
    finally:
        EG.set_active(None)



def test_the_agent_tool_answers_needs_key_without_a_backend_and_plans_with_one(tmp_path, monkeypatch):
    import asyncio
    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.turns import AgentHub
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("LAMPWAY_WORLD_LABS_KEY", raising=False)
    hub = AgentHub.__new__(AgentHub)
    args = {"action": "plan", "mode": "text", "prompt": "a temple", "lod": "low"}
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c", "lampway_splat_world", args)))
    assert not err and json.loads(out)["state"] == "needs_key"
    monkeypatch.setenv("LAMPWAY_WORLD_LABS_KEY", "k-test")
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c", "lampway_splat_world", args)))
    card = json.loads(out)
    assert not err and card["state"] == "needs_approval" and "_clean" not in card and "k-test" not in out
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c", "lampway_splat_world", dict(args, action="generate"))))
    assert err and "only plans" in out
