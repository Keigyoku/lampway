# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's ACP boundary in front of a Grok worker's native agent (issue #11 P4-17): a client MCP update that would replace the
canonical lampway_pane never reaches native Grok and is refused by name; everything else passes unchanged. The native proof is
tests/qa/grok_worker_boundary_validation.py."""
import io
import json
import sys
import textwrap

import pytest

from lampway_server import grok_acp_boundary as B
from lampway_server import grok_worker as G

CONNECTOR = "/owned/lampway-pane-mcp"


def update(*servers, rid=7):
    return {"jsonrpc": "2.0", "id": rid, "method": "_x.ai/session/update_mcp_servers",
            "params": {"sessionId": "s1", "mcpServers": list(servers)}}


HTTP = {"type": "http", "name": "lampway_pane", "url": "http://127.0.0.1:9/foreign-http", "headers": []}
SSE = {"type": "sse", "name": "lampway_pane", "url": "http://127.0.0.1:9/foreign-sse", "headers": []}
FOREIGN_ARGV = {"name": "lampway_pane", "command": sys.executable, "args": ["--fake-mcp", "x.jsonl"], "env": []}
CANONICAL_ENV = {"name": "lampway_pane", "command": CONNECTOR, "args": [], "env": [{"name": "A", "value": "1"}]}


@pytest.mark.parametrize("entry", [HTTP, SSE, FOREIGN_ARGV, {**HTTP, "name": "Lampway Pane"}, {**SSE, "name": "LAMPWAY_PANE"},
                                   {**HTTP, "name": "grok_com_lampway_pane"}, {**FOREIGN_ARGV, "command": CONNECTOR, "args": ["x"]},
                                   {"name": "lampway_pane", "url": "http://127.0.0.1:9/no-type"}])
def test_an_update_that_would_replace_the_canonical_server_is_refused(entry):
    assert B.screen(update({"name": "dynamic", "command": "x", "args": []}, entry), CONNECTOR)


@pytest.mark.parametrize("method", ["session/new", "session/load", "session/resume"])
def test_a_session_that_would_start_with_a_replaced_canonical_server_is_refused(method):
    assert B.screen({"jsonrpc": "2.0", "id": 1, "method": method, "params": {"cwd": "/p", "mcpServers": [HTTP]}}, CONNECTOR)


@pytest.mark.parametrize("message", [
    update(CANONICAL_ENV),                                                  # the canonical argv itself: native decides the rest
    update({**HTTP, "name": "foreign_http"}),                               # another name: the owned policy files decide it
    update(),
    {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "/p", "mcpServers": []}},
    {"jsonrpc": "2.0", "id": 2, "method": "_x.ai/mcp/list", "params": {"sessionId": "s1"}},
    "not a frame", None])
def test_everything_else_passes(message):
    assert B.screen(message, CONNECTOR) == ""


@pytest.mark.parametrize("message", [
    {"jsonrpc": "2.0", "id": 3, "method": "_x.ai/some/future_method", "params": {"mcpServers": [HTTP]}},  # any method carrying a list
    {"jsonrpc": "2.0", "id": 4, "method": "session/new", "params": {"mcpServers": {"lampway_pane": HTTP}}},  # not a list
    update("lampway_pane"),                                                                                # an entry not an object
    [{"jsonrpc": "2.0", "id": 5, "method": "_x.ai/mcp/list", "params": {}}, update(HTTP)]])               # a batch holding one
def test_it_fails_closed_on_what_it_cannot_check(message):
    assert B.screen(message, CONNECTOR)


@pytest.mark.parametrize("raw", [b'{"jsonrpc": "2.0", "id": 1, "id": 2, "method": "x"}\n', b"\xff\xfe not utf-8\n", b"{not json\n"])
def test_a_frame_it_cannot_read_exactly_is_not_forwarded(raw):
    assert B.parse(raw) is None


AGENT = textwrap.dedent('''
    import json, sys
    for line in sys.stdin:
        frame = json.loads(line)
        print(json.dumps({"jsonrpc": "2.0", "id": frame.get("id"), "result": {"seen": frame.get("method")}}), flush=True)
    sys.exit(3)
''')


def test_the_relay_answers_a_refusal_itself_and_never_forwards_it(tmp_path):
    agent = tmp_path / "agent.py"
    agent.write_text(AGENT)
    frames = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, update(HTTP, rid=2),
              {k: v for k, v in update(SSE).items() if k != "id"}, {"jsonrpc": "2.0", "id": 4, "method": "_x.ai/mcp/list", "params": {}}]
    out = io.BytesIO()
    status = B.relay([sys.executable, str(agent)], CONNECTOR, stdin=io.BytesIO(b"".join(json.dumps(f).encode() + b"\n" for f in frames)),
                     stdout=out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert status == 3                                                       # the agent's own exit status
    assert {r["id"]: r.get("result", {}).get("seen") for r in replies if "result" in r} == {1: "initialize", 4: "_x.ai/mcp/list"}
    refused = [r for r in replies if "error" in r]
    assert [r["id"] for r in refused] == [2]                                # the notification is dropped, unanswered
    assert refused[0]["error"]["code"] == B.REFUSED and "lampway_pane" in refused[0]["error"]["message"]
    assert refused[0]["error"]["data"] == {"refused_by": "lampway_acp_boundary"}


def test_the_relay_ends_when_its_agent_exits_even_while_the_client_stays_open(tmp_path):
    import os
    import threading
    agent = tmp_path / "agent.py"
    agent.write_text("import sys\nprint('bye', flush=True)\nsys.exit(5)\n")
    read_end, write_end = os.pipe()                                          # a client that never closes its side
    out = io.BytesIO()
    done = []
    worker = threading.Thread(target=lambda: done.append(B.relay([sys.executable, str(agent)], CONNECTOR,
                                                                  stdin=os.fdopen(read_end, "rb"), stdout=out)), daemon=True)
    worker.start()
    worker.join(timeout=20)
    os.close(write_end)
    assert done == [5] and out.getvalue() == b"bye\n"


def test_sigterm_ends_the_relay_and_its_agent_without_a_client_eof(tmp_path):
    import os
    import signal
    import subprocess
    import time
    agent = tmp_path / "agent.py"
    agent.write_text("import sys, time\nprint('ready', flush=True)\ntime.sleep(60)\n")
    server = os.path.dirname(os.path.dirname(os.path.abspath(B.__file__)))
    relay = subprocess.Popen([sys.executable, "-m", "lampway_server.grok_acp_boundary", "--canonical-command", CONNECTOR, "--",
                              sys.executable, str(agent)], cwd=server, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        assert relay.stdout.readline() == b"ready\n"
        started = time.monotonic()
        relay.send_signal(signal.SIGTERM)
        assert relay.wait(timeout=10) == 128 + signal.SIGTERM           # the agent's status: ended by the forwarded signal
        assert time.monotonic() - started < 10 and relay.stdout.read() == b""
    finally:
        if relay.poll() is None:
            relay.kill()
            relay.wait()


def test_the_worker_plan_puts_the_boundary_in_front_of_the_native_agent():
    argv = G.acp_boundary_argv(CONNECTOR, ["--x"], ["bwrap", "--", "grok", "agent", "--no-leader", "stdio"])
    assert argv[:4] == [sys.executable, "-I", "-m", "lampway_server.grok_acp_boundary"]
    assert argv[argv.index("--canonical-command") + 1] == CONNECTOR and "--canonical-arg=--x" in argv
    assert argv[argv.index("--") + 1:] == ["bwrap", "--", "grok", "agent", "--no-leader", "stdio"]


def test_main_parses_the_argv_the_worker_plan_builds(monkeypatch):
    seen = {}
    monkeypatch.setattr(B, "relay", lambda agent, command, args: seen.update(agent=agent, command=command, args=args) or 0)
    argv = G.acp_boundary_argv(CONNECTOR, ["--x"], ["grok", "agent", "--no-leader", "stdio"])
    assert B.main(argv[4:]) == 0
    assert seen == {"agent": ["grok", "agent", "--no-leader", "stdio"], "command": CONNECTOR, "args": ["--x"]}
