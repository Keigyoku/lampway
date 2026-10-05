"""A small JSON-Schema checker (the subset the recorded Higgsfield tool schemas use: type, enum, const, required, properties, additionalProperties,
items, minItems/maxItems, minimum/maximum, pattern, anyOf). The fake server runs every tools/call through it against the schema RECORDED from the live
server (tests/fixtures/higgsfield/tools_list.json), so a request that the live server would refuse is refused here too."""

import re

_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list}


def _type_ok(value, name) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def check(value, schema, path="$") -> list:
    """The list of violations of ``schema`` by ``value`` (empty = valid)."""
    if "anyOf" in schema:
        tries = [check(value, s, path) for s in schema["anyOf"]]
        return [] if any(not t for t in tries) else [f"{path}: matches none of the {len(tries)} alternatives: " + " | ".join("; ".join(t) for t in tries)]
    errs = []
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{path}: expected {schema['type']}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errs.append(f"{path}: {value!r} does not match the required pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} > maximum {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        for i, item in enumerate(value):
            errs += check(item, schema.get("items") or {}, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in value:
                errs.append(f"{path}: missing required {req!r}")
        for k, v in value.items():
            if k in props:
                errs += check(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unexpected property {k!r}")
    return errs
