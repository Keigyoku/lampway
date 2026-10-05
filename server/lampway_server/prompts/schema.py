"""Validation of prompt templates. The JSON Schema file next to this module is the published contract (and the single source of the enums and the
required keys); this validator checks it plus what a schema cannot say: variable defaults against their own type and bounds, every {{slot}} naming a
declared variable, beats whose end follows their start. Errors are ``{"path", "reason"}`` and name the exact place."""

import json
import re
from pathlib import Path

SCHEMA = json.loads((Path(__file__).parent / "prompt_template.schema.json").read_text(encoding="utf-8"))
_PROPS = SCHEMA["properties"]
PURPOSES = _PROPS["purpose"]["enum"]
MEDIA = _PROPS["media"]["enum"]
SPINE = tuple(_PROPS["body"]["required"])
VAR_TYPES = _PROPS["variables"]["additionalProperties"]["properties"]["type"]["enum"]
ROLES = _PROPS["inputs"]["propertyNames"]["enum"]
MAX_NEGATIVES = _PROPS["negatives"]["maxItems"]
_ID = re.compile(_PROPS["id"]["pattern"])
_VERSION = re.compile(_PROPS["version"]["pattern"])
SLOT = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_TOP = set(_PROPS)


def err(errors, path, reason):
    errors.append({"path": path, "reason": reason})


def check_value(spec: dict, value, name: str):
    """(ok, reason) for ``value`` against a variable spec."""
    t = spec.get("type")
    if t == "string":
        return (isinstance(value, str), "must be a string")
    if t == "boolean":
        return (isinstance(value, bool), "must be true or false")
    if t == "enum":
        return (value in (spec.get("enum") or []), f"must be one of the enum values {spec.get('enum')}")
    if t in ("integer", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (t == "integer" and isinstance(value, float) and not value.is_integer()):
            return (False, f"must be {'a whole number' if t == 'integer' else 'a number'}")
        if "min" in spec and value < spec["min"]:
            return (False, f"{value} is below the min {spec['min']}")
        if "max" in spec and value > spec["max"]:
            return (False, f"{value} is above the max {spec['max']}")
        return (True, "")
    return (False, "unknown type")


def validate(t) -> list:
    errors: list = []
    if not isinstance(t, dict):
        return [{"path": "", "reason": "a template is a JSON object"}]
    for key in t:
        if key not in _TOP:
            err(errors, key, f"unknown field (the fields are {sorted(_TOP)})")
    for key in SCHEMA["required"]:
        if key not in t:
            err(errors, key, "required")
    if "id" in t and not (isinstance(t["id"], str) and _ID.match(t["id"])):
        err(errors, "id", "must be kebab-case (lowercase letters, digits and single hyphens)")
    if "version" in t and not (isinstance(t["version"], str) and _VERSION.match(t["version"])):
        err(errors, "version", "must be semver, e.g. 1.0.0")
    if "purpose" in t and t["purpose"] not in PURPOSES:
        err(errors, "purpose", f"must be one of {PURPOSES}")
    if "media" in t and t["media"] not in MEDIA:
        err(errors, "media", "must be image or video")
    if "title" in t and not (isinstance(t["title"], str) and t["title"].strip()):
        err(errors, "title", "must be a non-empty string")
    body = t.get("body")
    if "body" in t and not isinstance(body, dict):
        err(errors, "body", "must be an object with the five spine parts")
        body = None
    if body is not None:
        for part in SPINE:
            if part not in body:
                err(errors, f"body.{part}", "required (the spine is subject, action, camera, style, constraints)")
            elif not isinstance(body[part], str):
                err(errors, f"body.{part}", "must be a string")
        for extra in set(body) - set(SPINE):
            err(errors, f"body.{extra}", "not a spine part")
    variables = t.get("variables", {})
    if not isinstance(variables, dict):
        err(errors, "variables", "must be an object")
        variables = {}
    for name, spec in variables.items():
        base = f"variables.{name}"
        if not isinstance(spec, dict):
            err(errors, base, "must be an object")
            continue
        if spec.get("type") not in VAR_TYPES:
            err(errors, f"{base}.type", f"must be one of {VAR_TYPES}")
            continue
        if spec["type"] == "enum" and not (isinstance(spec.get("enum"), list) and spec["enum"]):
            err(errors, f"{base}.enum", "an enum variable needs a non-empty enum list")
        if "default" in spec:
            ok, why = check_value(spec, spec["default"], name)
            if not ok:
                err(errors, f"{base}.default", why if spec["type"] != "enum" else "the default must be one of the enum values")
    negatives = t.get("negatives", [])
    if not isinstance(negatives, list) or not all(isinstance(n, str) for n in negatives):
        err(errors, "negatives", "must be a list of strings")
    elif len(negatives) > MAX_NEGATIVES:
        err(errors, "negatives", f"at most {MAX_NEGATIVES} (pick the 3-5 that matter; too many dull the result), got {len(negatives)}")
    for i, b in enumerate(t.get("beats", []) if isinstance(t.get("beats", []), list) else []):
        if not (isinstance(b, dict) and all(k in b for k in ("t0", "t1", "action"))):
            err(errors, f"beats[{i}]", "needs t0, t1 and action")
        elif not (isinstance(b["t0"], (int, float)) and isinstance(b["t1"], (int, float)) and b["t1"] > b["t0"] >= 0):
            err(errors, f"beats[{i}]", "t1 must be greater than t0 and t0 at least 0")
    inputs = t.get("inputs", {})
    if isinstance(inputs, dict):
        for role, spec in inputs.items():
            if role not in ROLES:
                err(errors, f"inputs.{role}", f"not an input role (the roles are {ROLES})")
            elif not (isinstance(spec, dict) and isinstance(spec.get("description"), str)):
                err(errors, f"inputs.{role}.description", "required: what the input must show")
    for i, g in enumerate(t.get("gates", []) if isinstance(t.get("gates", []), list) else []):
        if not (isinstance(g, dict) and isinstance(g.get("id"), str) and g["id"]):
            err(errors, f"gates[{i}].id", "required")
    # every {{slot}} must name a declared variable
    texts = ([(f"body.{k}", v) for k, v in (body or {}).items() if isinstance(v, str)]
             + [(f"beats[{i}].action", b.get("action")) for i, b in enumerate(t.get("beats", []) if isinstance(t.get("beats"), list) else []) if isinstance(b, dict)])
    for path, text in texts:
        for name in SLOT.findall(text or ""):
            if name not in variables:
                err(errors, path, f"uses {{{{{name}}}}} but declares no variable {name!r}")
    return errors
