"""MCP, the two endpoints the client's connector uses (docs "Connect AI apps"): GET /api/v1/mcp-desktop/eligibility says whether the
desktop instance is connected (200 {eligible, instance_id, contract, valid_for_seconds}; a 404 with another detail means "desktop
not connected"), and POST /api/v1/mcp forwards one MCP JSON-RPC message from an external AI app: initialize, notifications (202),
tools/list, tools/call. A tool call runs in the app instance named by X-Mixar-Instance-Id, in the scene session named by
X-Mixar-Session-Id, exactly as the agent's own tool calls do. The studio tools (credits) are NOT offered over MCP."""

import threading

import pytest

HEAD = {"X-Mixar-Instance-Id": "", "X-Mixar-Session-Id": "scene-1"}


@pytest.fixture
def signed(fake):
    fake.login()
    return fake


def _rpc(fake, body, instance=None, session="scene-1"):
    headers = {"X-Mixar-Instance-Id": instance or fake.instance_id, "X-Mixar-Session-Id": session,
               "Accept": "application/json, text/event-stream"}
    return fake.post("/api/v1/mcp", json=body, headers=headers)


def test_eligibility_needs_a_bearer_and_a_connected_instance(signed, http):
    assert http.get("/api/v1/mcp-desktop/eligibility", headers={"X-Mixar-Instance-Id": "x"}).status_code == 401
    assert signed.get("/api/v1/mcp-desktop/eligibility").status_code == 422
    r = signed.get("/api/v1/mcp-desktop/eligibility", headers={"X-Mixar-Instance-Id": "nobody"})
    assert r.status_code == 404 and "not connected" in r.json()["detail"] and r.json()["detail"] != "Not Found"
    with signed.connect_ws() as ws:
        signed.handshake(ws)
        r = signed.get("/api/v1/mcp-desktop/eligibility", headers={"X-Mixar-Instance-Id": signed.instance_id})
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True and body["instance_id"] == signed.instance_id and body["contract"] == "mixar_ui_v1"
    assert 1 <= body["valid_for_seconds"] <= 60


def test_initialize_notifications_and_ping(signed):
    r = _rpc(signed, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                                                      "clientInfo": {"name": "t", "version": "1"}}})
    res = r.json()["result"]
    assert r.status_code == 200 and res["serverInfo"]["name"] == "lampway" and "tools" in res["capabilities"] and res["protocolVersion"]
    assert _rpc(signed, {"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    assert _rpc(signed, {"jsonrpc": "2.0", "id": 2, "method": "ping"}).json()["result"] == {}
    assert _rpc(signed, {"jsonrpc": "2.0", "id": 3, "method": "nope"}).json()["error"]["code"] == -32601
    assert signed.post("/api/v1/mcp", content=b"not json", headers={"X-Mixar-Instance-Id": "x"}).json()["error"]["code"] == -32700


def test_tools_list_offers_the_scene_and_lampway_tools_but_never_the_credit_spending_studio_tools(signed):
    tools = _rpc(signed, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"run_blender_python", "scene_summary", "lampway_retopo", "lampway_uv_unwrap", "lampway_auto_rig"} <= names
    assert not [n for n in names if n.startswith("studio_")] and "ask_user" not in names
    assert all(t["inputSchema"]["type"] == "object" and t["description"] for t in tools)


def _serve_client(fake, answers, ready, stop):
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        ready.set()
        while not stop.is_set():
            try:
                frame = ws.receive_json()
            except Exception:  # noqa: BLE001
                return
            if frame.get("method") == "mcp.begin_operation":                # the scene lease every MCP scene call runs in (audit F2)
                answers.append(frame["params"])
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": {"success": True, "operation_id": frame["params"]["operation_id"],
                                                                             "session_id": frame["params"]["session_id"], "scene_name": "Scene"}})
            elif frame.get("method") == "blender.execute_script":
                answers.append(frame["params"])
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": {"success": True, "output": "hello from blender", "created_objects": ["Cube"]}})
            elif frame.get("method") == "mcp.end_operation":
                answers.append(frame["params"])
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": {"success": True, "released": True}})
                return


def test_tools_call_runs_the_script_in_the_named_instance_and_scene_and_returns_its_result(signed):
    answers, ready, stop = [], threading.Event(), threading.Event()
    t = threading.Thread(target=_serve_client, args=(signed, answers, ready, stop), daemon=True)
    t.start()
    assert ready.wait(10)
    r = _rpc(signed, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                      "params": {"name": "run_blender_python", "arguments": {"script": "print('hi')"}}}, session="scene-xyz")
    stop.set()
    t.join(5)
    res = r.json()["result"]
    assert res["isError"] is False and "hello from blender" in res["content"][0]["text"] and "Cube" in res["content"][0]["text"]
    begin, script, end = answers
    assert script["script"] == "print('hi')" and script["session_id"] == "scene-xyz" and script["tool_name"] == "run_blender_python"
    assert begin["session_id"] == "scene-xyz" and script["agent_ctx"]["mcp_operation_id"] == begin["operation_id"] == end["operation_id"]


def test_tools_call_without_a_connected_instance_or_with_a_bad_tool_is_an_error_result_not_a_crash(signed):
    r = _rpc(signed, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "1"}}},
             instance="nobody")
    res = r.json()["result"]
    assert res["isError"] is True and "not connected" in res["content"][0]["text"]
    bad = _rpc(signed, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "studio_tripo_mesh", "arguments": {}}})
    assert bad.json()["error"]["code"] == -32602 and "studio_tripo_mesh" in bad.json()["error"]["message"]


def test_mcp_requires_a_bearer(http):
    assert http.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401
