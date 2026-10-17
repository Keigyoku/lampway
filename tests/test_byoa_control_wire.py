# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island's pane controls in Your agent mode, both halves at once: what the client puts on the socket is what the server reads.

Each half had its own test and both passed while they disagreed: the client sent ``agent.byoa.interrupt`` (and resume, unbind) as
``{"session_id": ...}``, the server reads a command (``{"command_id", "payload"}``, ``agent/turns.py`` ``_command_parts``), so the
island's Stop on a real Claude Code pane answered "command_id and payload are required" and the pane kept working (real-account run
at 19967a88). Here only the socket is played: the client's own ``_control`` and ``agent_rpc`` build the frame, the server's own
``ByoaView._session_of`` reads it."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src" / "scripts", ROOT / "server"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from mixar.modules.common.agent_rpc import client as rpc  # noqa: E402
from mixar.modules.space_mixie_chat.core import byoa_view as BV  # noqa: E402
from lampway_server.agent.byoa import ByoaView  # noqa: E402

SID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def wire(monkeypatch):
    frames = []
    socket = SimpleNamespace(send_request=lambda method, params, on_result=None: frames.append((method, params, on_result)))
    monkeypatch.setattr(rpc, "get_client", lambda: socket)
    return frames


@pytest.mark.parametrize("control", [BV.stop, BV.resume, BV.unbind])
def test_each_pane_control_reaches_the_server_as_the_command_it_reads(wire, control):
    scene = SimpleNamespace(mixie_session_id=SID, name="Scene", mixie_chat_messages=[])
    assert control(scene) is True
    (method, params, _), = wire
    assert method == "agent.byoa." + control.__name__.replace("stop", "interrupt")
    assert ByoaView._session_of(params) == SID
