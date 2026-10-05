"""Provider setup beyond the environment: the main agent, the swarm workers and the image backend, chosen in the Client and kept in the
state dir (``provider_prefs.json``, 0600). The environment stays the default; a saved choice wins. Credentials are never part of this:
keys stay in the environment, a key file or the sign-in stores."""

import json
import os
import re
import copy
from dataclasses import replace
from pathlib import Path

from .config import Settings

MAIN_PROVIDERS = ("mock", "anthropic", "openai", "openrouter", "chatgpt_plan", "codex_cli", "claude_cli")
SWARM_PROVIDERS = ("", "claude_cli", "openrouter")            # '' = the main provider's own swarm path (chatgpt_plan, openrouter, mock...)
EFFORTS = ("", "minimal", "low", "medium", "high", "xhigh")
IMAGE_BACKENDS = ("tripo", "codex_cli", "openrouter")
IMAGE_QUALITIES = ("", "auto", "low", "medium", "high", "xhigh", "max")
MAX_IMAGE_PIXELS = 2880 * 2880                                 # measured 2026-10-05 on GPT Image 2.5: 2880x2880 works, 3840x3840 exceeds the budget
MAX_IMAGE_EDGE = 3840                                           # ... and no edge may pass 3840 (2160x3840 is within both)
PURPOSES = ("plates", "mask", "concept", "tile")
RESOLUTIONS = ("", "1K", "2K", "4K")
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
    w, h = int(m.group(1)), int(m.group(2))
    if w * h > MAX_IMAGE_PIXELS or max(w, h) > MAX_IMAGE_EDGE:
        raise PrefsError(f"size {v} is outside the model's budget (about 8.3 MP and at most {MAX_IMAGE_EDGE} per edge: 2880x2880 and 2160x3840 work, "
                         "3840x3840 was refused)")
    return v


def check_purposes(v):
    """A partial {purpose: {model?, size?, resolution?, quality?}}: each purpose carries its own image model and size / resolution."""
    if not isinstance(v, dict) or not v:
        raise PrefsError(f"must be an object of purposes {list(PURPOSES)}")
    out = {}
    for purpose, cfg in v.items():
        if purpose not in PURPOSES:
            raise PrefsError(f"unknown purpose {purpose!r}; the purposes are {list(PURPOSES)}")
        if not isinstance(cfg, dict) or not cfg:
            raise PrefsError(f"{purpose} must be an object")
        row = {}
        for key, val in cfg.items():
            try:
                row[key] = {"model": _model, "size": check_size, "resolution": _enum(RESOLUTIONS), "quality": _enum(IMAGE_QUALITIES)}[key](val)
            except KeyError:
                raise PrefsError(f"{purpose}: {key!r} is not a setting (model, size, resolution, quality)") from None
            except PrefsError as exc:
                raise PrefsError(f"{purpose}.{key}: {exc}") from None
        out[purpose] = row
    return out


FIELDS = {
    "provider": _enum(MAIN_PROVIDERS), "anthropic_model": _model, "openai_model": _model, "chatgpt_model": _model,
    "chatgpt_effort": _enum(EFFORTS), "chatgpt_swarm_model": _model, "chatgpt_swarm_effort": _enum(EFFORTS),
    "swarm_provider": _enum(SWARM_PROVIDERS), "claude_swarm_model": _model, "openrouter_model": _model, "openrouter_swarm_model": _model,
    "image_backend": _enum(IMAGE_BACKENDS), "openrouter_image_model": _model, "openrouter_image_size": check_size,
    "openrouter_image_quality": _enum(IMAGE_QUALITIES), "image_purposes": check_purposes,
}
MAIN_FIELDS = {"provider", "anthropic_model", "openai_model", "chatgpt_model", "chatgpt_effort", "openrouter_model"}


def choices() -> dict:
    return {"main_providers": list(MAIN_PROVIDERS), "swarm_providers": list(SWARM_PROVIDERS), "efforts": list(EFFORTS),
            "image_backends": list(IMAGE_BACKENDS), "image_qualities": list(IMAGE_QUALITIES), "max_image_pixels": MAX_IMAGE_PIXELS,
            "image_purposes": list(PURPOSES), "image_resolutions": list(RESOLUTIONS)}


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


def merge_values(base: dict, values: dict) -> dict:
    """``base`` updated with ``values``; the image purposes merge per purpose and per key (a partial update keeps the rest)."""
    out = copy.deepcopy(base)
    for key, value in values.items():
        if key == "image_purposes":
            cur = out.setdefault("image_purposes", {})
            for purpose, cfg in value.items():
                cur.setdefault(purpose, {}).update(cfg)
        else:
            out[key] = value
    return out


def apply(settings: Settings, values: dict) -> Settings:
    for key, value in values.items():
        if key == "image_purposes":
            for purpose, cfg in value.items():
                settings.image_purposes.setdefault(purpose, {}).update(cfg)
        else:
            setattr(settings, key, value)
    return settings


def trial(settings: Settings, values: dict) -> Settings:
    return apply(replace(settings, image_purposes=copy.deepcopy(settings.image_purposes)), values)


def view(settings: Settings) -> dict:
    saved = load(settings.state_dir)
    return {"values": {k: copy.deepcopy(getattr(settings, k)) for k in FIELDS}, "source": {k: ("saved" if k in saved else "env") for k in FIELDS},
            "choices": choices()}


def effective() -> Settings:
    """The environment's settings with the saved choices on top (what imagegen and other modules read per call)."""
    s = Settings.from_env()
    return apply(s, load(s.state_dir))
