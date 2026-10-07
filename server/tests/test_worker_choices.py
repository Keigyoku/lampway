# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Swarm workers resolve saved Choices independently of their parent's mode."""
import asyncio
from types import SimpleNamespace

import pytest

from lampway_server import choices as CH
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.choices.snapshot import World
from lampway_server.engine.wiring import provider_getter
from lampway_server.herdr.swarm_brain import WorkerBindings


@pytest.fixture
def saved_choices(monkeypatch, tmp_path):
    store = CH.MemoryStore()
    monkeypatch.setattr(CH, "_STORE", store)
    monkeypatch.setattr(CH, "_STATE", tmp_path)
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(
        connections={"chatgpt_plan": "connected"}, routes={"chatgpt_plan": True}))
    monkeypatch.delenv("LAMPWAY_SWARM_PROVIDER", raising=False)
    store.set("agent.worker", "global", None,
              {"preferred": "chatgpt_plan:gpt-6.1-sol", "params": {"effort": "medium"}}, by="user")
    return store


def test_saved_api_service_launches_hermes_even_from_a_byoa_parent(saved_choices, tmp_path):
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    context = SwarmContext(None, "scene", "turn", "call", mode="byoa", harness="codex",
                           project_root=str(tmp_path))
    brain = manager.worker_brain(context)
    assert brain.harness == "lampway_hermes"
    assert brain.choice.record()["option"] == "chatgpt_plan:gpt-6.1-sol"
    assert brain.choice.record()["scope"] == "global"
    assert brain.choice.params["effort"] == "medium"


def test_project_saved_service_and_effort_override_global_worker_choice(saved_choices, tmp_path):
    saved_choices.set("agent.worker", "project", str(tmp_path),
                      {"preferred": "chatgpt_plan:project-selected-model", "params": {"effort": "high"}}, by="user")
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    brain = manager.worker_brain(SwarmContext(None, "scene", "turn", "call", project_root=str(tmp_path)))
    assert brain.choice.record()["option"] == "chatgpt_plan:project-selected-model"
    assert brain.choice.record()["scope"] == "project"
    assert brain.choice.params["effort"] == "high"


def test_saved_worker_mode_survives_reopen_without_erasing_api_service(tmp_path, monkeypatch):
    store = CH.FileStore(tmp_path)
    store.set("agent.worker", "global", None,
              {"preferred": "chatgpt_plan:kept-api-model", "params": {"effort": "high"}}, by="user")
    original_service = store.global_doc()["purposes"]["agent.worker"]
    store.set("agent.worker_mode", "global", None, {"preferred": "byoa:codex"}, by="user")
    reopened = CH.FileStore(tmp_path)
    assert reopened.global_doc()["purposes"]["agent.worker"] == original_service
    assert original_service["preferred"] == "chatgpt_plan:kept-api-model" and original_service["params"] == {"effort": "high"}
    assert reopened.global_doc()["purposes"]["agent.worker_mode"]["preferred"] == "byoa:codex"


def test_byoa_mode_facts_never_describe_a_login_as_a_lampway_model():
    from lampway_server.choices import registry as REG
    facts = REG.option_facts("byoa:codex")
    assert facts["model"] is None and facts["connection"] is None
    assert facts["route"] == "byoa:codex" and facts["retention"] == "unknown"


def test_saved_byoa_mode_runs_from_a_mode1_parent_without_resolving_api_service(saved_choices, tmp_path, monkeypatch):
    from lampway_server import egress as EG
    from .worker_choice_support import install_worker_harness
    install_worker_harness(tmp_path, monkeypatch, "codex")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    EG.ACTIVE.set_route("byoa:codex", True)
    saved_choices.set("agent.worker_mode", "global", None, {"preferred": "byoa:codex"}, by="user")
    seen = []
    resolve = CH.resolve

    def observed(purpose, *args, **kwargs):
        seen.append(purpose)
        return resolve(purpose, *args, **kwargs)

    monkeypatch.setattr(CH, "resolve", observed)
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=None)
    brain = manager.worker_brain(SwarmContext(None, "scene", "turn", "call", mode="runtime",
                                            project_root=str(tmp_path)))
    assert brain.harness == "codex" and brain.choice is None
    assert brain.mode_choice.option == "byoa:codex" and brain.mode_choice.scope == "global"
    assert seen == ["agent.worker_mode"]


@pytest.mark.parametrize("failure", ["opt_in", "route", "installation"])
def test_byoa_refuses_before_activation_when_local_or_route_fact_is_missing(saved_choices, tmp_path, monkeypatch, failure):
    from lampway_server import egress as EG
    from .worker_choice_support import install_worker_harness
    if failure != "installation":
        install_worker_harness(tmp_path, monkeypatch, "codex")
    else:
        monkeypatch.setenv("PATH", str(tmp_path / "empty-vendor-bin"))
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "0" if failure == "opt_in" else "1")
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    strict = EG.Egress(tmp_path / "strict-egress")
    monkeypatch.setattr(EG, "ACTIVE", strict)
    if failure != "route":
        strict.set_route("byoa:codex", True)
    saved_choices.set("agent.worker_mode", "global", None, {"preferred": "byoa:codex"}, by="user")
    asked = []

    class Socket:
        async def request(self, method, params, timeout=None):
            asked.append(method)
            return {"success": True}

    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    context = SwarmContext(Socket(), "scene", "turn", "call", mode="runtime", project_root=str(tmp_path))
    text, is_error = asyncio.run(manager.call("swarm_start", {"tasks": [
        {"name": "worker", "prompt": "Inspect the scene"}]}, context))
    expected = {"opt_in": "enable Bring Your Own Agent", "route": "switch it on in Privacy", "installation": "not installed"}
    assert is_error and expected[failure] in text
    assert asked == [] and manager.swarms == {}


def test_an_agent_cannot_override_its_worker_mode(saved_choices):
    with pytest.raises(CH.NoChoice, match="must not change its own provider"):
        CH.resolve("agent.worker_mode", CH.Job(origin="agent", override="byoa:codex"))
    with pytest.raises(CH.Refused, match="must not change its own provider"):
        saved_choices.set("agent.worker_mode", "global", None,
                          {"preferred": "byoa:codex", "override_policy": "chain"}, by="user")


@pytest.mark.parametrize("harness", ["hermes", "grok"])
def test_unsupported_selected_byoa_does_not_fall_back_to_mode1(saved_choices, tmp_path, monkeypatch, harness):
    from lampway_server import egress as EG
    from .worker_choice_support import install_worker_harness
    install_worker_harness(tmp_path, monkeypatch, harness)
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    EG.ACTIVE.set_route(f"byoa:{harness}", True)
    saved_choices.set("agent.worker_mode", "global", None, {"preferred": f"byoa:{harness}"}, by="user")
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    with pytest.raises(SwarmError, match="cannot run a worker"):
        manager.worker_brain(SwarmContext(None, "scene", "turn", "call", mode="runtime"))
    assert manager.swarms == {}
    assert CH.chain("agent.worker_mode") == [f"byoa:{harness}"]


def test_only_the_users_explicit_mode_fallback_chain_can_switch_modes(saved_choices, tmp_path, monkeypatch):
    from lampway_server import egress as EG
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    EG.ACTIVE.set_route("byoa:hermes", True)
    saved_choices.set("agent.worker", "global", None, {"preferred": "mock"}, by="user")
    saved_choices.set("agent.worker_mode", "global", None,
                      {"preferred": "byoa:hermes", "fallbacks": ["local:lampway_hermes"]}, by="user")
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    brain = manager.worker_brain(SwarmContext(None, "scene", "turn", "call", mode="byoa", harness="codex"))
    assert brain.harness == "lampway_hermes" and brain.choice.option == "mock"
    assert brain.mode_choice.reason == "fallback" and brain.mode_choice.skipped[0]["option"] == "byoa:hermes"


def test_running_worker_mode_remains_pinned_after_saved_mode_changes(saved_choices, tmp_path, monkeypatch):
    from lampway_server import egress as EG
    from .worker_choice_support import install_worker_harness
    install_worker_harness(tmp_path, monkeypatch, "codex")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    EG.ACTIVE.set_route("byoa:codex", True)
    saved_choices.set("agent.worker_mode", "global", None, {"preferred": "byoa:codex"}, by="user")
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    brain = manager.worker_brain(SwarmContext(None, "scene", "turn", "call"))
    saved_choices.set("agent.worker_mode", "global", None, {"preferred": "local:lampway_hermes"}, by="user")
    assert brain.harness == "codex" and brain.mode_choice.record()["option"] == "byoa:codex" and brain.choice is None
    assert CH.preferred("agent.worker_mode") == "local:lampway_hermes"


def test_saved_worker_choice_is_checked_before_any_run_starts(saved_choices, monkeypatch, tmp_path):
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(
        connections={"chatgpt_plan": "connected"}, routes={"chatgpt_plan": False}))
    asked = []

    class Socket:
        async def request(self, method, params, timeout=None):
            asked.append(method)
            return {"success": True}

    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    context = SwarmContext(Socket(), "scene", "turn", "call", mode="byoa", harness="codex",
                           project_root=str(tmp_path))
    text, is_error = asyncio.run(manager.call("swarm_start", {"tasks": [
        {"name": "worker", "prompt": "Inspect the scene"}]}, context))
    assert is_error and "switch it on in Privacy" in text
    assert asked == [] and manager.swarms == {}


def test_gateway_uses_spawn_selection_even_after_saved_choice_changes(saved_choices, tmp_path):
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    selection = manager.worker_brain(SwarmContext(None, "scene", "turn", "call")).choice
    calls = []

    def factory(label, *, resolution=None):
        calls.append((label, resolution))
        return SimpleNamespace(name="chosen", model=resolution.model)

    async def run():
        bindings = WorkerBindings()
        job = SimpleNamespace(meta={"choice": selection})
        bindings.issue("swarm:sw1:worker-1", job)
        agent = SimpleNamespace(provider=object(), swarm_provider_factory=factory,
                                swarm=SimpleNamespace(bindings=bindings))
        get = provider_getter(agent)
        saved_choices.set("agent.worker", "global", None,
                          {"preferred": "chatgpt_plan:new-user-choice"}, by="user")
        provider = get("swarm:sw1:worker-1")
        assert provider.model == "gpt-6.1-sol"
        assert get("swarm:sw1:worker-1") is provider
        assert calls == [("worker-1", selection)]
        assert get("scene") is agent.provider
        bindings.revoke("swarm:sw1:worker-1")
        assert provider_getter(agent)("swarm:sw1:worker-1").model == "gpt-6.1-sol"
    asyncio.run(run())


def test_gateway_refuses_old_factory_instead_of_ignoring_saved_selection(saved_choices):
    selection = CH.resolve("agent.worker")
    calls = []

    async def run():
        bindings = WorkerBindings()
        bindings.issue("swarm:sw1:worker-1", SimpleNamespace(meta={"choice": selection}))
        agent = SimpleNamespace(provider=object(), swarm_provider_factory=lambda label: calls.append(label),
                                swarm=SimpleNamespace(bindings=bindings))
        with pytest.raises(ValueError, match="saved Choices resolution"):
            provider_getter(agent)("swarm:sw1:worker-1")
    asyncio.run(run())
    assert calls == []


def test_authenticated_orphan_worker_token_cannot_reselect_after_restart():
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from lampway_server.engine.gateway import Registry, gateway_routes
    from lampway_server.agent.providers.mock import ScriptedProvider
    from lampway_server.agent.providers.base import Text

    calls = []
    provider = ScriptedProvider([[Text("must not answer the orphan worker")]])
    agent = SimpleNamespace(provider=provider, swarm=SimpleNamespace(bindings=WorkerBindings()),
                            swarm_provider_factory=lambda label: calls.append(label) or provider)
    before_restart = Registry()
    worker_token = before_restart.issue_token("swarm:before-restart:worker-1")
    tokens = Registry()
    tokens.adopt_digest("swarm:before-restart:worker-1", before_restart.digest(worker_token))
    app = Starlette(routes=gateway_routes(tokens, provider_getter(agent)))
    with TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 40000)) as client:
        result = client.post("/engine/v1/chat/completions", headers={"Authorization": f"Bearer {worker_token}"},
                             json={"messages": [{"role": "user", "content": "continue"}]})
    assert result.status_code >= 400
    assert "pinned worker choice" in result.json()["error"]["message"]
    assert calls == [] and provider.requests == []


def test_resolved_factory_preserves_selected_model_effort_and_shared_auth(saved_choices, settings):
    from lampway_server.agent.providers import make_swarm_provider
    selection = CH.resolve("agent.worker")
    shared_auth = object()
    settings.provider = "mock"
    settings.chatgpt_swarm_model = "different-settings-model"
    worker = make_swarm_provider(settings, "worker-1", chatgpt_auth=shared_auth, resolution=selection)
    assert worker.name == "chatgpt_plan" and worker.model == "gpt-6.1-sol"
    assert worker.effort == "medium" and worker.auth is shared_auth
    assert worker.choice == selection.record()


def test_selected_factory_failure_never_reselects_settings_or_a_fallback(saved_choices, settings, monkeypatch):
    from lampway_server.agent import providers
    selection = CH.resolve("agent.worker")
    calls = []

    def refuse(selected, auth):
        calls.append((selected.provider, selected.chatgpt_model))
        raise ValueError("selected service cannot be built")

    monkeypatch.setattr(providers, "_make_provider", refuse)
    settings.provider = "mock"
    with pytest.raises(ValueError, match="selected service cannot be built"):
        providers.make_swarm_provider(settings, "worker-1", resolution=selection)
    assert calls == [("chatgpt_plan", "gpt-6.1-sol")]


def test_each_provider_step_has_resolution_context_and_restores_caller_context(saved_choices):
    from lampway_server import egress as EG
    from lampway_server.agent.providers import ResolvedWorkerProvider
    selection = CH.resolve("agent.worker")
    seen = []

    class Provider:
        async def stream(self, request):
            try:
                for event in ("first", "second"):
                    seen.append(dict(EG._ctx.get()))
                    yield event
            finally:
                seen.append(dict(EG._ctx.get()))

    async def run():
        with EG.context(kind="caller"):
            events = ResolvedWorkerProvider(Provider(), selection).stream(None)
            # Gateway consumes the first event before creating its SSE task.
            assert await events.__anext__() == "first"
            assert EG._ctx.get() == {"kind": "caller"}
            assert await asyncio.create_task(events.__anext__()) == "second"
            await asyncio.create_task(events.aclose())
            assert EG._ctx.get() == {"kind": "caller"}
    asyncio.run(run())
    assert len(seen) == 3
    assert all(row["option"] == selection.option and row["content_class"] == "private" for row in seen)
