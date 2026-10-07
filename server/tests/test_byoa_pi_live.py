# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's Pi extension on a real Pi (agent-modes spec B1, the Pi row): a pane's own MCP entries reach Pi's own MCP client.

Runs only where a Pi is installed (``LAMPWAY_PI_BIN``, else ``pi`` on PATH); without one it SKIPS, and a skip is not a pass. Pi
runs in RPC mode with a throwaway HOME, no provider, ``PI_OFFLINE=1`` and no proxy: nothing can reach a model or the network. The
only command sent is ``/mcp`` (Pi's own status of its MCP servers). The Lampway server is played by a stand-in stdio MCP server
that records the binding it was started with."""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from lampway_server.herdr import harnesses as HN

PI = os.environ.get("LAMPWAY_PI_BIN") or shutil.which("pi") or ""
pytestmark = pytest.mark.skipif(not PI, reason="no Pi installed: set LAMPWAY_PI_BIN to a pi binary (npm @earendil-works/pi-coding-agent)")

STUB = '''import json, os, sys
open(os.environ["STUB_LOG"], "a").write(json.dumps({"bound": os.environ.get("LAMPWAY_BOUND_SESSION")}) + "\\n")
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if msg.get("method") == "initialize":
        res = {"protocolVersion": msg["params"].get("protocolVersion"), "capabilities": {"tools": {}}, "serverInfo": {"name": "stub", "version": "0"}}
    elif msg.get("method") == "tools/list":
        res = {"tools": [{"name": "lampway_inspect", "description": "stub", "inputSchema": {"type": "object", "properties": {}}}]}
    else:
        res = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}) + "\\n")
    sys.stdout.flush()
'''


def test_a_bound_pi_pane_reaches_lampway_through_the_extension(tmp_path):
    stub, log, home, proj = tmp_path / "stub.py", tmp_path / "stub.log", tmp_path / "home", tmp_path / "proj"
    stub.write_text(STUB)
    home.mkdir()
    proj.mkdir()
    cfg = tmp_path / "pane" / "mcp.json"
    pane = HN.PaneSpec(cwd=str(proj), session_id="1b2c3d4e-0000-4000-8000-0000000000aa", scene_session_id="scene-pi",
                       mcp_config_path=str(cfg), launcher=(sys.executable, str(stub)))
    wiring = HN.get("pi").lampway_tools(pane)
    cfg.parent.mkdir()
    for path, text in wiring.files.items():                                     # what the cockpit host writes, 0600
        with open(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), "w") as fh:
            fh.write(text.replace('"env": {', f'"env": {{"STUB_LOG": "{log}", ', 1))
    argv = HN.get("pi").launch(pane)
    node = os.path.dirname(os.environ.get("LAMPWAY_NODE") or shutil.which("node") or "/usr/bin/node")      # Pi is a Node program
    env = {"HOME": str(home), "PATH": os.pathsep.join([os.path.dirname(PI), node, os.path.dirname(sys.executable), "/usr/bin", "/bin"]),
           "PI_OFFLINE": "1", "LANG": "C.UTF-8", **wiring.env}
    p = subprocess.Popen([PI, "--mode", "rpc", *argv[1:]], cwd=proj, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        p.stdin.write(json.dumps({"id": "1", "type": "prompt", "message": "/mcp"}) + "\n")
        p.stdin.flush()
        time.sleep(6)
        p.stdin.close()
        out, err = p.communicate(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()
    notes = [json.loads(line).get("message", "") for line in out.splitlines() if line.startswith("{")]
    assert any(n.startswith("lampway: connected") for n in notes), (notes, err[-2000:])
    assert json.loads(log.read_text().splitlines()[0]) == {"bound": "scene-pi"}
