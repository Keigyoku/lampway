# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Agent provenance capture for generation jobs."""

from dataclasses import dataclass, field
import sys
from types import SimpleNamespace

from mixar.modules.common.agent_execution_context import (
    clear_agent_execution_context,
    set_agent_execution_context,
)
from mixar.modules.common.job_queue.core.job import Job
from mixar.modules.space_mixie_chat.core.main_thread_executor import (
    _resolve_agent_context_ids,
)


@dataclass
class PayloadJob(Job):
    payload: dict = field(default_factory=dict)


def test_job_payload_is_stamped_only_during_agent_execution(monkeypatch):
    # Some standalone suites reinstall the bpy mock during collection, so use
    # the currently registered module rather than a collection-time reference.
    bpy = sys.modules["bpy"]
    monkeypatch.setattr(
        bpy.context,
        "window_manager",
        SimpleNamespace(mixie_instance_id="instance-123"),
        raising=False,
    )
    clear_agent_execution_context()

    try:
        set_agent_execution_context("session-123", "request-456")
        agent_job = PayloadJob(payload={"prompt": "oak bark"})
    finally:
        clear_agent_execution_context()

    assert agent_job.payload["agent_context"] == {
        "source": "agent",
        "session_id": "session-123",
        "turn_id": "request-456",
        "instance_id": "instance-123",
    }

    user_job = PayloadJob(payload={"prompt": "marble"})
    assert "agent_context" not in user_job.payload


def test_explicit_agent_ctx_values_are_used_for_job_stamp(monkeypatch):
    bpy = sys.modules["bpy"]
    monkeypatch.setattr(
        bpy.context,
        "window_manager",
        SimpleNamespace(mixie_instance_id="instance-explicit"),
        raising=False,
    )
    session_id, turn_id = _resolve_agent_context_ids(
        {"chat_session_id": "chat-session", "turn_id": "chat-turn"},
        "scene-routing-session",
        "transport-request",
    )

    try:
        set_agent_execution_context(session_id, turn_id)
        job = PayloadJob(payload={})
    finally:
        clear_agent_execution_context()

    assert job.payload["agent_context"] == {
        "source": "agent",
        "session_id": "chat-session",
        "turn_id": "chat-turn",
        "instance_id": "instance-explicit",
    }


def test_absent_agent_ctx_falls_back_for_job_stamp(monkeypatch):
    bpy = sys.modules["bpy"]
    monkeypatch.setattr(
        bpy.context,
        "window_manager",
        SimpleNamespace(mixie_instance_id="instance-fallback"),
        raising=False,
    )
    session_id, turn_id = _resolve_agent_context_ids(
        None, "scene-routing-session", "transport-request"
    )

    try:
        set_agent_execution_context(session_id, turn_id)
        job = PayloadJob(payload={})
    finally:
        clear_agent_execution_context()

    assert job.payload["agent_context"] == {
        "source": "agent",
        "session_id": "scene-routing-session",
        "turn_id": "transport-request",
        "instance_id": "instance-fallback",
    }


def test_matgen_forwards_context_captured_at_construction(monkeypatch):
    from mixar.modules.paint.procedural_materials import matgen_queue

    bpy = sys.modules["bpy"]
    monkeypatch.setattr(
        bpy.context,
        "window_manager",
        SimpleNamespace(mixie_instance_id="instance-matgen"),
        raising=False,
    )
    posted = []
    workers = []
    landings = []
    monkeypatch.setattr(matgen_queue, "_in_flight", {})
    monkeypatch.setattr(matgen_queue, "_run_in_thread", workers.append)
    monkeypatch.setattr(matgen_queue, "_on_main_thread", landings.append)
    monkeypatch.setattr(matgen_queue, "_post",
                        lambda path, body: posted.append((path, body)) or {})
    try:
        set_agent_execution_context("session-matgen", "request-matgen")
        job = matgen_queue.enqueue_matgen_job(prompt="weathered copper", pipeline="fast")
    finally:
        clear_agent_execution_context()

    # The thread runs after the originating script's context has ended. A
    # different script's context must not be attributed to this queued job.
    try:
        set_agent_execution_context("other-session", "other-turn")
        workers.pop()()
    finally:
        clear_agent_execution_context()
    assert len(posted) == 1
    path, body = posted[0]
    assert path == "/api/v1/matgen"
    assert body["prompt"] == "weathered copper"
    assert body["pipeline"] == "fast"
    assert body["agent_context"] == {
        "source": "agent",
        "session_id": "session-matgen",
        "turn_id": "request-matgen",
        "instance_id": "instance-matgen",
    }
    assert job.state is matgen_queue.JobState.QUEUED
    assert len(landings) == 1


def test_user_matgen_does_not_adopt_a_later_agent_context(monkeypatch):
    from mixar.modules.paint.procedural_materials import matgen_queue

    posted, workers = [], []
    monkeypatch.setattr(matgen_queue, "_in_flight", {})
    monkeypatch.setattr(matgen_queue, "_run_in_thread", workers.append)
    monkeypatch.setattr(matgen_queue, "_on_main_thread", lambda fn: None)
    monkeypatch.setattr(matgen_queue, "_post",
                        lambda path, body: posted.append((path, body)) or {})
    clear_agent_execution_context()
    matgen_queue.enqueue_matgen_job(prompt="user material", pipeline="fast")
    try:
        set_agent_execution_context("later-session", "later-turn")
        workers.pop()()
    finally:
        clear_agent_execution_context()
    assert posted == [("/api/v1/matgen", {"prompt": "user material", "pipeline": "fast"})]


def test_transport_ids_map_to_the_routed_scenes_chat_session(monkeypatch):
    """Older backends send no chat_session_id: the request carries the
    connection id or a worker lane id. Turns and the undo-checkpoint cap are
    keyed by the scene's session, and the pump runs with the window pinned
    to the script's scene, so that scene's id is the owner."""
    from mixar.modules.common.agent_execution import pump

    bpy = sys.modules["bpy"]
    monkeypatch.setattr(bpy.context, "scene", SimpleNamespace(mixie_session_id="sess-owner"),
                        raising=False)
    assert pump.owning_chat_session("agent:conn-1") == "sess-owner"
    assert pump.owning_chat_session("agentlane:sess-owner:2") == "sess-owner"
    assert pump.owning_chat_session("") == "sess-owner"
    assert pump.owning_chat_session("sess-real") == "sess-real"
    assert pump.resolve_agent_context_ids({"turn_id": "t"}, "agent:conn-1", "r") == ("sess-owner", "t")
    assert pump.resolve_agent_context_ids(None, "agentlane:x:1", "r") == ("sess-owner", "r")

    monkeypatch.setattr(bpy.context, "scene", SimpleNamespace(mixie_session_id=""), raising=False)
    assert pump.owning_chat_session("agent:conn-1") == "agent:conn-1"
