# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retired native tasks cannot alter a newer observed turn or its activity."""
import copy
import os
import socket
import subprocess

import pytest

from lampway_server.herdr.observers.activity import SessionActivity
from lampway_server.herdr.observers.mirror import CodexMirror


@pytest.fixture(autouse=True)
def refuse_external_effects(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("pure observer tests must not launch, connect or signal")

    monkeypatch.setattr(subprocess.Popen, "__init__", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(os, "kill", refused)
    monkeypatch.setattr(os, "killpg", refused)


def event(kind, turn_id=None, **fields):
    payload = {"type": kind, **fields}
    if turn_id is not None:
        payload["turn_id"] = turn_id
    return {"type": "event_msg", "payload": payload}


def response(kind, turn_id=None, **fields):
    payload = {"type": kind, **fields}
    if turn_id is not None:
        payload["internal_chat_message_metadata_passthrough"] = {"turn_id": turn_id}
    return {"type": "response_item", "payload": payload}


LATE_A = [
    event("task_started", "A"),
    event("task_complete", "A", last_agent_message="late A answer"),
    event("turn_aborted", "A"),
    event("user_message", "A", message="late A prompt"),
    event("agent_message", "A", message="late A text"),
    event("item_completed", "A", item={"type": "McpToolCall", "id": "call-B",
          "server": "lampway", "tool": "scene", "status": "failed"}),
    response("message", "A", role="assistant", content=[{"type": "output_text", "text": "late A raw"}]),
    response("function_call", "A", call_id="call-A", name="late_tool", arguments="{}"),
    response("function_call_output", "A", call_id="call-B", id="late-output", output={"isError": True}),
]


@pytest.mark.parametrize("late", LATE_A, ids=["restart", "complete", "abort", "user", "assistant", "item", "raw-text", "raw-call", "raw-output"])
@pytest.mark.parametrize("terminal,status", [("task_complete", "completed"), ("turn_aborted", "cancelled")])
def test_replaced_explicit_task_is_retired_before_late_records_can_touch_current_turn(late, terminal, status):
    mirror = CodexMirror("pane")
    mirror.feed(event("task_started", "A"), 0)
    mirror.feed(event("user_message", "A", message="first prompt"), 1)
    old = mirror.turn
    assert mirror.feed(event("task_started", "B"), 2) == [("end", old, {"status": "completed"})]
    mirror.feed(event("user_message", "B", message="current prompt"), 3)
    mirror.feed(event("agent_message", "B", message="current answer"), 4)
    mirror.feed(response("function_call", call_id="call-B", name="lampway__scene", arguments="{}"), 5)
    current = mirror.turn
    before = copy.deepcopy(mirror.__dict__)

    assert mirror.feed(late, 6) == []
    assert mirror.__dict__ == before
    assert mirror.turn == current and mirror._task_id == "B"

    ops = mirror.feed(event(terminal, "B", last_agent_message="current answer"), 7)
    assert [op for op in ops if op[0] == "end"] == [("end", current, {"status": status})]
    assert mirror.turn is None
    closed = copy.deepcopy(mirror.__dict__)
    assert mirror.feed(event(terminal, "B", last_agent_message="current answer"), 8) == []
    assert mirror.__dict__ == closed


@pytest.mark.parametrize("late", LATE_A[1:], ids=["complete", "abort", "user", "assistant", "item", "raw-text", "raw-call", "raw-output"])
def test_unobserved_foreign_task_records_cannot_touch_an_explicit_current_task(late):
    # Tailing can begin at B: A's start or completion need not have been observed.
    mirror = CodexMirror("pane")
    mirror.feed(event("task_started", "B"), 0)
    mirror.feed(event("user_message", "B", message="current prompt"), 1)
    mirror.feed(event("agent_message", "B", message="current answer"), 2)
    mirror.feed(response("function_call", call_id="call-B", name="lampway__scene", arguments="{}"), 3)
    current = mirror.turn
    before = copy.deepcopy(mirror.__dict__)
    assert mirror.feed(late, 4) == []
    assert mirror.__dict__ == before
    ops = mirror.feed(event("task_complete", "B", last_agent_message="current answer"), 5)
    assert [op for op in ops if op[0] == "end"] == [("end", current, {"status": "completed"})]
    assert mirror.feed(event("task_complete", "B", last_agent_message="current answer"), 6) == []


@pytest.mark.parametrize("next_event", [{"kind": "turn-started"}, {"kind": "attention", "text": "permission needed"}], ids=["working", "waiting"])
def test_duplicate_completion_preserves_new_work_or_attention_and_unread_metadata(next_event):
    activity = SessionActivity()
    activity.apply({"kind": "turn-completed", "id": "A", "preview": "first answer"})
    activity.apply(next_event)
    before = activity.to_dict()
    activity.apply({"kind": "turn-completed", "id": "A", "preview": "late duplicate"})
    assert activity.to_dict() == before
    activity.apply({"kind": "turn-completed", "id": "B", "preview": "current answer"})
    assert activity.activity == "idle"
    assert activity.completion_version == before["completion_version"] + 1
    assert activity.preview == "current answer" and activity.unread
    completed = activity.to_dict()
    activity.apply({"kind": "turn-completed", "id": "B", "preview": "echo"})
    assert activity.to_dict() == completed


def test_unidentified_raw_messages_and_tool_echoes_still_belong_to_current_explicit_task():
    mirror = CodexMirror("pane")
    mirror.feed(event("task_started", "B"), 0)
    mirror.feed(response("message", role="user", id="user-B", content=[{"type": "input_text", "text": "prompt"}]), 1)
    assert mirror.feed(event("user_message", "B", message="prompt"), 2) == []
    current = mirror.turn
    mirror.feed(response("function_call", call_id="call-B", name="lampway__scene", arguments="{}"), 3)
    assert mirror.feed(event("item_started", "B", item={"type": "McpToolCall", "id": "call-B", "server": "lampway", "tool": "scene"}), 4) == []
    mirror.feed(response("function_call_output", call_id="call-B", id="output-B", output={}), 5)
    assert mirror.feed(event("item_completed", "B", item={"type": "FunctionCallOutput", "id": "output-B", "output": {}}), 6) == []
    mirror.feed(response("message", role="assistant", id="answer-B", content=[{"type": "output_text", "text": "answer"}]), 7)
    assert mirror.feed(event("agent_message", "B", message="answer"), 8) == []
    assert mirror._texts == ["answer"]
    assert len(mirror._steps) == 1 and mirror._steps[0]["status"] == "done"
    assert mirror.feed(event("task_complete", "B", last_agent_message="answer"), 9) == [("end", current, {"status": "completed"})]


def test_records_without_task_identity_keep_legacy_completion_behavior():
    mirror = CodexMirror("pane")
    mirror.feed(event("user_message", message="prompt"), 0)
    current = mirror.turn
    mirror.feed(event("agent_message", message="answer"), 1)
    assert mirror.feed(event("task_complete", last_agent_message="answer"), 2) == [("end", current, {"status": "completed"})]
    activity = SessionActivity()
    for preview in ("first", "second"):
        activity.apply({"kind": "turn-started"})
        activity.apply({"kind": "turn-completed", "preview": preview})
        assert activity.activity == "idle" and activity.preview == preview
    assert activity.completion_version == 2
