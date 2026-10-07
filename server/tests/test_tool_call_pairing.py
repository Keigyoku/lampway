# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pairing invariant (docs/reports/agent-modes-spec.md R1): every assistant ``tool_call`` has exactly one ``tool_result`` before
the next model round or the end of the turn.

Before it, the loop appended the assistant's calls before running them and the results only after all of them finished, so a
cancel in between, an ``ask_user`` issued beside other calls, or a new message while a question waited left calls with no result.
The next request then carried an orphan call, which the Anthropic and OpenAI APIs refuse.
"""

import uuid

from lampway_server.agent.providers.base import Message, Text, ToolCall
from lampway_server.agent.turns import pair_tool_calls


def open_calls(messages):
    """The ids of tool calls in ``messages`` that no later tool_result answers, and results that answer nothing."""
    calls, results = [], []
    for m in messages:
        for p in m.content:
            if p.get("type") == "tool_call":
                calls.append(p["id"])
            elif p.get("type") == "tool_result":
                results.append(p["tool_call_id"])
    return [c for c in calls if results.count(c) != 1] + [r for r in results if r not in calls]


def _results(messages, call_id):
    return [p for m in messages for p in m.content if p.get("type") == "tool_result" and p["tool_call_id"] == call_id]


def test_a_cancel_during_a_tool_call_leaves_a_paired_cancelled_result(fake, provider):
    provider.script.append([ToolCall(id="c1", name="run_blender_python", arguments={"script": "import time"})])
    provider.script.append([Text("Fine.")])
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id = str(uuid.uuid4())
        first = fake.command(ws, "chat", fake.chat_payload("do something slow", session_id))
        frames = []
        while not frames or frames[-1].get("method") != "blender.execute_script":
            frames.append(ws.receive_json())
        fake.command(ws, "cancel", {"session_id": session_id})
        while not any(f.get("method") == "agent.turn.ended" and f["params"].get("turn_id") == first for f in frames):
            frames.append(ws.receive_json())
        second = fake.command(ws, "chat", fake.chat_payload("something else", session_id))
        fake.run_turn(ws, second, on_script=lambda p: {"success": True})
    sent = provider.requests[-1].messages
    assert open_calls(sent) == [], [m.content for m in sent]
    (result,) = _results(sent, "c1")
    assert result["is_error"] and "cancelled" in result["content"]


def test_ask_user_beside_another_call_answers_both(fake, provider):
    provider.script = [
        [ToolCall(id="t1", name="run_blender_python", arguments={"script": "x = 1"}),
         ToolCall(id="q1", name="ask_user", arguments={"question": "Round or square?", "options": ["Round", "Square"]})],
        [Text("Round it is.")],
    ]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("make a table", "pair-ask"))
        frames = fake.run_turn(ws, cmd, on_script=lambda p: {"success": True})
        question = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"
                    and f["params"]["event"].get("interrupt_id")][-1]
        answer = fake.command(ws, "input", {"session_id": "pair-ask", "action": "respond", "text": "Round", "answers": ["Round"],
                                             "interrupt_id": question["interrupt_id"]})
        fake.run_turn(ws, answer, on_script=lambda p: {"success": True})
    sent = provider.requests[-1].messages
    assert open_calls(sent) == [], [m.content for m in sent]
    assert _results(sent, "q1")[0]["content"] == "Round"
    # Both results ride in ONE message right after the assistant's calls, as the providers' APIs require.
    calls_at = next(i for i, m in enumerate(sent) if any(p.get("id") == "q1" for p in m.content if p.get("type") == "tool_call"))
    assert {p["tool_call_id"] for p in sent[calls_at + 1].content} == {"t1", "q1"}


def test_a_new_message_while_a_question_waits_closes_the_question(fake, provider):
    provider.script = [
        [ToolCall(id="q1", name="ask_user", arguments={"question": "Round or square?", "options": ["Round", "Square"]})],
        [Text("Forget the table, then.")],
        [Text("plain")],
    ]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cmd = fake.command(ws, "chat", fake.chat_payload("make a table", "pair-new"))
        frames = fake.run_turn(ws, cmd, on_script=lambda p: {"success": True})
        question = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"
                    and f["params"]["event"].get("interrupt_id")][-1]
        moved_on = fake.command(ws, "chat", fake.chat_payload("actually make a lamp", "pair-new"))
        fake.run_turn(ws, moved_on, on_script=lambda p: {"success": True})
        # The old question is closed: answering it now is a plain message, not a second result for q1.
        late = fake.command(ws, "input", {"session_id": "pair-new", "action": "respond", "text": "Round",
                                           "interrupt_id": question["interrupt_id"]})
        fake.run_turn(ws, late, on_script=lambda p: {"success": True})
    after_new = provider.requests[1].messages
    assert open_calls(after_new) == [], [m.content for m in after_new]
    assert after_new[-1].text() == "actually make a lamp"
    final = provider.requests[-1].messages
    assert open_calls(final) == [] and final[-1].text() == "Round"


def test_an_old_history_with_an_orphan_call_is_repaired():
    history = [
        Message.user_text("make a table"),
        Message("assistant", [{"type": "tool_call", "id": "a", "name": "run_blender_python", "arguments": {}},
                              {"type": "tool_call", "id": "b", "name": "run_blender_python", "arguments": {}}]),
        Message("user", [{"type": "tool_result", "tool_call_id": "a", "content": "ok", "is_error": False}]),
        Message("assistant", [{"type": "tool_call", "id": "c", "name": "run_blender_python", "arguments": {}}]),
        Message.user_text("hello?"),
    ]
    assert pair_tool_calls(history, "repaired") == 2
    assert open_calls(history) == []
    assert [p["tool_call_id"] for p in history[2].content] == ["a", "b"]
    assert history[4].content[0]["tool_call_id"] == "c" and history[5].text() == "hello?"
    assert pair_tool_calls(history, "repaired") == 0
