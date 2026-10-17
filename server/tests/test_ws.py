"""The agent WebSocket's system layer (socket_connection.py, jsonrpc_frames.py,
socket_reauth.py, connection_manager.py on_connected)."""

import pytest
from starlette.websockets import WebSocketDisconnect


def test_handshake_is_answered_with_success_agent_ws_v1_and_only_the_history_capabilities_it_serves(fake):
    """Spec R2: the handshake advertises only what is served. This server runs no engine (no Mode 1, no Hermes sessions), so it
    serves no archive and advertises none; with the engine it is ``agent_history_v1`` alone (test_engine_history.py)."""
    fake.login()
    with fake.connect_ws() as ws:
        reply = fake.handshake(ws)
    result = reply["result"]
    assert result["success"] is True                 # jsonrpc_frames.py:99
    assert result["agent_ws_v1"] is True             # socket_connection.py:361
    assert "agent_history_v1" not in result["server_capabilities"]
    assert "agent_history_v2" not in result["server_capabilities"]


def test_upgrade_with_a_bad_bearer_is_closed_with_4001(fake):
    with pytest.raises(WebSocketDisconnect) as closed:
        with fake.connect_ws(token="not-a-token") as ws:
            ws.receive_json()
    assert closed.value.code == 4001                 # WS_CLOSE_AUTH_FAILED


def test_upgrade_without_any_bearer_is_closed_with_4001(fake):
    with pytest.raises(WebSocketDisconnect) as closed:
        with fake.connect_ws(token=None) as ws:
            ws.receive_json()
    assert closed.value.code == 4001


def test_ping_without_params_gets_a_result_with_the_same_id(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        ws.send_json({"jsonrpc": "2.0", "method": "system.ping", "id": "ping_7"})  # socket_requests.py:91-96
        reply = ws.receive_json()
    assert reply["id"] == "ping_7" and "result" in reply


def test_reauth_accepts_our_token_and_refuses_garbage(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        good = fake.request(ws, "system.reauth", {"token": fake.access_token})
        reply = ws.receive_json()
        assert reply["id"] == good and reply["result"]["authenticated"] is True   # socket_reauth.py:47
        bad = fake.request(ws, "system.reauth", {"token": "garbage"})
        reply = ws.receive_json()
        assert reply["id"] == bad and reply["result"]["authenticated"] is False


def test_unknown_method_is_method_not_found(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "agent.no_such_method", {"session_ids": []})
        reply = ws.receive_json()
    assert reply["id"] == rid and reply["error"]["code"] == -32601   # sync.py: -32601 => older backend, stop


def test_notification_and_job_sync_stubs(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        rid = fake.request(ws, "notifications.sync", {})
        reply = ws.receive_json()
        assert reply["id"] == rid and reply["result"]["notifications"] == []   # connection_manager.py:223
        rid = fake.request(ws, "job.sync", {})
        reply = ws.receive_json()
        assert reply["id"] == rid and reply["result"]["jobs"] == []            # queue_manager.py:222
        rid = fake.request(ws, "job.get", {"job_id": "nope"})
        reply = ws.receive_json()
        assert reply["id"] == rid and reply["result"]["job"] is None           # queue_manager.py:288
        rid = fake.request(ws, "system.set_context", {"telemetry_consent": False})
        reply = ws.receive_json()
        assert reply["id"] == rid and "result" in reply                        # an error here closes the socket
        rid = fake.request(ws, "notifications.mark_read", {"notification_ids": ["x"]})
        reply = ws.receive_json()
        assert reply["id"] == rid and "result" in reply


def test_a_notification_frame_without_an_id_is_not_answered(fake):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        ws.send_json({"jsonrpc": "2.0", "method": "generation.agent_result", "params": {}})
        ws.send_json({"jsonrpc": "2.0", "method": "system.ping", "id": "ping_1"})
        reply = ws.receive_json()
    assert reply["id"] == "ping_1"
