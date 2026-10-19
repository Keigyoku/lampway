# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A motion render shows its progress in the chat's tool bubble while it runs (#10 item 6): each progress row becomes the bubble's last
step detail, emitted on the turn's stream as the swarm's progress is."""
import asyncio
import copy

from lampway_server.agent import motion_tools as MT
from lampway_server.agent.providers.base import ToolCall
from lampway_server.agent.turns import AgentHub, Turn

ROWS = [{"phase": "render", "frame": 1, "frames": 60, "elapsed_s": 0.0, "eta_s": 0.0},
        {"phase": "render", "frame": 60, "frames": 60, "elapsed_s": 5.1, "eta_s": 0.0}]


class _Stream:
    def __init__(self):
        self.payloads = []

    async def emit_quietly(self, payload):
        self.payloads.append(copy.deepcopy(payload))


def test_each_motion_progress_row_becomes_the_bubbles_step_detail(monkeypatch):
    def work(vault, root, arguments, capture, cancel, progress=None):
        for row in ROWS:
            progress(row)
        return {"ok": True}

    monkeypatch.setattr(MT, "_work", work)

    async def scenario():
        hub = AgentHub(object(), assets=object())
        stream, steps = _Stream(), [{"label": MT.NAME, "detail": ""}]
        out = await hub._run_tool(object(), hub._session("u"), Turn("u", "u-turn", ""), ToolCall("c1", MT.NAME, {"html": "x", "name": "n"}),
                                  stream=stream, bubble_id="b1", steps=steps)
        return out, stream.payloads, steps

    (text, is_error), payloads, steps = asyncio.run(scenario())
    assert is_error is False, text
    assert [p["steps"]["items"][-1]["detail"] for p in payloads] == ["render 1/60 frames, 0 s, eta 0 s", "render 60/60 frames, 5.1 s, eta 0 s"]
    assert all(p["bubble_id"] == "b1" for p in payloads)
    assert steps[-1]["detail"] == "render 60/60 frames, 5.1 s, eta 0 s"


def test_two_lines_shown_before_either_emit_runs_each_keep_their_own_detail():
    async def scenario():
        stream, steps, pending = _Stream(), [{"label": MT.NAME, "detail": ""}], []
        show = AgentHub._step_detail(stream, "b1", steps, pending)
        show("first")
        show("second")                                                  # both before the loop runs either emit
        await asyncio.gather(*pending)
        return stream.payloads

    assert [p["steps"]["items"][-1]["detail"] for p in asyncio.run(scenario())] == ["first", "second"]


def test_without_a_bubble_a_motion_render_still_runs_and_reports_nothing(monkeypatch):
    seen = []

    def work(vault, root, arguments, capture, cancel, progress=None):
        for row in ROWS:
            progress(row)
        seen.append(len(ROWS))
        return {"ok": True}

    monkeypatch.setattr(MT, "_work", work)

    async def scenario():
        hub = AgentHub(object(), assets=object())
        return await hub._run_tool(object(), hub._session("u"), Turn("u", "u-turn", ""), ToolCall("c1", MT.NAME, {"html": "x", "name": "n"}))

    text, is_error = asyncio.run(scenario())
    assert is_error is False and seen == [2], text
