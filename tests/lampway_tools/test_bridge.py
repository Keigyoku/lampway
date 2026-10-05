# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live bridge: a socket the Blender MCP connects to, polled from the app's own timer.

Wire contract (the shelf's live/bridge.py, which the main session drives today): the client sends
``{"type": "execute", "code": ..., "strict_json": bool}`` + NUL; the reply is
``{"status": "ok"|"error", "result" | "message", "stdout", "stderr"}`` + NUL. A bare connect (a port probe)
carries no request and gets no reply. Everything runs on the main thread, inside a window context.
"""

import json
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import bridge  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ask(port, payload, timeout=5.0):
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as c:
        c.sendall(json.dumps(payload).encode() + b"\0")
        buf = b""
        while b"\0" not in buf:
            chunk = c.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.partition(b"\0")[0]) if buf else None


def _serve_in_thread(b, rounds=1):
    """Pump the bridge the way the timer does, while the test client talks."""
    done = threading.Event()

    def loop():
        for _ in range(2000):
            if b.pump() >= rounds:
                break
            done.wait(0.005)
    t = threading.Thread(target=loop)
    t.start()
    return t


@pytest.fixture
def make():
    made = []

    def _make(run=None, **kw):
        b = bridge.Bridge(port=kw.pop("port", _free_port()), run_code=run or bridge.exec_code, **kw)
        assert b.start() is True
        made.append(b)
        return b
    yield _make
    for b in made:
        b.stop()


def test_execute_returns_result_and_stdout(make):
    b = make()
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "print('hi')\nresult = {'n': 2}"})
    t.join()
    assert reply == {"status": "ok", "result": {"n": 2}, "stdout": "hi\n", "stderr": ""}


def test_an_exception_comes_back_as_an_error_with_a_traceback(make):
    b = make()
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "1/0"})
    t.join()
    assert reply["status"] == "error"
    assert "ZeroDivisionError" in reply["message"]
    assert reply["stdout"] == "" and reply["stderr"] == ""


def test_a_bare_connect_gets_no_reply_and_does_not_break_the_next_request(make):
    b = make()
    probe = socket.create_connection(("127.0.0.1", b.port))
    probe.close()
    t = _serve_in_thread(b, rounds=2)
    reply = _ask(b.port, {"type": "execute", "code": "result = 1"})
    t.join()
    assert reply["result"] == 1


def test_strict_json_refuses_an_unserialisable_result(make):
    b = make()
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "result = {1, 2}", "strict_json": True})
    t.join()
    assert reply["status"] == "error"
    assert "not JSON-serialisable" in reply["message"]


def test_non_strict_json_reprs_an_unserialisable_result(make):
    b = make()
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "result = {1, 2}"})
    t.join()
    assert reply["status"] == "ok" and reply["result"] == "{1, 2}"


def test_the_injected_runner_gets_the_code_and_decides_the_context(make):
    seen = []

    def run(code, g):
        seen.append(code)
        g["result"] = "from-runner"
    b = make(run=run)
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "ignored"})
    t.join()
    assert seen == ["ignored"] and reply["result"] == "from-runner"


def test_a_port_already_in_use_is_reported_not_raised():
    port = _free_port()
    first = bridge.Bridge(port=port, run_code=bridge.exec_code)
    assert first.start() is True
    try:
        second = bridge.Bridge(port=port, run_code=bridge.exec_code)
        assert second.start() is False
        assert "in use" in second.error
    finally:
        first.stop()


def test_port_zero_means_disabled():
    b = bridge.Bridge(port=0, run_code=bridge.exec_code)
    assert b.start() is False and b.enabled is False and b.error == "disabled (port 0)"


def test_config_from_env_prefers_lampway_names_then_the_mcp_name(monkeypatch):
    monkeypatch.delenv("LAMPWAY_BRIDGE_PORT", raising=False)
    monkeypatch.delenv("BLENDER_MCP_PORT", raising=False)
    assert bridge.port_from_env() == 9876
    monkeypatch.setenv("BLENDER_MCP_PORT", "9999")
    assert bridge.port_from_env() == 9999
    monkeypatch.setenv("LAMPWAY_BRIDGE_PORT", "1234")
    assert bridge.port_from_env() == 1234
    monkeypatch.setenv("LAMPWAY_BRIDGE_PORT", "nope")
    assert bridge.port_from_env() == 9876


def test_the_socket_is_loopback_only(make):
    b = make()
    assert b.address[0] == "127.0.0.1"


def test_inbox_runs_numbered_files_once_and_writes_the_outbox(tmp_path):
    inbox, outbox = tmp_path / "inbox", tmp_path / "outbox"
    inbox.mkdir()
    (inbox / "002_b.py").write_text("raise ValueError('boom')")
    (inbox / "001_a.py").write_text("ran.append(1)")
    ran = []
    b = bridge.Bridge(port=0, run_code=lambda code, g: exec(compile(code, "<t>", "exec"), {"ran": ran, **g}),
                      inbox=inbox, outbox=outbox)
    assert b.poll_inbox() == 2
    assert ran == [1]
    assert not list(inbox.iterdir())                       # consumed
    ok, bad = (json.loads((outbox / n).read_text()) for n in ("001_a.json", "002_b.json"))
    assert ok["ok"] is True and bad["ok"] is False and "ValueError" in bad["error"]
    assert b.poll_inbox() == 0
