"""Provider setup beyond the environment: the main agent, the swarm workers and the image backend, chosen in the Client and kept in the
state dir (``provider_prefs.json``, 0600). The environment stays the default; a saved choice wins. Credentials are never part of this:
keys stay in the environment, a key file or the sign-in stores."""

import json
import os
import re
from dataclasses import replace
from pathlib import Path

from .config import Settings

MAIN_PROVIDERS = ("mock", "anthropic", "openai", "openrouter", "chatgpt_plan", "codex_cli", "claude_cli")
SWARM_PROVIDERS = ("", "claude_cli", "openrouter")            # '' = the main provider's own swarm path (chatgpt_plan, openrouter, mock...)
EFFORTS = ("", "minimal", "low", "medium", "high", "xhigh")
IMAGE_BACKENDS = ("tripo", "codex_cli", "openrouter")
IMAGE_QUALITIES = ("", "auto", "low", "medium", "high", "xhigh", "max")
MAX_IMAGE_PIXELS = 2880 * 2880                                 # measured 2026-10-05 on GPT Image 2.5: 2880x2880 works, 3840x3840 exceeds the budget
_MODEL = re.compile(r"^[\w./:\-]{0,100}$")
_SIZE = re.compile(r"^(\d{3,5})x(\d{3,5})$")


class PrefsError(ValueError):
    pass


def _enum(choices):
    def check(v):
        if v not in choices:
            raise PrefsError(f"must be one of {[c or '(default)' for c in choices]}")
        return v
    return check


def _model(v):
    if not isinstance(v, str) or not _MODEL.match(v):
        raise PrefsError("must be a model id (letters, digits, . / : _ -)")
    return v


def check_size(v) -> str:
    """'' (the provider's default) or WIDTHxHEIGHT within the image model's pixel budget."""
    if v == "":
        return v
    m = _SIZE.match(str(v))
    if not m:
        raise PrefsError("size must be WIDTHxHEIGHT, e.g. 2880x2880 (the images API refuses '4K')")
    if int(m.group(1)) * int(m.group(2)) > MAX_IMAGE_PIXELS:
        raise PrefsError(f"size {v} exceeds the pixel budget ({MAX_IMAGE_PIXELS} px = 2880x2880; 3840x3840 was refused by the model)")
    return v


FIELDS = {
    "provider": _enum(MAIN_PROVIDERS), "anthropic_model": _model, "openai_model": _model, "chatgpt_model": _model,
    "chatgpt_effort": _enum(EFFORTS), "chatgpt_swarm_model": _model, "chatgpt_swarm_effort": _enum(EFFORTS),
    "swarm_provider": _enum(SWARM_PROVIDERS), "claude_swarm_model": _model, "openrouter_model": _model, "openrouter_swarm_model": _model,
    "image_backend": _enum(IMAGE_BACKENDS), "openrouter_image_model": _model, "openrouter_image_size": check_size,
    "openrouter_image_quality": _enum(IMAGE_QUALITIES),
}
MAIN_FIELDS = {"provider", "anthropic_model", "openai_model", "chatgpt_model", "chatgpt_effort", "openrouter_model"}


def choices() -> dict:
    return {"main_providers": list(MAIN_PROVIDERS), "swarm_providers": list(SWARM_PROVIDERS), "efforts": list(EFFORTS),
            "image_backends": list(IMAGE_BACKENDS), "image_qualities": list(IMAGE_QUALITIES), "max_image_pixels": MAX_IMAGE_PIXELS}


def _path(state_dir) -> Path:
    return Path(state_dir) / "provider_prefs.json"


def load(state_dir) -> dict:
    p = _path(state_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if k in FIELDS} if isinstance(data, dict) else {}


def save(state_dir, values: dict) -> None:
    p = _path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(values, fh, indent=1)


def validate(values: dict) -> dict:
    if not isinstance(values, dict) or not values:
        raise PrefsError("values must be an object of provider settings")
    clean = {}
    for key, value in values.items():
        if key not in FIELDS:
            raise PrefsError(f"{key!r} is not a provider setting (credentials are never set here)")
        try:
            clean[key] = FIELDS[key](value)
        except PrefsError as exc:
            raise PrefsError(f"{key}: {exc}") from None
    return clean


def apply(settings: Settings, values: dict) -> Settings:
    for key, value in values.items():
        setattr(settings, key, value)
    return settings


def trial(settings: Settings, values: dict) -> Settings:
    return apply(replace(settings), values)


def view(settings: Settings) -> dict:
    saved = load(settings.state_dir)
    return {"values": {k: getattr(settings, k) for k in FIELDS}, "source": {k: ("saved" if k in saved else "env") for k in FIELDS},
            "choices": choices()}


def effective() -> Settings:
    """The environment's settings with the saved choices on top (what imagegen and other modules read per call)."""
    s = Settings.from_env()
    return apply(s, load(s.state_dir))
