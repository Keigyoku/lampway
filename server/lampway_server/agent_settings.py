"""Agent settings the client edits over HTTP: BYOK credentials and the hosted
model preference, stored locally under the state dir. The provider/model
catalogue the client's pickers show is ours (GET /agent/models)."""

import json
import os
from pathlib import Path
from typing import Optional

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


class AgentSettingsStore:
    """One JSON file, mode 0600. Keys are written here and nowhere else."""

    def __init__(self, state_dir: Path):
        self._path = Path(state_dir) / "agent_settings.json"
        self._data = {"byok": None, "preferences": {}}
        if self._path.exists():
            try:
                self._data.update(json.loads(self._path.read_text()))
            except ValueError:
                pass

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(self._data, handle)

    # ------------------------------------------------------------------ BYOK
    def credentials_view(self) -> dict:
        byok = self._data.get("byok")
        if not byok:
            return {"byok_active": False, "items": []}
        key = byok.get("api_key") or ""
        return {"byok_active": True, "items": [{
            "provider": byok["provider"], "model": byok["model"],
            "supports_vision": bool(byok.get("supports_vision", True)),
            "key_preview": f"...{key[-4:]}" if key else "",
        }]}

    def save_byok(self, provider: str, model: str, api_key: Optional[str],
                  base_url: Optional[str] = None, supports_vision: Optional[bool] = None) -> dict:
        self._data["byok"] = {
            "provider": provider, "model": model, "api_key": api_key, "base_url": base_url,
            "supports_vision": True if supports_vision is None else bool(supports_vision),
        }
        self._save()
        return self.credentials_view()

    def byok(self) -> Optional[dict]:
        return self._data.get("byok")

    def delete_byok(self) -> int:
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
