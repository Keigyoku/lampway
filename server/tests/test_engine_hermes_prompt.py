# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned guidance composes after native personality without changing its pivot."""
import threading
import types
from pathlib import Path
import os
import socket
import subprocess

import pytest

from lampway_server.engine import hermes_features as F


@pytest.fixture(autouse=True)
def refuse_effects(monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("pure prompt control attempted process, network or signal")
    monkeypatch.setattr(subprocess.Popen, "__init__", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(os, "kill", refused)
    monkeypatch.setattr(os, "killpg", refused)


@pytest.fixture
def policy(tmp_path):
    (tmp_path / "config.yaml").write_text('agent:\n  system_prompt: "Lampway owned guidance"\n')
    return F.Policy(tmp_path)


def test_initial_native_personality_keeps_owned_guidance(policy):
    module = types.ModuleType("tui_gateway.server")
    module._methods = {}
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    module._spawn_side_agent = lambda *args, **kwargs: None
    module._startup_system_prompt = lambda cfg, task: "Native concise persona"
    F.install_module(module, policy)
    assert module._startup_system_prompt({}, "native-task") == (
        "Native concise persona\n\nLampway owned guidance")


@pytest.mark.parametrize("persona", ["Native clear persona", "custom persona", ""])
def test_live_native_pivot_unchanged_and_guidance_exactly_once(policy, persona):
    module = types.ModuleType("tui_gateway.agent_callbacks")
    agent = types.SimpleNamespace(ephemeral_system_prompt=None)
    session = {"agent": agent, "history": [], "history_lock": threading.RLock()}
    calls = []
    def native(sid, current, prompt, personality=""):
        calls.append((sid, prompt, personality))
        current["history"].append({"role": "user", "content": prompt,
                                   "display_kind": "personality_switch"})
        agent.ephemeral_system_prompt = prompt or None
        return False, {"personality": personality}
    module._apply_personality_to_session = native
    F.install_module(module, policy)
    F.install_module(module, policy)
    result = module._apply_personality_to_session("sid", session, persona, "chosen")
    assert result == (False, {"personality": "chosen"})
    assert calls == [("sid", persona, "chosen")]
    assert session["history"] == [{"role": "user", "content": persona,
                                    "display_kind": "personality_switch"}]
    assert agent.ephemeral_system_prompt == "\n\n".join(filter(None, [persona, "Lampway owned guidance"]))


def test_native_preloaded_skills_do_not_duplicate_guidance(policy):
    from lampway_server.engine.hermes_prompt import compose
    prompt = "Lampway owned guidance\n\nNative preloaded skills"
    assert compose(prompt, policy) == prompt


@pytest.mark.parametrize("task", ["initial-main", "resumed-main", "compressed-main", "initial-worker", "resumed-worker"])
def test_initial_lifecycle_preserves_native_resolution_and_forwarding(policy, task):
    module = types.ModuleType("tui_gateway.server")
    module._methods = {}
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    module._spawn_side_agent = lambda *args, **kwargs: None
    calls = []
    def native(cfg, task_id):
        calls.append((cfg, task_id))
        return cfg["native_prompt"]
    module._startup_system_prompt = native
    F.install_module(module, policy)
    cfg = {"native_prompt": "Native custom persona\n\nNative skills", "provider": "unchanged", "model": "pinned"}
    assert module._startup_system_prompt(cfg, task) == cfg["native_prompt"] + "\n\nLampway owned guidance"
    assert calls == [(cfg, task)]
    assert cfg == {"native_prompt": "Native custom persona\n\nNative skills", "provider": "unchanged", "model": "pinned"}


def test_live_hook_survives_native_split_module_rebinding(policy):
    path = Path(__file__).resolve().parents[2] / "third_party/hermes-agent/tui_gateway/method_ctx.py"
    context = types.ModuleType("native_pure_method_ctx")
    exec(compile(path.read_text(), str(path), "exec"), context.__dict__)
    module = types.ModuleType("tui_gateway.agent_callbacks")
    exec("def _apply_personality_to_session(sid, session, new_prompt, personality=''):\n"
         "    session['agent'].ephemeral_system_prompt = new_prompt\n"
         "    native_pivot(new_prompt)\n"
         "    return False, {'personality': personality}\n", module.__dict__)
    F.install_module(module, policy)
    pivots = []
    bound = context.rebind(module._apply_personality_to_session, {"native_pivot": pivots.append})
    agent = types.SimpleNamespace(ephemeral_system_prompt="")
    assert bound("sid", {"agent": agent}, "Native concise", "concise") == (False, {"personality": "concise"})
    assert pivots == ["Native concise"]
    assert agent.ephemeral_system_prompt == "Native concise\n\nLampway owned guidance"
