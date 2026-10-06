# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway.ue-profile/1: the one file that describes the UE scene a piece is judged in (specs/ue_parity/contracts/ue_look.md §4).

Every field is required and there are no defaults inside the tool: the shipped ``profiles/engine_defaults.json`` IS the default,
with each value's source in its ``notes``. The captain's open choices are named fields (``OPEN_CHOICES``); the code reads them,
never a constant. Pure Python (no bpy): the hash is of the canonical content (sorted keys, floats to 6 decimals), so two files
that say the same thing hash the same."""

import hashlib
import json
import math
from pathlib import Path

SCHEMA = "lampway.ue-profile/1"
DEFAULT_PROFILE = Path(__file__).parent / "profiles" / "engine_defaults.json"

# the captain's open choices (REPORT.md "Decisions the captain owes"), each a named field of the profile
OPEN_CHOICES = ("light_units.k", "judgement_surface", "project.cvars.r.Material.EnergyConservation", "preview.texture_compression",
                "export.precision")

CVARS = ("r.Substrate", "r.Material.EnergyConservation", "r.DynamicGlobalIlluminationMethod", "r.ReflectionMethod", "r.Shadow.Virtual.Enable",
         "r.AntiAliasingMethod", "r.LUT.Size", "r.LUT.Shaper", "r.HDR.Aces.Version", "r.MaxAnisotropy")


class ProfileError(ValueError):
    pass


def _need(d, key, where):
    if not isinstance(d, dict) or key not in d:
        raise ProfileError(f"{where + '.' if where else ''}{key} is required")
    return d[key]


def _num(d, key, where, positive=False):
    v = _need(d, key, where)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (positive and v <= 0):
        raise ProfileError(f"{where}.{key} must be a {'positive ' if positive else ''}number")
    return v


def _one_of(d, key, where, allowed, message):
    v = _need(d, key, where)
    if v not in allowed:
        raise ProfileError(message)
    return v


def validate(p: dict) -> dict:
    """Refuse a profile that lacks a field or carries a value the renderer cannot act on; the message names the field."""
    if _need(p, "schema", "") != SCHEMA:
        raise ProfileError(f"schema must be {SCHEMA}")
    _one_of(p, "source", "", ("live-dump", "engine-defaults"), "source is live-dump or engine-defaults")
    eng = _need(p, "engine", "")
    _need(eng, "version", "engine"), _need(eng, "changelist", "engine")
    proj = _need(p, "project", "")
    _need(proj, "name", "project"), _need(proj, "working_color_space", "project"), _need(proj, "scalability", "project")
    cv = _need(proj, "cvars", "project")
    for name in CVARS:
        _num(cv, name, "project.cvars")
    tm = _need(p, "tonemap", "")
    _need(tm, "method", "tonemap")
    film = _need(tm, "film", "tonemap")
    for k in ("slope", "toe", "shoulder", "black_clip", "white_clip"):
        _num(film, k, "tonemap.film")
    for k in ("blue_correction", "expand_gamut", "tone_curve_amount", "white_temp", "white_tint"):
        _num(tm, k, "tonemap")
    _need(tm, "grading", "tonemap")
    for k in ("tonemap_cube", "tonemap_cube_meta"):
        v = _need(p, k, "")
        if v is not None and (not isinstance(v, str) or not v):
            raise ProfileError(f"{k} is a path or null")
    ex = _need(p, "exposure", "")
    _one_of(ex, "method", "exposure", ("manual", "auto"), "exposure.method is manual or auto")
    _num(ex, "bias", "exposure")
    if not isinstance(_need(ex, "apply_physical_camera", "exposure"), bool):
        raise ProfileError("exposure.apply_physical_camera must be true or false")
    for k in ("fstop", "shutter", "iso"):
        _num(ex, k, "exposure", positive=True)
    post = _need(p, "post", "")
    for k in ("bloom", "vignette", "ssao"):
        _num(post, k, "post")
    le = _need(post, "local_exposure", "post")
    for k in ("highlight", "shadow", "detail"):
        _num(le, k, "post.local_exposure")
    _num(_need(p, "light_units", ""), "k", "light_units", positive=True)
    js = _need(p, "judgement_surface", "")
    if not (js in ("capture", "viewport") or (isinstance(js, str) and js.startswith("map:") and len(js) > 4)):
        raise ProfileError("judgement_surface is capture, viewport or map:<name>")
    _one_of(_need(p, "preview", ""), "texture_compression", "preview", ("source", "bc_decoded"), "preview.texture_compression is source or bc_decoded")
    _one_of(_need(p, "export", ""), "precision", "export", ("standard", "hero"), "export.precision is standard or hero")
    if not isinstance(_need(_need(p, "material", ""), "clear_coat", "material"), bool):
        raise ProfileError("material.clear_coat must be true or false")
    return p


def load(path) -> dict:
    """Read and validate a profile file; a missing file or bad JSON is refused by name."""
    q = Path(path)
    try:
        data = json.loads(q.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProfileError(f"no profile at {q}") from None
    except ValueError as exc:
        raise ProfileError(f"{q.name} is not JSON: {exc}") from None
    return validate(data)


def _canon(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    return v


def canonical_json(obj) -> str:
    """Sorted keys, floats rounded to 6 decimals, no whitespace: the form every hash in the UE Renderer is taken of."""
    return json.dumps(_canon(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(profile: dict) -> str:
    return hashlib.sha256(canonical_json(profile).encode("utf-8")).hexdigest()


def ev100(profile: dict) -> float:
    """UE's physical-camera EV100 = log2(N^2 * shutter * 100 / ISO) (shutter as 1/seconds); 0 when the physical camera is off (COL-08)."""
    ex = profile["exposure"]
    if not ex["apply_physical_camera"]:
        return 0.0
    return math.log2(ex["fstop"] ** 2 * ex["shutter"] * 100.0 / ex["iso"])


def exposure_stops(profile: dict) -> float:
    """Blender's exposure that reproduces UE's manual exposure for lights scaled by k: log2(k) + Bias - EV100 (COL-08)."""
    return math.log2(profile["light_units"]["k"]) + profile["exposure"]["bias"] - ev100(profile)
