# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit F1 (2026-10-06): the MCP launcher must start OUTSIDE Blender, as an AI app starts it: the interpreter alone, isolated
(-I: no PYTHONPATH, no user site, no script directory on sys.path). A bpy import anywhere on its path kills it before the
handshake, and every AI app then sees only "connection closed"."""
import json
import os
from pathlib import Path
import subprocess
import sys

LAUNCHER = Path(__file__).resolve().parents[2] / "src/scripts/mixar/mcp.py"


def test_the_isolated_launcher_answers_initialize_without_blender(tmp_path):
    env = {**os.environ, "MIXAR_MCP_DISCOVERY_DIR": str(tmp_path / "discovery"), "LAMPWAY_MCP_DISCOVERY_DIR": str(tmp_path / "discovery")}
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "launcher-test", "version": "0"}}}
    proc = subprocess.Popen([sys.executable, "-I", str(LAUNCHER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, cwd=str(tmp_path))
    try:
        out, err = proc.communicate((json.dumps(request) + "\n").encode(), timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    lines = [line for line in out.decode(errors="replace").splitlines() if line.strip()]
    assert lines, "the launcher answered nothing; stderr:\n" + err.decode(errors="replace")[-2000:]
    reply = json.loads(lines[0])
    assert reply.get("id") == 1 and reply["result"]["serverInfo"]["name"] == "Lampway", reply
    assert "No module named 'bpy'" not in err.decode(errors="replace")
