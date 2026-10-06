# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Today's choices as Choices scopes, read in place (choices_migration.md steps 2-3, before the shim): the shipped defaults from the
registry and ``Settings()``; the Providers dialog's saved values (``provider_prefs.json``) as the global scope wherever the user has not
set a choice in Choices; the ``LAMPWAY_*`` environment as the session layer (CH4). One mapping from a settings value to a chain, so
the three agree by construction."""

import os

from .. import provider_prefs as PP
from ..config import Settings
from . import registry as REG

_MAIN_MODEL = {"chatgpt_plan": "chatgpt_model", "anthropic": "anthropic_model", "openrouter": "openrouter_model"}
_FIELDS = {
    "agent.main": {"provider", "anthropic_model", "openai_model", "chatgpt_model", "chatgpt_effort", "openrouter_model"},
    "agent.worker": {"provider", "swarm_provider", "claude_swarm_model", "chatgpt_swarm_model", "chatgpt_swarm_effort", "openrouter_swarm_model"},
    "image.plates": {"image_backend", "image_purposes"},
}
_EXTRA_ENV = {"agent.main": ("LAMPWAY_CODEX_MODEL", "LAMPWAY_CLAUDE_MODEL", "LAMPWAY_CODEX_EFFORT"), "agent.dictation": ("LAMPWAY_OPENROUTER_STT_MODEL",)}


def _entry(preferred, fallbacks=(), params=None, source=None) -> dict:
    e = {"preferred": preferred, "fallbacks": [f for f in fallbacks if f and f != preferred],
         "params": {k: v for k, v in (params or {}).items() if v not in ("", None)}}
    if source:
        e["source"] = source
    return e


def _video_option(slug: str) -> str:
    return "higgsfield:" + slug.split("/", 1)[1] if slug.startswith("higgsfield/") else "openrouter:" + slug


def chains(s: Settings, env=None) -> dict:
    """{purpose: entry} for every purpose a settings value decides."""
    env = os.environ if env is None else env
    out = {}
    prov = s.provider
    if prov in _MAIN_MODEL:
        out["agent.main"] = _entry(f"{prov}:{getattr(s, _MAIN_MODEL[prov])}", params={"effort": s.chatgpt_effort} if prov == "chatgpt_plan" else None)
    elif prov == "openai":
        out["agent.main"] = _entry("openai:local", params={"model": s.openai_model, "base_url": s.openai_base_url})
    elif prov in ("codex_cli", "codex_app_server"):
        out["agent.main"] = _entry(prov, params={"model": env.get("LAMPWAY_CODEX_MODEL", ""), "effort": env.get("LAMPWAY_CODEX_EFFORT", "")})
    elif prov == "claude_cli":
        out["agent.main"] = _entry("claude_cli", params={"model": env.get("LAMPWAY_CLAUDE_MODEL", "")})
    else:
        out["agent.main"] = _entry("mock")
    kind = s.swarm_provider or prov
    if kind == "claude_cli":
        out["agent.worker"] = _entry("claude_cli", params={"model": s.claude_swarm_model})
    elif kind == "openrouter":
        out["agent.worker"] = _entry(f"openrouter:{s.openrouter_swarm_model}")
    elif kind == "chatgpt_plan":
        out["agent.worker"] = _entry(f"chatgpt_plan:{s.chatgpt_swarm_model}", params={"effort": s.chatgpt_swarm_effort})
    else:
        out["agent.worker"] = _entry("follow:agent.main")
    for purpose, cfg in s.image_purposes.items():
        model = f"openrouter:{cfg.get('model')}"
        params = {k: v for k, v in cfg.items() if k != "model"}
        pid = f"image.{purpose}"
        if pid not in REG.PURPOSES:
            continue
        if purpose == "plates" and s.image_backend == "tripo":
            out[pid] = _entry("studio:tripo.image", [model], params)
        elif purpose == "plates" and s.image_backend == "codex_cli":
            out[pid] = _entry("codex_cli:imagegen", [model], params)
        else:
            out[pid] = _entry(model, params=params)
    for purpose, cfg in s.video_purposes.items():
        pid = f"video.{purpose}"
        if pid in REG.PURPOSES and cfg.get("model"):
            out[pid] = _entry(_video_option(cfg["model"]), params={k: v for k, v in cfg.items() if k != "model"})
    out["agent.dictation"] = _entry(f"openrouter:{s.openrouter_stt_model}")
    return out


def _touched(keys) -> set:
    """The purposes a set of settings keys decides."""
    out = set()
    for key in keys:
        for pid, fields in _FIELDS.items():
            if key in fields:
                out.add(pid)
        if key == "image_purposes":
            out.update(f"image.{p}" for p in PP.PURPOSES)
        if key == "video_purposes":
            out.update(f"video.{p}" for p in PP.VIDEO_PURPOSES)
    return out


def shipped() -> dict:
    out = {p.id: _entry(p.default[0], p.default[1:], p.params) for p in REG.PURPOSES.values() if p.default}
    out.update(chains(Settings(), env={}))
    return out


def providers_scope(state_dir) -> dict:
    """The Providers dialog's saved values, as the global scope of the purposes they decide."""
    saved = PP.load(state_dir)
    if not saved:
        return {}
    s = PP.apply_saved(Settings(), saved, env={})
    every = chains(s, env={})
    return {pid: {**every[pid], "source": "providers"} for pid in _touched(saved) if pid in every}


def env_scope(env=None) -> dict:
    """The session layer: the purposes the environment decides, each naming the variables that decide it."""
    env = os.environ if env is None else env
    set_keys = {k for k, var in PP.ENV_VARS.items() if var in env}
    touched = _touched(set_keys)
    for pid, names in _EXTRA_ENV.items():
        if any(n in env for n in names):
            touched.add(pid)
    if not touched:
        return {}
    every = chains(Settings.from_env(env), env=env)
    out = {}
    for pid in touched:
        if pid in every:
            names = sorted({PP.ENV_VARS[k] for k in set_keys if pid in _touched({k})} | {n for n in _EXTRA_ENV.get(pid, ()) if n in env})
            out[pid] = {**every[pid], "source": ", ".join(names)}
    return out
