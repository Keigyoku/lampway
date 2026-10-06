"""Rendering a template: validate the variables (typed, bounded; a refusal names the variable), fill the five-part spine in order, add the timed beats and
the negatives (at most 5), apply the per-model adapter, and return ``{prompt, negatives, inputs_required, params, warnings, template, variables, model}``. The
rendered text is what every job stores."""

import fnmatch
import re
from typing import Optional

from . import schema as S
from .library import Library

_ROLE = re.compile(r"\[(start_image|end_image|image_references|video_reference)\]")
DEFAULT_REF = {"start_image": "the start image", "end_image": "the end image", "image_references": "the reference images", "video_reference": "the reference video"}


class RenderError(ValueError):
    pass


def cap_negatives(negatives: list) -> list:
    """At most 5: the guidance is to pick the 3-5 that matter (too many negatives dull the result)."""
    return [str(n).strip() for n in negatives if str(n).strip()][:S.MAX_NEGATIVES]


def fill_variables(t: dict, given: Optional[dict]) -> dict:
    given = given or {}
    specs = t.get("variables", {})
    out = {}
    for name in given:
        if name not in specs:
            raise RenderError(f"{name}: not a variable of {t['id']} (its variables: {sorted(specs)})")
    for name, spec in specs.items():
        if name in given:
            ok, why = S.check_value(spec, given[name], name)
            if not ok:
                raise RenderError(f"{name}: {why}")
            out[name] = given[name]
        elif "default" in spec:
            out[name] = spec["default"]
        else:
            raise RenderError(f"{name}: a value is required (no default)")
    return out


def _slot(text: str, values: dict) -> str:
    def sub(m):
        v = values[m.group(1)]
        return ("yes" if v else "no") if isinstance(v, bool) else (f"{v:g}" if isinstance(v, float) else str(v))
    return S.SLOT.sub(sub, text)


def _adapter(t: dict, model: Optional[str]) -> dict:
    for pattern, adapter in (t.get("model_adapters") or {}).items():
        if model and fnmatch.fnmatch(model, pattern):
            return adapter
    return {}


def render(lib: Library, template_id: str, variables: Optional[dict] = None, model: Optional[str] = None, version: Optional[str] = None) -> dict:
    t = lib.get(template_id, version)
    values = fill_variables(t, variables)
    parts = [_slot(t["body"][p].strip(), values) for p in S.SPINE if t["body"][p].strip()]      # an empty part is skipped (verbatim ports have none)
    beats = t.get("beats") or []
    if beats:
        parts.append("Timing: " + "; ".join(f"{b['t0']:g}-{b['t1']:g} s: {_slot(b['action'].strip().rstrip('.'), values)}" for b in beats) + ".")
    negatives = cap_negatives(t.get("negatives") or [])
    if negatives:
        parts.append("Avoid: " + "; ".join(negatives) + ".")
    text = " ".join(p if p.endswith((".", "!", "?", ":")) else p + "." for p in parts)
    template_model = (t.get("defaults") or {}).get("model")
    pinned = bool(t.get("pin") is True and str(t.get("pin_reason") or "").strip())
    model = model or (template_model if pinned else None)        # CH5: the purpose's choice wins; a template's model is a hint unless pinned
    adapter = _adapter(t, model)
    warnings = []
    for phrase in adapter.get("drop_phrases") or []:
        text = re.sub(r",?\s*" + re.escape(phrase) + r",?", "", text)
    for old, new in (adapter.get("replace") or {}).items():
        text = text.replace(old, new)
    names = {**DEFAULT_REF, **(adapter.get("ref_names") or {})}
    text = _ROLE.sub(lambda m: names[m.group(1)], text)
    text = re.sub(r"\s+", " ", text).replace(" ,", ",").replace(" .", ".").strip()
    if adapter.get("note"):
        warnings.append(f"{model}: {adapter['note']}")
    words = len(text.split())
    if adapter.get("max_words") and words > adapter["max_words"]:
        warnings.append(f"{model} reads at most {adapter['max_words']} words; this prompt has {words}: shorten the variables or choose another model")
    inputs = [{"role": r, "required": bool(s.get("required")), "description": s["description"]} for r, s in (t.get("inputs") or {}).items()]
    params = {k: v for k, v in (t.get("defaults") or {}).items() if k != "model"}
    if model:
        params["model"] = model
    if t["media"] == "image" and model:
        params = adapt_image_params(model, params)
    return {"prompt": text, "negatives": negatives, "inputs_required": inputs, "params": params, "warnings": warnings, "template": f"{t['id']}@{t['version']}",
            "variables": values, "model": model, "words": words, "template_model": template_model, "pinned": pinned}


# ------------------------------------------------------------------------------------------------ ordered references
def order_references(t: dict, given) -> list:
    """The reference inputs in the order the template's prompt names them. ``given`` is a ``{role: item | [items]}`` dict (any order) or a positional list
    (matched to the roles by count and order). Refuses a missing required role, an unknown role and several items for a single-item role."""
    roles = sorted((t.get("inputs") or {}).items(), key=lambda kv: kv[1].get("order", 99))
    if isinstance(given, (list, tuple)):
        expected = sum(1 for _, s in roles if s.get("required"))
        multi = any(s.get("multiple") for _, s in roles)
        if len(given) != expected and not multi and not (len(given) <= len(roles) and len(given) >= expected):
            raise RenderError(f"{t['id']} takes {expected} reference image(s) in this order: {', '.join(r for r, _ in roles)}; got {len(given)}")
        if len(given) < expected:
            raise RenderError(f"{t['id']} takes {expected} reference image(s) in this order: {', '.join(r for r, _ in roles)}; got {len(given)}")
        mapped, i = {}, 0
        for role, spec in roles:
            if spec.get("multiple"):
                mapped[role] = list(given[i:])
                i = len(given)
            elif i < len(given):
                mapped[role] = given[i]
                i += 1
        given = mapped
    for role in given:
        if role not in dict(roles):
            raise RenderError(f"{role}: not an input of {t['id']} (its inputs in order: {', '.join(r for r, _ in roles)})")
    out = []
    for role, spec in roles:
        items = given.get(role)
        if items is None or items == []:
            if spec.get("required"):
                raise RenderError(f"{role}: required by {t['id']} ({spec['description']})")
            continue
        if isinstance(items, (list, tuple)):
            if not spec.get("multiple") and len(items) != 1:
                raise RenderError(f"{role}: takes one image, got {len(items)}")
            out += [(role, i) for i in items]
        else:
            out.append((role, items))
    return out


# ---------------------------------------------------------------------------------------- image parameters per model family
SIZE_FAMILY = ("openai/gpt-image",)
RESOLUTION_FAMILY = ("black-forest-labs/", "bytedance-seed/", "google/", "sourceful/", "qwen/", "recraft/", "inclusionai/")
_RES = {"1K", "2K", "4K"}


def family(model: str) -> str:
    if model.startswith(SIZE_FAMILY):
        return "size"
    if model.startswith(RESOLUTION_FAMILY):
        return "resolution"
    return "unknown"


def validate_image_params(model: str, params: dict) -> dict:
    """GPT Image takes ``size`` (<= 3840 per edge, ~8.3 MP) and no resolution / aspect_ratio; FLUX, Seedream, Gemini and Riverflow take ``resolution`` +
    ``aspect_ratio`` and no size. Anything else is refused with what the family takes."""
    from ..provider_prefs import PrefsError, check_size
    fam = family(model)
    if fam == "size":
        for bad in ("resolution", "aspect_ratio"):
            if params.get(bad):
                raise RenderError(f"{model} takes size (WIDTHxHEIGHT), not {bad}")
        if params.get("size"):
            try:
                check_size(params["size"])
            except PrefsError as exc:
                raise RenderError(f"{model}: {exc}") from None
    elif fam == "resolution":
        if params.get("size"):
            raise RenderError(f"{model} takes resolution + aspect_ratio, not size")
        if params.get("resolution") and params["resolution"] not in _RES:
            raise RenderError(f"{model}: resolution must be one of {sorted(_RES)}")
    return params


def _reduce(w: int, h: int) -> str:
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def adapt_image_params(model: str, params: dict) -> dict:
    """The template's defaults in the form the model's family takes: a ``size`` becomes resolution + aspect_ratio for FLUX / Gemini / Seedream / Riverflow."""
    out = dict(params)
    fam = family(model)
    if fam == "resolution" and out.get("size"):
        w, h = (int(x) for x in out.pop("size").split("x"))
        out.setdefault("aspect_ratio", _reduce(w, h) if w != h else "1:1")
        out.setdefault("resolution", out.pop("resolution_class", None) or ("2K" if max(w, h) <= 2880 else "4K"))
    elif fam == "size":
        for k in ("resolution", "aspect_ratio"):
            out.pop(k, None)
    out.pop("resolution_class", None)
    return out
