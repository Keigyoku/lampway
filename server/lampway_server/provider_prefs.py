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
VIDEO_PURPOSES = ("bulk", "loop", "motion", "edit", "upscale")
IMAGE_MODES = ("first_frame", "first_last_frame", "reference")
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


def _pos_int(v):
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 60:
        raise PrefsError("must be a whole number of seconds from 1 to 60")
    return v


def _usd_cap(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 100:
        raise PrefsError("must be a dollar amount above 0 and at most 100")
    return float(v)


def _resolution_text(v):
    if not isinstance(v, str) or not re.match(r"^(\d{3,4}p|[124]K)?$", v):
        raise PrefsError("must look like 720p or 2K")
    return v


def _aspect(v):
    if not isinstance(v, str) or not re.match(r"^(\d{1,2}:\d{1,2})?$", v):
        raise PrefsError("must look like 16:9")
    return v


def check_video_purposes(v):
    """A partial {purpose: {model?, resolution?, duration?, aspect_ratio?, image_mode?}} for bulk / loop / motion."""
    if not isinstance(v, dict) or not v:
        raise PrefsError(f"must be an object of purposes {list(VIDEO_PURPOSES)}")
    checks = {"model": _model, "resolution": _resolution_text, "duration": _pos_int, "aspect_ratio": _aspect, "image_mode": _enum(IMAGE_MODES)}
    out = {}
    for purpose, cfg in v.items():
        if purpose not in VIDEO_PURPOSES:
            raise PrefsError(f"unknown purpose {purpose!r}; the purposes are {list(VIDEO_PURPOSES)}")
        if not isinstance(cfg, dict) or not cfg:
            raise PrefsError(f"{purpose} must be an object")
        row = {}
        for key, val in cfg.items():
            if key not in checks:
                raise PrefsError(f"{purpose}: {key!r} is not a setting ({', '.join(checks)})")
            try:
                row[key] = checks[key](val)
            except PrefsError as exc:
                raise PrefsError(f"{purpose}.{key}: {exc}") from None
        out[purpose] = row
    return out


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


def check_spend_policy(v):
    """A partial {provider: {click?, above?, job_cap?, session_cap?}} for openrouter / higgsfield / studios / hyper3d (amounts in the provider's unit: USD, else credits)."""
    from .spendpolicy import CLICKS, PROVIDERS
    if not isinstance(v, dict) or not v:
        raise PrefsError(f"must be an object of providers {list(PROVIDERS)}")
    out = {}
    for provider, cfg in v.items():
        if provider not in PROVIDERS:
            raise PrefsError(f"unknown provider {provider!r}; the providers are {list(PROVIDERS)}")
        if not isinstance(cfg, dict) or not cfg:
            raise PrefsError(f"{provider} must be an object")
        row = {}
        for key, val in cfg.items():
            if key == "click":
                row[key] = _enum(CLICKS)(val)
            elif key in ("above", "job_cap", "session_cap"):
                if val is None and key != "above":
                    row[key] = None
                elif isinstance(val, bool) or not isinstance(val, (int, float)) or not 0 <= val <= 1_000_000:
                    raise PrefsError(f"{provider}.{key}: must be an amount from 0 to 1000000")
                else:
                    row[key] = float(val)
            else:
                raise PrefsError(f"{provider}: {key!r} is not a setting (click, above, job_cap, session_cap)")
        if row.get("click") == "above" and "above" not in row:
            raise PrefsError(f"{provider}: click above needs `above`, the price over which the user's click is needed")
        out[provider] = row
    return out


FIELDS = {
    "provider": _enum(MAIN_PROVIDERS), "anthropic_model": _model, "openai_model": _model, "chatgpt_model": _model,
    "chatgpt_effort": _enum(EFFORTS), "chatgpt_swarm_model": _model, "chatgpt_swarm_effort": _enum(EFFORTS),
    "swarm_provider": _enum(SWARM_PROVIDERS), "claude_swarm_model": _model, "openrouter_model": _model, "openrouter_swarm_model": _model,
    "image_backend": _enum(IMAGE_BACKENDS), "openrouter_image_model": _model, "openrouter_image_size": check_size,
    "openrouter_image_quality": _enum(IMAGE_QUALITIES), "image_purposes": check_purposes,
    "video_purposes": check_video_purposes, "video_max_job_usd": _usd_cap, "spend_policy": check_spend_policy,
}
MAIN_FIELDS = {"provider", "anthropic_model", "openai_model", "chatgpt_model", "chatgpt_effort", "openrouter_model"}


def choices() -> dict:
    return {"main_providers": list(MAIN_PROVIDERS), "swarm_providers": list(SWARM_PROVIDERS), "efforts": list(EFFORTS),
            "image_backends": list(IMAGE_BACKENDS), "image_qualities": list(IMAGE_QUALITIES), "max_image_pixels": MAX_IMAGE_PIXELS,
            "image_purposes": list(PURPOSES), "image_resolutions": list(RESOLUTIONS), "video_purposes": list(VIDEO_PURPOSES),
            "video_image_modes": list(IMAGE_MODES)}


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
        if key in ("image_purposes", "video_purposes", "spend_policy"):
            cur = out.setdefault(key, {})
            for purpose, cfg in value.items():
                cur.setdefault(purpose, {}).update(cfg)
        else:
            out[key] = value
    return out


# The environment variable each setting can be given for a session (Settings.from_env reads the same names). PRECEDENCE, one rule everywhere:
# an explicit call argument > the environment for a session > the saved Providers-dialog choices > the defaults.
ENV_VARS = {"provider": "LAMPWAY_PROVIDER", "anthropic_model": "LAMPWAY_ANTHROPIC_MODEL", "openai_model": "LAMPWAY_OPENAI_MODEL",
            "chatgpt_model": "LAMPWAY_CHATGPT_MODEL", "chatgpt_effort": "LAMPWAY_CHATGPT_EFFORT", "chatgpt_swarm_model": "LAMPWAY_CHATGPT_SWARM_MODEL",
            "chatgpt_swarm_effort": "LAMPWAY_CHATGPT_SWARM_EFFORT", "swarm_provider": "LAMPWAY_SWARM_PROVIDER", "claude_swarm_model": "LAMPWAY_CLAUDE_SWARM_MODEL",
            "openrouter_model": "LAMPWAY_OPENROUTER_MODEL", "openrouter_swarm_model": "LAMPWAY_OPENROUTER_SWARM_MODEL", "image_backend": "LAMPWAY_IMAGE_BACKEND",
            "openrouter_image_model": "LAMPWAY_OPENROUTER_IMAGE_MODEL", "openrouter_image_size": "LAMPWAY_OPENROUTER_IMAGE_SIZE",
            "openrouter_image_quality": "LAMPWAY_OPENROUTER_IMAGE_QUALITY"}


def apply_saved(settings: Settings, saved: dict, env=None) -> Settings:
    """The saved choices UNDER the environment: a field the environment sets is left as the environment has it. ``settings.sources`` records, per field, whether
    the value in force is env, saved or default."""
    env = os.environ if env is None else env
    sources = {k: ("env" if k in ENV_VARS and ENV_VARS[k] in env else "default") for k in FIELDS}
    for key, value in saved.items():
        if sources.get(key) == "env":
            continue
        if key in ("image_purposes", "video_purposes", "spend_policy"):
            for purpose, cfg in value.items():
                getattr(settings, key).setdefault(purpose, {}).update(cfg)
        else:
            setattr(settings, key, value)
        sources[key] = "saved"
    settings.sources = sources
    return settings


def apply(settings: Settings, values: dict) -> Settings:
    for key, value in values.items():
        if key in ("image_purposes", "video_purposes", "spend_policy"):
            for purpose, cfg in value.items():
                getattr(settings, key).setdefault(purpose, {}).update(cfg)
        else:
            setattr(settings, key, value)
    return settings


def trial(settings: Settings, values: dict) -> Settings:
    return apply(replace(settings, image_purposes=copy.deepcopy(settings.image_purposes), video_purposes=copy.deepcopy(settings.video_purposes),
                         spend_policy=copy.deepcopy(settings.spend_policy)), values)


def view(settings: Settings) -> dict:
    saved = load(settings.state_dir)
    return {"values": {k: copy.deepcopy(getattr(settings, k)) for k in FIELDS},
            "source": {k: settings.sources.get(k) or ("saved" if k in saved else "default") for k in FIELDS}, "choices": choices()}


def effective(env=None) -> Settings:
    """The settings in force (what imagegen and other modules read per call): the environment, with the saved choices only where the environment is silent."""
    env = os.environ if env is None else env
    s = Settings.from_env(env)
    return apply_saved(s, load(s.state_dir), env)
