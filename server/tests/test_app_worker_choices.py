# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The configured app factory must consume the worker's actual pinned selection."""
from lampway_server import choices as CH
from lampway_server.app import create_app
from lampway_server.choices.snapshot import World


def test_configured_app_worker_factory_uses_pinned_service_and_shared_auth(settings, monkeypatch):
    settings.provider = "mock"
    app = create_app(settings)
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(
        connections={"chatgpt_plan": "connected"}, routes={"chatgpt_plan": True}))
    CH.active_store().set("agent.worker", "global", None,
                          {"preferred": "chatgpt_plan:gpt-6.1-sol", "fallbacks": [],
                           "params": {"effort": "high"}}, by="user")
    selection = CH.resolve("agent.worker", CH.Job(origin="agent"))
    settings.chatgpt_swarm_model = "different-settings-model"
    settings.chatgpt_swarm_effort = "low"

    worker = app.state.agent.swarm_provider_factory("worker-1", resolution=selection)

    assert worker.name == "chatgpt_plan" and worker.model == "gpt-6.1-sol"
    assert worker.effort == "high" and worker.auth is app.state.chatgpt
    assert worker.choice == selection.record()
