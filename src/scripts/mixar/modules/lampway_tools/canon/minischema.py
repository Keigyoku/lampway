# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A minimal JSON Schema (draft 2020-12) validator for the subset the canonical-asset schema uses: type, const, enum, required,
properties, additionalProperties (boolean or schema), items, minItems, maxItems, minLength, pattern, minimum, maximum,
exclusiveMinimum, if/then/else, allOf, anyOf, oneOf, not and local $ref (#/$defs/...). Blender's bundled python has no jsonschema;
an unknown keyword raises (never a silent pass), and the suite cross-checks this validator against jsonschema where it exists."""

import re

KNOWN = {"$schema", "$id", "$defs", "$ref", "$comment", "title", "description", "examples", "default", "type", "const", "enum",
         "required", "properties", "additionalProperties", "items", "minItems", "maxItems", "minLength", "pattern", "minimum",
         "maximum", "exclusiveMinimum", "if", "then", "else", "allOf", "anyOf", "oneOf", "not"}


def _is_type(v, t):
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "string":
        return isinstance(v, str)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "null":
        return v is None
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool) or (isinstance(v, float) and v.is_integer())
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    raise ValueError(f"unknown JSON Schema type {t!r}")


def _eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


class Validator:
    def __init__(self, schema):
        self.root = schema

    def _ref(self, ref):
        if not ref.startswith("#/"):
            raise ValueError(f"only local $ref is supported, got {ref!r}")
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def errors(self, inst, schema=None, path="$"):
        schema = self.root if schema is None else schema
        if schema is True:
            return []
        if schema is False:
            return [f"{path}: no value is allowed here"]
        unknown = set(schema) - KNOWN
        if unknown:
            raise ValueError(f"the vendored validator does not know {sorted(unknown)} (at {path})")
        out = []
        if "$ref" in schema:
            out += self.errors(inst, self._ref(schema["$ref"]), path)
        if "type" in schema:
            ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_is_type(inst, t) for t in ts):
                return out + [f"{path}: {inst!r:.60} is not of type {ts}"]
        if "const" in schema and not _eq(inst, schema["const"]):
            out.append(f"{path}: {inst!r:.60} is not {schema['const']!r}")
        if "enum" in schema and not any(_eq(inst, e) for e in schema["enum"]):
            out.append(f"{path}: {inst!r:.60} is not one of {schema['enum']}")
        if isinstance(inst, dict):
            for k in schema.get("required", []):
                if k not in inst:
                    out.append(f"{path}: {k!r} is a required property")
            props = schema.get("properties", {})
            for k, v in inst.items():
                if k in props:
                    out += self.errors(v, props[k], f"{path}.{k}")
                elif "additionalProperties" in schema:
                    ap = schema["additionalProperties"]
                    if ap is False:
                        out.append(f"{path}: additional property {k!r} is not allowed")
                    elif isinstance(ap, dict):
                        out += self.errors(v, ap, f"{path}.{k}")
        if isinstance(inst, list):
            if "minItems" in schema and len(inst) < schema["minItems"]:
                out.append(f"{path}: fewer than {schema['minItems']} items")
            if "maxItems" in schema and len(inst) > schema["maxItems"]:
                out.append(f"{path}: more than {schema['maxItems']} items")
            if isinstance(schema.get("items"), (dict, bool)):
                for i, v in enumerate(inst):
                    out += self.errors(v, schema["items"], f"{path}[{i}]")
        if isinstance(inst, str):
            if "minLength" in schema and len(inst) < schema["minLength"]:
                out.append(f"{path}: shorter than {schema['minLength']}")
            if "pattern" in schema and not re.search(schema["pattern"], inst):
                out.append(f"{path}: {inst!r:.60} does not match {schema['pattern']!r}")
        if isinstance(inst, (int, float)) and not isinstance(inst, bool):
            if "minimum" in schema and inst < schema["minimum"]:
                out.append(f"{path}: {inst} is less than the minimum {schema['minimum']}")
            if "maximum" in schema and inst > schema["maximum"]:
                out.append(f"{path}: {inst} is more than the maximum {schema['maximum']}")
            if "exclusiveMinimum" in schema and inst <= schema["exclusiveMinimum"]:
                out.append(f"{path}: {inst} is not more than {schema['exclusiveMinimum']}")
        for sub in schema.get("allOf", []):
            out += self.errors(inst, sub, path)
        if "anyOf" in schema and not any(not self.errors(inst, s, path) for s in schema["anyOf"]):
            out.append(f"{path}: matches none of anyOf")
        if "oneOf" in schema and sum(1 for s in schema["oneOf"] if not self.errors(inst, s, path)) != 1:
            out.append(f"{path}: does not match exactly one of oneOf")
        if "not" in schema and not self.errors(inst, schema["not"], path):
            out.append(f"{path}: matches a schema it must not")
        if "if" in schema:
            branch = "then" if not self.errors(inst, schema["if"], path) else "else"
            if branch in schema:
                out += self.errors(inst, schema[branch], path)
        return out
