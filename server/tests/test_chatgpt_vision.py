# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import base64
import copy
import json
import re
import time
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette

from lampway_server.agent.providers.base import Message, ModelRequest
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanProvider

IMAGE = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "c3ludGhldGlj"}, "detail": "low"}


def test_user_typed_image_preserves_order_bytes_mime_detail():
    message = Message("user", [{"type": "text", "text": "caption"}, IMAGE, {"type": "text", "text": "after"}])
    content = ChatGPTPlanProvider._items(message)[0]["content"]
    assert [p["type"] for p in content] == ["input_text", "input_image", "input_text"]
    assert content[1] == {"type": "input_image", "image_url": "data:image/png;base64,c3ludGhldGlj", "detail": "low"}


def test_tool_images_acknowledge_all_calls_before_labeled_images():
    msg = Message("user", [{"type": "tool_result", "tool_call_id": "a", "content": [{"type": "text", "text": "A"}, IMAGE]},
                           {"type": "tool_result", "tool_call_id": "b", "content": [{"type": "text", "text": "B"}, IMAGE]}])
    original = copy.deepcopy(msg)
    parts = ChatGPTPlanProvider._items(msg)
    assert [p["type"] for p in parts] == ["function_call_output", "function_call_output", "message", "message"]
    assert [p["output"] for p in parts[:2]] == ["A", "B"]
    assert [p["content"][0]["text"] for p in parts[2:]] == ["Images from tool call a", "Images from tool call b"]
    assert msg == original


@pytest.fixture
def stack(tmp_path, monkeypatch):
    from lampway_server import chatgpt_auth as CA, chatgpt_vision as V, egress
    auth = CA.ChatGPTAuth(tmp_path / "state", http=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected auth request"))))
    auth._write({"selected": "synthetic-client", "accounts": {"synthetic-client": {
        "issuer": CA.ISSUER, "subject": "synthetic-account", "client_id": "synthetic-client", "ext_agent_host_id": "synthetic-host",
        "vision_login_id": "synthetic-login", "access_token": "synthetic-access", "expires_at": time.time()+3600, "scopes": [CA.DIRECT_SCOPE]}}})
    monkeypatch.setattr(egress, "preflight", lambda route: None)
    monkeypatch.setattr(V.secrets, "choice", lambda values: "RED")
    return auth, V


def stream_response(text=" ".join(["RED"]*8), ending="response.completed"):
    return httpx.Response(200, text='data: '+json.dumps({"type": "response.output_text.delta", "delta": text})+'\n\ndata: '+json.dumps({"type": ending})+'\n\n')


def verified(auth, V):
    V.CF.atomic_write_json(V._path(auth,"synthetic-model"), {"version": V.VERSION, "status": "verified", "account_scope": auth.vision_account_scope(),
        "route": V.ROUTE, "model": "synthetic-model", "completed": True, "attempt": "a"*32,
        "image_sha256": "b"*64, "started_at": 0, "finished_at": 0, "verified_at": 0})


def test_fixed_probe_pending_before_bytes_receipt_no_secrets_and_durable(stack):
    auth, V = stack
    calls=[]
    def handler(request):
        assert V._read(auth,"synthetic-model")["status"] == "pending"
        assert str(request.url) == V.ROUTE and request.method == "POST"
        body=json.loads(request.content);calls.append(body)
        assert set(body)=={"model", "instructions", "store", "stream", "input"}
        assert body["store"] is False and body["stream"] is True
        raw=base64.b64decode(body["input"][0]["content"][1]["image_url"].split(",",1)[1])
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        return stream_response()
    assert asyncio.run(V.probe(auth, "synthetic-model", consent=True, transport=httpx.MockTransport(handler)))["images_enabled"]
    assert len(calls)==1 and V.admitted(auth,"synthetic-model")
    raw=V._path(auth,"synthetic-model").read_text()
    assert all(x not in raw for x in ["synthetic-access", "synthetic-account", "synthetic-client", "RED RED", "data:image"])
    assert V._path(auth,"synthetic-model").stat().st_mode & 0o777 == 0o600
    assert auth.dir.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("change", [{"version": 2}, {"version": True}, {"status": "failed"}, {"status": "pending"}, {"model": "other"},
    {"route": "https://other.invalid/responses"}, {"account_scope": "other"}])
def test_scope_stale_or_malformed_receipts_fail_closed(stack, change):
    auth,V=stack;verified(auth,V);r=V._read(auth,"synthetic-model");r.update(change);V.CF.atomic_write_json(V._path(auth,"synthetic-model"),r)
    assert not V.admitted(auth,"synthetic-model")


def test_new_signin_invalidates_but_token_rotation_preserves_scope(stack):
    auth,V=stack;verified(auth,V);data=auth._read();acct=data["accounts"][data["selected"]]
    acct["access_token"]="synthetic-rotation";auth._write(data);assert V.admitted(auth,"synthetic-model")
    acct["vision_login_id"]="new-login";auth._write(data);assert not V.admitted(auth,"synthetic-model")


def test_scope_bound_token_refuses_account_switch(stack):
    auth,V=stack;scope=auth.vision_account_scope();data=auth._read();data["accounts"][data["selected"]]["subject"]="other";auth._write(data)
    with pytest.raises(Exception, match="sign-in changed"):
        asyncio.run(auth.access_token_for_scope(scope))


@pytest.mark.parametrize("response", [lambda: httpx.Response(400,text="synthetic-access"), lambda:stream_response("WRONG"),
    lambda:stream_response(ending="response.failed"), lambda:stream_response(ending="response.incomplete")])
def test_rejection_or_incorrect_probe_invalidates_prior_pass(stack,response):
    auth,V=stack;verified(auth,V)
    assert not asyncio.run(V.probe(auth,"synthetic-model",consent=True,transport=httpx.MockTransport(lambda r:response())))["images_enabled"]
    assert V._read(auth,"synthetic-model")["status"]=="failed"


def test_unknown_blocks_retry_without_ack_and_no_auto_retry(stack):
    auth,V=stack;calls=[]
    def handler(r):calls.append(r);raise httpx.ConnectError("synthetic network failure")
    with pytest.raises(httpx.ConnectError):asyncio.run(V.probe(auth,"synthetic-model",consent=True,transport=httpx.MockTransport(handler)))
    assert V._read(auth,"synthetic-model")["status"]=="unknown"
    with pytest.raises(ValueError,match="acknowledge"):asyncio.run(V.probe(auth,"synthetic-model",consent=True,transport=httpx.MockTransport(handler)))
    assert len(calls)==1


def test_probe_requires_click_and_route_opt_in_before_receipt(stack,monkeypatch):
    auth,V=stack
    with pytest.raises(ValueError,match="consent"):asyncio.run(V.probe(auth,"synthetic-model"))
    from lampway_server import egress
    monkeypatch.setattr(egress,"preflight",lambda route: (_ for _ in ()).throw(ValueError("route off")))
    with pytest.raises(ValueError,match="route off"):asyncio.run(V.probe(auth,"synthetic-model",consent=True))
    assert not V._path(auth,"synthetic-model").exists()


def test_final_provider_and_gateway_refuse_planted_vision_and_preserve_history(stack):
    auth,V=stack
    from lampway_server.engine import gateway as G
    p=ChatGPTPlanProvider(auth,"synthetic-model",transport=httpx.MockTransport(lambda r:stream_response("OK")))
    req=ModelRequest("system",[Message("user",[IMAGE])],[]);original=copy.deepcopy(req)
    G._provider_images(req,p,True)
    assert req.messages[0].content[0]["type"]=="text"
    seen=[]
    p.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:(seen.append(json.loads(r.content)) or stream_response("OK"))))
    async def run():
        try:return [e async for e in p.stream(original)]
        finally:await p.client.aclose()
    asyncio.run(run());assert "input_image" not in json.dumps(seen)
    assert original.messages[0].content==[IMAGE]
    verified(auth,V);assert G.models_dev_registry(p,vision=True)["lampway"]["models"]["synthetic-model"]["attachment"]


def test_proved_final_provider_preserves_typed_image(stack):
    auth,V=stack;verified(auth,V);seen=[]
    p=ChatGPTPlanProvider(auth,"synthetic-model",transport=httpx.MockTransport(lambda r:(seen.append(json.loads(r.content)) or stream_response("OK"))))
    async def run():
        try:return [e async for e in p.stream(ModelRequest("system",[Message("user",[IMAGE])],[]))]
        finally:await p.client.aclose()
    asyncio.run(run());assert seen[0]["input"][0]["content"][0]["type"]=="input_image"


def test_browser_disclosure_one_use_and_no_arbitrary_payload(stack):
    auth,V=stack
    from lampway_server.chatgpt_vision_routes import routes
    calls=[]
    async def run_probe(auth,model,**kwargs):calls.append((model,kwargs));return {"images_enabled":False,"status":"failed","model":model}
    def origin(request):return "agent" if request.headers.get("x-lampway-origin") in {"agent","mcp"} else "user"
    app=Starlette(routes=routes(auth,lambda:"synthetic-model",origin,human_session=lambda r:("synthetic-user-session",time.time()+3600) if r.headers.get("authorization")=="Bearer synthetic-user" else None,run_probe=run_probe))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("127.0.0.1",1234)),base_url="http://127.0.0.1:8787") as c:
            entry=await c.post("/app/chatgpt/vision/ticket",json={},headers={"Authorization":"Bearer synthetic-user"})
            assert entry.status_code==200
            page=await c.get(entry.json()["path"]);assert V.DISCLOSURE in page.text
            nonce=re.search('name="consent" value="([^"]+)"',page.text)[1]
            assert "HttpOnly" in page.headers["set-cookie"] and "SameSite=strict" in page.headers["set-cookie"]
            for headers in [{"x-lampway-origin":"agent"},{"x-lampway-origin":"mcp"},{"authorization":"Bearer synthetic"},{"origin":"http://127.0.0.1:9999"}]:
                assert (await c.post("/app/chatgpt/vision",data={"consent":nonce},headers=headers)).status_code==403
            assert (await c.post("/app/chatgpt/vision",data={"consent":nonce,"prompt":"arbitrary"})).status_code==400
            assert (await c.post("/app/chatgpt/vision",data={"consent":nonce})).status_code==200
            assert (await c.post("/app/chatgpt/vision",data={"consent":nonce})).status_code==403
    asyncio.run(run());assert calls==[("synthetic-model",{"consent":True,"acknowledge_unknown":False})]


def test_timestamp_is_audit_only_no_expiry_policy(stack):
    auth,V=stack;verified(auth,V);r=V._read(auth,"synthetic-model");r["verified_at"]=0;V.CF.atomic_write_json(V._path(auth,"synthetic-model"),r)
    assert V.admitted(auth,"synthetic-model")


def test_failed_image_request_invalidates_matching_receipt(stack):
    auth,V=stack;verified(auth,V)
    p=ChatGPTPlanProvider(auth,"synthetic-model",transport=httpx.MockTransport(lambda r:httpx.Response(400,json={"error":{"code":"subscription_sharing_unsupported_capability"}})))
    async def run():
        try:
            with pytest.raises(Exception):
                _=[e async for e in p.stream(ModelRequest("system",[Message("user",[IMAGE])],[]))]
        finally:await p.client.aclose()
    asyncio.run(run());assert not V.admitted(auth,"synthetic-model") and V._read(auth,"synthetic-model")["status"]=="failed"


def test_account_switch_during_probe_never_qualifies_new_account(stack):
    auth,V=stack
    def handler(request):
        data=auth._read();data["accounts"][data["selected"]]["subject"]="changed";auth._write(data)
        return stream_response()
    assert not asyncio.run(V.probe(auth,"synthetic-model",consent=True,transport=httpx.MockTransport(handler)))["images_enabled"]


def test_malformed_receipt_and_missing_login_generation_fail_closed(stack):
    auth,V=stack;V._path(auth,"synthetic-model").parent.mkdir();V._path(auth,"synthetic-model").write_text("malformed");assert not V.admitted(auth,"synthetic-model")
    data=auth._read();data["accounts"][data["selected"]].pop("vision_login_id");auth._write(data)
    assert auth.vision_account_scope() is None


def test_distinct_models_keep_independent_qualifications(stack):
    auth,V=stack;verified(auth,V)
    result=asyncio.run(V.probe(auth,"other-model",consent=True,transport=httpx.MockTransport(lambda r:stream_response())))
    assert result["images_enabled"] and V.admitted(auth,"synthetic-model") and V.admitted(auth,"other-model")


def test_concurrent_probe_cannot_rebind_even_with_acknowledgement(stack):
    auth,V=stack
    async def run():
        entered=asyncio.Event();release=asyncio.Event()
        async def handler(request):entered.set();await release.wait();return stream_response()
        first=asyncio.create_task(V.probe(auth,"synthetic-model",consent=True,transport=httpx.MockTransport(handler)))
        await entered.wait()
        with pytest.raises(ValueError,match="already running"):
            await V.probe(auth,"synthetic-model",consent=True,acknowledge_unknown=True,transport=httpx.MockTransport(handler))
        release.set();assert (await first)["images_enabled"]
    asyncio.run(run())


def test_named_summary_matches_own_model_receipt_with_nonplan_main(stack):
    auth,V=stack;verified(auth,V)
    from lampway_server.engine.wiring import _SummaryProvider, selected_vision
    resolution=SimpleNamespace(provider="chatgpt_plan",model="synthetic-model",params={})
    agent=SimpleNamespace(provider=SimpleNamespace(name="mock",model="main"))
    summary=_SummaryProvider(None,agent,resolution,auth)
    assert summary.supports_vision and selected_vision(summary,agent)
    resolution.model="other-model";assert not _SummaryProvider(None,agent,resolution,auth).supports_vision


def test_browser_result_requests_existing_native_refresh_without_a_turn(stack):
    auth,V=stack
    from lampway_server.chatgpt_vision_routes import routes
    changes=[]
    async def fail(auth,model,**kwargs):raise httpx.ConnectError("synthetic failure")
    app=Starlette(routes=routes(auth,lambda:"synthetic-model",lambda request:"user",human_session=lambda r:("synthetic-user-session",time.time()+3600) if r.headers.get("authorization")=="Bearer synthetic-user" else None,run_probe=fail,on_change=lambda:changes.append("refresh")))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("127.0.0.1",1234)),base_url="http://127.0.0.1:8787") as c:
            entry=await c.post("/app/chatgpt/vision/ticket",json={},headers={"Authorization":"Bearer synthetic-user"})
            assert entry.status_code==200
            page=await c.get(entry.json()["path"]);nonce=re.search('name="consent" value="([^"]+)"',page.text)[1]
            assert not changes
            assert (await c.post("/app/chatgpt/vision",data={"consent":nonce})).status_code==502
    asyncio.run(run());assert changes==["refresh"]


def test_minimal_verified_status_without_completed_evidence_is_refused(stack):
    auth,V=stack;verified(auth,V)
    r=V._read(auth,"synthetic-model")
    for key in ["completed","attempt","image_sha256","started_at","finished_at"]:r.pop(key,None)
    V.CF.atomic_write_json(V._path(auth,"synthetic-model"),r)
    assert not V.admitted(auth,"synthetic-model")


def test_matching_explicit_resolution_false_overrides_receipt(stack):
    auth,V=stack;verified(auth,V)
    from lampway_server.engine.wiring import selected_vision
    p=ChatGPTPlanProvider(auth,"synthetic-model")
    choice=SimpleNamespace(model="synthetic-model",params={"supports_vision":False})
    assert selected_vision(p,SimpleNamespace(),choice) is False


def test_explicit_request_false_with_valid_receipt_never_sends_images(stack):
    auth,V=stack;verified(auth,V);seen=[]
    p=ChatGPTPlanProvider(auth,"synthetic-model",transport=httpx.MockTransport(lambda r:(seen.append(json.loads(r.content)) or stream_response("OK"))))
    req=ModelRequest("system",[Message("user",[IMAGE])],[]);req.supports_vision=False
    async def run():
        try:return [e async for e in p.stream(req)]
        finally:await p.client.aclose()
    asyncio.run(run());assert "input_image" not in json.dumps(seen) and req.messages[0].content==[IMAGE]


@pytest.mark.parametrize("change", [{"completed":False},{"completed":1},{"attempt":"short"},{"image_sha256":"wrong"},
    {"started_at":float("nan")},{"finished_at":float("inf")},{"started_at":2,"finished_at":1},
    {"finished_at":2,"verified_at":3},{"started_at":True}])
def test_invalid_completed_evidence_shape_fails_closed(stack,change):
    auth,V=stack;verified(auth,V);r=V._read(auth,"synthetic-model");r.update(change);V.CF.atomic_write_json(V._path(auth,"synthetic-model"),r)
    assert not V.admitted(auth,"synthetic-model")



def test_eight_panel_png_matches_its_full_semantic_challenge(stack,monkeypatch):
    auth,V=stack
    import struct,zlib
    choices=iter(["RED","GREEN","BLUE","GREEN","RED","BLUE","RED","GREEN"])
    monkeypatch.setattr(V.secrets,"choice",lambda values:next(choices))
    png,expected=V._challenge()
    assert expected=="RED GREEN BLUE GREEN RED BLUE RED GREEN"
    offset=8;chunks={}
    while offset<len(png):
        size=struct.unpack("!I",png[offset:offset+4])[0];kind=png[offset+4:offset+8];raw=png[offset+8:offset+8+size]
        crc=struct.unpack("!I",png[offset+8+size:offset+12+size])[0]
        assert zlib.crc32(kind+raw)==crc
        chunks[kind]=raw;offset+=12+size
    assert struct.unpack("!2I5B",chunks[b"IHDR"])==(128,16,8,2,0,0,0)
    colors={"RED":bytes([255,0,0]),"GREEN":bytes([0,255,0]),"BLUE":bytes([0,0,255])}
    row=b"\0"+b"".join(colors[c]*16 for c in expected.split())
    assert zlib.decompress(chunks[b"IDAT"])==row*16


def test_gateway_preserves_explicit_request_false_with_true_receipt(stack):
    auth,V=stack;verified(auth,V)
    from lampway_server.engine.gateway import _provider_images
    p=ChatGPTPlanProvider(auth,"synthetic-model")
    request=ModelRequest("system",[Message("user",[IMAGE])],[],supports_vision=False)
    _provider_images(request,p,True)
    assert request.supports_vision is False and request.messages[0].content[0]["type"]=="text"



def test_scope_bound_refresh_grant_loss_refuses_before_inference(stack):
    auth,V=stack;scope=auth.vision_account_scope();data=auth._read();acct=data["accounts"][data["selected"]]
    acct.update(expires_at=0,refresh_token="synthetic-refresh");auth._write(data)
    auth.http=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={
        "access_token":"synthetic-new-access","refresh_token":"synthetic-new-refresh","scope":"openid","expires_in":3600})))
    from lampway_server.chatgpt_auth import PlanUsageDisabled
    with pytest.raises(PlanUsageDisabled,match="scope changed"):
        asyncio.run(auth.access_token_for_scope(scope))
    assert auth.vision_account_scope() is None
