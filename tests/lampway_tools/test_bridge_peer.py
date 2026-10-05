# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Who may talk to the live bridge. The socket runs unsandboxed Python with the whole of bpy, bound to loopback with no
token (the shelf's clients send none). Loopback is not "this user": any local process may connect. So the bridge resolves
the peer's uid from the kernel's socket table (/proc/net/tcp, the loopback connection's own row) and serves only the uid
it runs as; a request it cannot attribute is refused, and so is a request bigger than the cap."""

import json
import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from mixar.modules.lampway_tools import bridge  # noqa: E402
from test_bridge import _ask, _serve_in_thread, make  # noqa: E402,F401

# /proc/net/tcp rows: a connection from port 0xC350 (50000) to the bridge on 0x2694 (9876), owned by uid 1001; an
# unrelated listener owned by 0.
TABLE = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:2694 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 11111 1 0000000000000000 100 0 0 10 0
   1: 0100007F:C350 0100007F:2694 01 00000000:00000000 00:00000000 00000000  1001        0 22222 1 0000000000000000 20 4 30 10 -1
"""


def test_the_peers_uid_is_read_from_its_own_row_of_the_socket_table():
    assert bridge.uid_from_table(TABLE, peer_port=50000, local_port=9876) == 1001


def test_a_connection_with_no_row_has_no_uid():
    assert bridge.uid_from_table(TABLE, peer_port=50001, local_port=9876) is None


def test_the_same_user_is_served(make):
    b = make()
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "result = 'served'"})
    t.join()
    assert reply == {"status": "ok", "result": "served", "stdout": "", "stderr": ""}
    assert b.refused == 0


def test_another_users_connection_is_refused_and_runs_nothing(make, monkeypatch):
    ran = []
    b = make(run=lambda code, g: ran.append(code))
    monkeypatch.setattr(bridge, "peer_uid", lambda conn, local_port: os.getuid() + 1)
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "result = 1"})
    t.join()
    assert ran == [] and reply["status"] == "error" and "refused" in reply["message"] and b.refused == 1


def test_a_connection_whose_uid_cannot_be_read_is_refused(make, monkeypatch):
    ran = []
    b = make(run=lambda code, g: ran.append(code))
    monkeypatch.setattr(bridge, "peer_uid", lambda conn, local_port: None)
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "result = 1"})
    t.join()
    assert ran == [] and reply["status"] == "error" and b.refused == 1


def test_an_oversized_request_is_refused_before_it_is_parsed(make, monkeypatch):
    ran = []
    b = make(run=lambda code, g: ran.append(code))
    monkeypatch.setattr(bridge, "MAX_REQUEST_BYTES", 64)
    t = _serve_in_thread(b)
    reply = _ask(b.port, {"type": "execute", "code": "x = '" + "a" * 200 + "'"})
    t.join()
    assert ran == [] and reply["status"] == "error" and "too large" in reply["message"]
