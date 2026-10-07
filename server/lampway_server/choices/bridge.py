# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Today's choices as Choices scopes, read in place (choices_migration.md steps 2-3, before the shim): the shipped defaults from the
registry and ``Settings()``; the Providers dialog's saved values (``provider_prefs.json``) as the global scope wherever the user has not
set a choice in Choices; the ``LAMPWAY_*`` environment as the session layer (CH4). One mapping from a settings value to a chain, so
the three agree by construction."""

import os
import time

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
    s = PP.apply_saved(Settings(), saved, env={}, choices=False)
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


# ---------------------------------------------------------------------------------------------------------------- choices -> settings
_MAIN_FIELD = {"chatgpt_plan": "chatgpt_model", "anthropic": "anthropic_model", "openrouter": "openrouter_model"}


def _apply(s: Settings, pid: str, entry: dict) -> set:
    """The settings fields one Choices entry decides; returns the fields it set."""
    oid, params = entry.get("preferred") or "", entry.get("params") or {}
    prov, _, model = oid.partition(":")
    out = set()
    if pid == "agent.main":
        provider = {"openai": "openai"}.get(prov, prov)
        if provider not in PP.MAIN_PROVIDERS:
            return out
        s.provider = provider
        out.add("provider")
        if provider in _MAIN_FIELD and model:
            setattr(s, _MAIN_FIELD[provider], model)
            out.add(_MAIN_FIELD[provider])
        if provider == "chatgpt_plan" and params.get("effort") is not None:
            s.chatgpt_effort = params["effort"]
            out.add("chatgpt_effort")
        if provider == "openai" and params.get("model"):
            s.openai_model = params["model"]
            out.add("openai_model")
        if provider == "openai" and params.get("base_url"):
            s.openai_base_url = str(params["base_url"])
            out.add("openai_base_url")
    elif pid == "agent.worker":
        if prov == "claude_cli":
            s.swarm_provider, out = "claude_cli", {"swarm_provider"}
            if params.get("model"):
                s.claude_swarm_model = params["model"]
                out.add("claude_swarm_model")
        elif prov == "openrouter" and model:
            s.swarm_provider, s.openrouter_swarm_model, out = "openrouter", model, {"swarm_provider", "openrouter_swarm_model"}
        elif prov == "chatgpt_plan" and model and s.provider == "chatgpt_plan":
            s.swarm_provider, s.chatgpt_swarm_model, out = "", model, {"swarm_provider", "chatgpt_swarm_model"}
        elif oid == "follow:agent.main":
            s.swarm_provider, out = "", {"swarm_provider"}
    elif pid.startswith("image.") and pid.split(".", 1)[1] in PP.PURPOSES:
        purpose = pid.split(".", 1)[1]
        cfg = s.image_purposes.setdefault(purpose, {})
        if prov == "openrouter" and model:
            cfg["model"] = model
            out.add("image_purposes")
            if purpose == "plates":
                s.image_backend, out = "openrouter", out | {"image_backend"}
        elif purpose == "plates" and oid in ("studio:tripo.image", "codex_cli:imagegen"):
            s.image_backend, out = ("tripo" if oid.startswith("studio") else "codex_cli"), {"image_backend"}
            fb = next((f for f in entry.get("fallbacks") or [] if f.startswith("openrouter:")), None)
            if fb:
                cfg["model"] = fb.split(":", 1)[1]
                out.add("image_purposes")
        cfg.update({k: v for k, v in params.items() if k in ("size", "resolution", "quality")})
    elif pid.startswith("video.") and pid.split(".", 1)[1] in PP.VIDEO_PURPOSES and model:
        cfg = s.video_purposes.setdefault(pid.split(".", 1)[1], {})
        cfg["model"] = ("higgsfield/" + model) if prov == "higgsfield" else model
        cfg.update({k: v for k, v in params.items() if k in ("resolution", "duration", "aspect_ratio", "image_mode")})
        out.add("video_purposes")
    return out


def apply_choices(s: Settings, env=None) -> Settings:
    """The user's Choices (``choices.json``) over the Providers dialog's values, under the environment (CH4): a purpose the environment
    decides this session is left as the environment has it. ``s.sources`` names "choices" for every field a choice set."""
    from .store import FileStore
    env = os.environ if env is None else env
    try:
        purposes = FileStore(s.state_dir).global_doc().get("purposes") or {}
    except Exception:  # noqa: BLE001 - an unreadable store is reported by Choices itself; the settings keep the dialog's values
        return s
    session = set(env_scope(env))
    for pid, entry in sorted(purposes.items()):
        if pid in session:
            continue
        for field in _apply(s, pid, entry):
            s.sources[field] = "choices"
    return s


def settings_for_option(s: Settings, oid: str, params=None) -> Settings:
    """A copy of ``s`` set as if ``oid`` were the main agent's choice: how a chat option of another purpose is built (MatGen, a judge)."""
    trial = PP.trial(s, {})
    trial.sources = dict(s.sources)
    _apply(trial, "agent.main", {"preferred": oid, "params": params or {}})
    return trial


def import_embed_defaults(library_root) -> int:
    """Steps 2 and 8 for embeddings (HC20): ``<library>/embed_defaults.json`` (``job:sensitivity -> model``, written by a registry nothing
    used) becomes the embed.<job> choices; the file is renamed ``.migrated`` once every entry is in the store or logged as unrepresentable."""
    import json as _json
    from pathlib import Path as _P
    from .. import choices as CH
    src = _P(library_root) / "embed_defaults.json"
    if not src.exists():
        return 0
    try:
        data = _json.loads(src.read_text())
    except ValueError:
        return 0
    store, done = CH.active_store(), 0
    for key, model in sorted((data or {}).items()):
        job, _, sensitivity = key.partition(":")
        pid = f"embed.{job}"
        if pid not in REG.PURPOSES or sensitivity != "private":
            continue                                          # a public pick has no scope of its own: the private default is the purpose's
        oid = model if model.startswith(("local:", "deterministic:")) else f"openrouter:{model}"
        try:
            store.set(pid, "global", None, {"preferred": oid}, by="user")
            done += 1
        except Exception as exc:  # noqa: BLE001 - logged, never silently dropped
            store._append_log({"t": time.time(), "purpose": pid, "action": "import_refused", "reason": str(exc)[:200], "by": "migration"})
    src.rename(src.with_name("embed_defaults.json.migrated"))
    return done


MODELED = {"provider", "anthropic_model", "openai_model", "chatgpt_model", "chatgpt_effort", "openrouter_model", "swarm_provider", "claude_swarm_model",
           "chatgpt_swarm_model", "chatgpt_swarm_effort", "openrouter_swarm_model", "image_backend", "image_purposes", "video_purposes"}


def save_dialog_choices(s: Settings, values: dict) -> dict:
    """Step 9: the Providers dialog's values that Choices models are written to choices.json as the user's click (the purposes they
    decide, from the settings those values give); returns the values that have no Choices home (they stay in provider_prefs.json)."""
    from .. import choices as CH
    modeled = {k: v for k, v in values.items() if k in MODELED}
    if modeled:
        trial = PP.trial(s, modeled)
        every = chains(trial)
        for pid in sorted(_touched(modeled)):
            if pid in every:
                entry = {k: every[pid][k] for k in ("preferred", "fallbacks", "params")}
                CH.active_store().set(pid, "global", None, entry, by="user")
    return {k: v for k, v in values.items() if k not in MODELED}
