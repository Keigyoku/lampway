# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral Lampway guidance beside the native session personality.

Native selection, pivot markers and persistence remain unchanged. Only the
already-owned Mode 1 configuration supplies this additional instruction.
"""
import functools

MODULES = frozenset({"tui_gateway.server", "tui_gateway.agent_callbacks"})


def compose(prompt, policy):
    agent = policy.config().get("agent")
    guidance = agent.get("system_prompt", "") if isinstance(agent, dict) else ""
    if not isinstance(guidance, str) or not guidance:
        return prompt
    text = prompt or ""
    if guidance in text:
        return text
    return "\n\n".join(part for part in (text, guidance) if part)


def install_module(module, policy):
    name = ("_startup_system_prompt" if module.__name__ == "tui_gateway.server"
            else "_apply_personality_to_session" if module.__name__ == "tui_gateway.agent_callbacks"
            else None)
    original = getattr(module, name, None) if name else None
    if original is None or getattr(original, "_lampway_prompt_composed", False):
        return
    # Native split-module rebinding changes function globals. Keep our owned
    # composition function in a closure so it retains its own namespace.
    composition = compose
    if name == "_startup_system_prompt":
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            return composition(original(*args, **kwargs), policy)
    else:
        @functools.wraps(original)
        def wrapped(sid, session, new_prompt, personality=""):
            # Run the native pivot first with its exact original text. No extra
            # history row, callback, personality choice or persistence write.
            result = original(sid, session, new_prompt, personality)
            if session and (agent := session.get("agent")) is not None:
                agent.ephemeral_system_prompt = composition(agent.ephemeral_system_prompt, policy) or None
            return result
    wrapped._lampway_prompt_composed = True
    setattr(module, name, wrapped)
