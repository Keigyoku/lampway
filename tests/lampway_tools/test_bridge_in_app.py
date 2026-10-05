# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The bridge as an add-on: it starts with the app, on the configured port, and a headless run
does not take the default port unless asked. These run the REAL binary."""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


CLIENT = '''
import json, socket, sys, threading, time
import bpy
mod = sys.modules["mixar.bootstrap.lampway_bridge"]
b = mod.get_bridge()
res = {"enabled": bool(b and b.enabled)}
if res["enabled"]:
    out = {}
    def ask():
        with socket.create_connection(b.address, timeout=10) as c:
            c.sendall(json.dumps({"type": "execute", "code": "bpy.ops.mesh.primitive_cube_add()\\nresult = [o.name for o in bpy.data.objects]"}).encode() + b"\\0")
            buf = b""
            while b"\\0" not in buf:
                buf += c.recv(65536)
        out["reply"] = json.loads(buf.partition(b"\\0")[0])
    t = threading.Thread(target=ask); t.start()
    for _ in range(400):
        if b.pump():
            break
        time.sleep(0.01)
    t.join()
    res["reply"] = out.get("reply")
    res["objects"] = [o.name for o in bpy.data.objects]
print("RESULT", json.dumps(res))
'''


def test_the_add_on_listens_on_the_configured_port_and_drives_the_scene():
    port = _free_port()
    run = run_script(CLIENT, env={"LAMPWAY_BRIDGE_PORT": str(port)})
    assert run.rc == 0, run.out[-2500:]
    res = run.results[0]
    assert res["enabled"] is True
    assert res["reply"]["status"] == "ok", res["reply"]
    assert "Cube" in res["reply"]["result"] and "Cube" in res["objects"]


def test_port_zero_leaves_the_bridge_off():
    run = run_script(CLIENT, env={"LAMPWAY_BRIDGE_PORT": "0"})
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"enabled": False}]


def test_a_headless_run_without_a_port_setting_does_not_take_the_default_port():
    env = {"LAMPWAY_BRIDGE_PORT": "", "BLENDER_MCP_PORT": ""}
    code = ("import sys, json\n"
            "mod = sys.modules['mixar.bootstrap.lampway_bridge']\n"
            "b = mod.get_bridge()\n"
            "print('RESULT', json.dumps({'enabled': bool(b and b.enabled)}))\n")
    run = run_script(code, env=env)
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"enabled": False}]
