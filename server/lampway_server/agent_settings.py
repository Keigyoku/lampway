"""Agent settings the client edits over HTTP: BYOK credentials and the hosted
model preference, stored locally under the state dir. The provider/model
catalogue the client's pickers show is ours (GET /agent/models)."""

import logging
from pathlib import Path
from typing import Optional

from .connections import files as CF

ANTHROPIC_MODELS = [
    ("claude-sonnet-5-5", "Claude Sonnet 5.5"),
    ("claude-opus-5-5", "Claude Opus 5.5"),
    ("claude-haiku-4-5", "Claude Haiku 4.5"),
]


def models_catalog(settings) -> dict:
    """The {providers:[...]} payload of GET /agent/models (models_cache.py:166-168,
    model fields per protocol.json agent.models)."""

    def model(model_id, label):
        return {
            "id": model_id, "label": label, "platform_available": True, "byok_available": True,
            "supports_vision": True, "min_tier": "free", "eligible": True, "thinking_levels": [],
        }

    openai_models = [model(settings.openai_model, settings.openai_model)] if settings.openai_model else []
    providers = [
        {"id": "anthropic", "label": "Anthropic", "models": [model(i, l) for i, l in ANTHROPIC_MODELS]},
        {"id": "openai", "label": "OpenAI-compatible", "models": openai_models},
    ]
    if settings.provider == "mock":
        providers.append({"id": "mock", "label": "Mock (no model)", "models": [model("mock", "Mock")]})
    return {"providers": providers}


def known_models(settings) -> set:
    return {(p["id"], m["id"]) for p in models_catalog(settings)["providers"] for m in p["models"]}


BYOK_CONNECTIONS = {"anthropic": "anthropic", "openai": "custom_llm", "openai_compatible": "custom_llm", "local": "custom_llm",
                    "openrouter": "openrouter"}

#: Providers whose endpoint is the user's own OpenAI-compatible server (llama.cpp, Ollama, vLLM, LM Studio...). ``local`` is what
#: the client's local-models form sends; it is the same kind of provider (agent-modes spec R0).
BARE_ENDPOINTS = ("openai", "openai_compatible", "local")


def byok_choice(provider: str, model: str, base_url: Optional[str], default_base_url: str) -> Optional[dict]:
    """The Choices entry for agent.main that a BYOK save means (spec R0: the dialog drives the provider), or None for a provider
    the main agent cannot run on."""
    if provider == "anthropic":
        return {"preferred": f"anthropic:{model}"}
    if provider == "openrouter":
        return {"preferred": f"openrouter:{model}"}
    if provider in BARE_ENDPOINTS:
        return {"preferred": "openai:local", "params": {"model": model, "base_url": (base_url or default_base_url).rstrip("/")}}
    return None


class AgentSettingsStore:
    """One JSON file, mode 0600: the hosted model preference and the BYOK choice. A BYOK key lives in Connections, never here."""

    def __init__(self, state_dir: Path):
        self._path = Path(state_dir) / "agent_settings.json"
        self._data = {"byok": None, "preferences": {}}
        try:
            self._data.update(CF.read_json(self._path))
        except CF.Unreadable as exc:                 # set aside, never emptied: the user's file survives as <name>.corrupt-<time>
            logging.getLogger("lampway.settings").warning("%s", exc)

    def _save(self):
        CF.atomic_write_json(self._path, self._data)          # a crash mid-write keeps the old file (finding F5)

    # ------------------------------------------------------------------ BYOK
    # C5: BYOK only writes into Connections. The key becomes the manual source of the matching connection; this file keeps the choice
    # ({provider, model, base_url, supports_vision}) and where the key went, never the key (finding F3).
    def _hub(self):
        from . import connections as C
        return C.active()

    def credentials_view(self) -> dict:
        byok = self._data.get("byok")
        if not byok:
            return {"byok_active": False, "items": []}
        key, preview = byok.get("api_key") or "", ""
        if key:                                                   # a key not yet moved (an older file whose move failed)
            preview = f"...{key[-4:]}"
        elif byok.get("connection"):
            fp = self._hub().held_fingerprint(byok["connection"]) or {}
            preview = f"...{fp['last4']}" if fp.get("last4") else ""
        return {"byok_active": True, "items": [{
            "provider": byok["provider"], "model": byok["model"],
            "supports_vision": bool(byok.get("supports_vision", True)),
            "key_preview": preview,
        }]}

    def save_byok(self, provider: str, model: str, api_key: Optional[str],
                  base_url: Optional[str] = None, supports_vision: Optional[bool] = None) -> dict:
        from . import connections as C
        cid = BYOK_CONNECTIONS.get(provider)
        if api_key:
            if cid is None:
                raise C.Refused(f"Lampway has no connection for provider {provider!r}: BYOK keys go to {', '.join(sorted(BYOK_CONNECTIONS))}", 422)
            self._hub().put_secret(cid, {"key": api_key}, by="user")
        self._data["byok"] = {"provider": provider, "model": model, "base_url": base_url,
                              "supports_vision": True if supports_vision is None else bool(supports_vision),
                              "stored_in": "connections", "connection": cid}
        self._save()
        return self.credentials_view()

    def migrate_into_connections(self) -> Optional[str]:
        """An older plain key moves into Connections once; it leaves this file only after the store gives it back. Returns the
        reason it could not move, or None."""
        from . import connections as C
        byok = self._data.get("byok") or {}
        key, cid = byok.get("api_key"), BYOK_CONNECTIONS.get(byok.get("provider"))
        if not key:
            return None
        hub = self._hub()
        try:
            if cid is None:
                raise C.Refused(f"provider {byok.get('provider')!r} has no connection")
            hub.put_secret(cid, {"key": key}, by="user")
            if hub.store().get(cid, "key") != key:
                raise C.Refused("the store did not give the key back")
        except Exception as exc:  # noqa: BLE001 - any failure keeps the key where it was; the row says why
            reason = str(exc) if isinstance(exc, C.Refused) else type(exc).__name__
            hub.note("byok_legacy", "move_error", reason)
            return reason
        byok.pop("api_key", None)
        byok.update(stored_in="connections", connection=cid)
        self._save()
        hub.note("byok_legacy", "move_error", None)
        hub._log(cid, "byok-moved", "system", True, "the BYOK key moved from agent_settings.json into Connections")
        return None

    def byok(self) -> Optional[dict]:
        return self._data.get("byok")

    def delete_byok(self) -> int:
        from . import connections as C
        byok = self._data.get("byok") or {}
        if byok.get("connection") and byok.get("stored_in") == "connections":
            try:
                self._hub().forget(byok["connection"], "manual", by="user")
            except C.Refused:
                pass
        removed = 1 if self._data.get("byok") else 0
        self._data["byok"] = None
        self._save()
        return removed

    # -------------------------------------------------------------- preference
    def preference_view(self) -> dict:
        items = [{"role": role, **pick} for role, pick in self._data["preferences"].items()]
        return {"byok_active": bool(self._data.get("byok")), "items": items}

    def save_preference(self, role: str, provider: str, model: str, label: str,
                        thinking_level: Optional[str]) -> dict:
        self._data["preferences"][role] = {
            "provider": provider, "model": model, "label": label,
            "thinking_level": thinking_level, "eligible": True,
        }
        self._save()
        return self.preference_view()

    def delete_preference(self, role: str) -> bool:
        existed = self._data["preferences"].pop(role, None) is not None
        self._save()
        return existed

    def delete_all_preferences(self) -> int:
        count = len(self._data["preferences"])
        self._data["preferences"] = {}
        self._save()
        return count
