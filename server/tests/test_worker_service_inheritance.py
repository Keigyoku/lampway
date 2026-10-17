# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The worker service follows the parent until the user changes the worker choice."""
import pytest

from lampway_server import choices as CH
from lampway_server import provider_prefs as PP
from lampway_server.choices import bridge as B
from lampway_server.choices import resolver as R
from lampway_server.choices.snapshot import World
from lampway_server.config import Settings


@pytest.fixture
def state(tmp_path, monkeypatch):
    for name in PP.ENV_VARS.values():
        monkeypatch.delenv(name, raising=False)
    CH.set_active(CH.FileStore(tmp_path), tmp_path)
    yield tmp_path
    CH.set_active(None, None)


def resolve(doc):
    world = World(connections={"openrouter": "connected", "chatgpt_plan": "connected"},
                  routes={"openrouter": True, "chatgpt_plan": True})
    return R.resolve("agent.worker", R.Job(), world, doc)


PARENTS = (
    {"provider": "openrouter", "openrouter_model": "parent-model"},
    {"provider": "chatgpt_plan", "chatgpt_model": "parent-model", "chatgpt_effort": "high"},
)


@pytest.mark.parametrize("provider", ("mock", "openrouter", "chatgpt_plan", "anthropic", "openai"))
def test_unset_worker_settings_follow_the_complete_parent_choice(provider):
    assert B.chains(Settings(provider=provider), env={})["agent.worker"] == {
        "preferred": "follow:agent.main", "fallbacks": [], "params": {}}


@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize("scope", ("prefs", "env", "dialog"))
def test_parent_only_changes_leave_the_worker_implicit(state, parent, scope):
    settings = Settings(state_dir=state)
    if scope == "prefs":
        PP.save(state, parent)
        assert "agent.worker" not in B.providers_scope(state)
        doc = CH.document(env={})
    elif scope == "env":
        env = {PP.ENV_VARS[k]: v for k, v in parent.items()}
        assert "agent.worker" not in B.env_scope(env)
        doc = CH.document(env=env)
    else:
        B.save_dialog_choices(settings, parent)
        assert "agent.worker" not in CH.active_store().global_doc().get("purposes", {})
        doc = CH.document(env={})
    worker = resolve(doc)
    main = R.resolve("agent.main", R.Job(), World(
        connections={"openrouter": "connected", "chatgpt_plan": "connected"},
        routes={"openrouter": True, "chatgpt_plan": True}), doc)
    assert (worker.option, worker.params) == (main.option, main.params)
    assert worker.followed == "agent.main"


@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize("scope", ("prefs", "env", "dialog"))
def test_parent_only_changes_preserve_a_saved_worker_service(state, parent, scope):
    CH.active_store().set("agent.worker", "global", None,
                          {"preferred": "chatgpt_plan:worker-model", "params": {"effort": "medium"}}, by="user")
    if scope == "prefs":
        PP.save(state, parent)
        doc = CH.document(env={})
    elif scope == "env":
        doc = CH.document(env={PP.ENV_VARS[k]: v for k, v in parent.items()})
    else:
        B.save_dialog_choices(Settings(state_dir=state), parent)
        doc = CH.document(env={})
    worker = resolve(doc)
    assert (worker.option, worker.params, worker.followed) == (
        "chatgpt_plan:worker-model", {"effort": "medium"}, None)


@pytest.mark.parametrize("scope", ("prefs", "env", "dialog"))
@pytest.mark.parametrize("values,expected,params", (
    ({"swarm_provider": "openrouter", "openrouter_swarm_model": "worker-model"}, "openrouter:worker-model", {}),
    ({"openrouter_swarm_model": "worker-model"}, "openrouter:worker-model", {}),
    ({"chatgpt_swarm_model": "worker-model", "chatgpt_swarm_effort": "medium"},
     "chatgpt_plan:worker-model", {"effort": "medium"}),
))
def test_explicit_worker_fields_select_the_worker_service(state, scope, values, expected, params):
    # Parent mock makes accidental derivation from the parent's provider fail.
    if scope == "prefs":
        PP.save(state, values)
        entry = B.providers_scope(state)["agent.worker"]
    elif scope == "env":
        entry = B.env_scope({PP.ENV_VARS[k]: v for k, v in values.items()})["agent.worker"]
    else:
        B.save_dialog_choices(Settings(state_dir=state), values)
        entry = CH.active_store().global_doc()["purposes"]["agent.worker"]
    assert entry["preferred"] == expected and entry["params"] == params


def test_explicit_follow_and_spawn_snapshot_keep_their_meaning(state):
    CH.active_store().set("agent.worker", "global", None, {"preferred": "follow:agent.main"}, by="user")
    B.save_dialog_choices(Settings(state_dir=state), PARENTS[1])
    pinned = resolve(CH.document(env={}))
    B.save_dialog_choices(Settings(state_dir=state), {"provider": "openrouter", "openrouter_model": "later-parent"})
    later = resolve(CH.document(env={}))
    assert pinned.option == "chatgpt_plan:parent-model" and pinned.params == {"effort": "high"}
    assert later.option == "openrouter:later-parent" and later.params == {}
    assert pinned.followed == later.followed == "agent.main"


def test_empty_worker_provider_restores_implicit_follow(state):
    B.save_dialog_choices(Settings(state_dir=state, provider="openrouter"), {"swarm_provider": ""})
    assert CH.active_store().global_doc()["purposes"]["agent.worker"]["preferred"] == "follow:agent.main"
