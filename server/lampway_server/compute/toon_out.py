"""A small TOON encoder (toonformat.dev, spec 4.3): `key: value`, tables as `name[N]{f1,f2}:` rows when every element is an object
with the same keys and primitive values, scalar lists as `name[N]: a,b`, list form (`- ...` items) otherwise, and `name: []` for an
empty list. Strings, keys and numbers follow the spec's quoting, escaping and canonical-number rules (audit F9, 2026-10-06: an
unquoted "true", "42", "x: y" or "#c" decoded as a bool, a number, a key and a dropped comment; ragged rows got invented nulls).
server/tests/test_toon_out_fixtures.py holds it to the official encode fixtures. Not built: keyed tabular objects and nested field
groups (compact forms; the shared encoder is the cloud crew's C0)."""
from __future__ import annotations

import decimal
import math
import re

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_NUMERIC_LIKE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)
_STRUCTURAL = set(':"\\[]{}')
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _quoted(s: str) -> str:
    return '"' + "".join(_ESCAPES.get(c, f"\\u{ord(c):04x}" if ord(c) < 0x20 else c) for c in s) + '"'


def _number(v) -> str:
    if isinstance(v, int):
        return str(v)
    if not math.isfinite(v):
        return "null"                                   # the spec's normalization: a non-finite number is null
    if v == 0:
        return "0"                                      # -0 too
    if 1e-6 <= abs(v) < 1e21:
        s = format(decimal.Decimal(repr(v)), "f")       # repr is the shortest round-trip form; no exponent in the canonical range
        return s.rstrip("0").rstrip(".") if "." in s else s
    mantissa, exponent = repr(v).lower().split("e")
    return f"{mantissa}e{'+' if int(exponent) >= 0 else '-'}{abs(int(exponent))}"


def _string(s: str, delim: str = ",") -> str:
    needs = (s == "" or s[0] in " \t" or s[-1] in " \t" or s in ("true", "false", "null") or _NUMERIC_LIKE.match(s)
             or any(c in _STRUCTURAL or ord(c) < 0x20 for c in s) or delim in s or s[0] in "-#")
    return _quoted(s) if needs else s


def _scalar(v, delim: str = ",") -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _number(v)
    return _string(str(v), delim)


def _key(k) -> str:
    k = str(k)
    return k if _KEY.fullmatch(k) else _quoted(k)            # fullmatch: "$" alone would let a trailing newline through


def _primitive(v) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _field(key: str, v, depth: int) -> list:
    pad = "  " * depth
    if isinstance(v, dict):
        return [f"{pad}{key}:"] + _object(v, depth + 1)
    if isinstance(v, (list, tuple)):
        return _array(key, list(v), depth)
    return [f"{pad}{key}: {_scalar(v)}"]


def _object(obj: dict, depth: int) -> list:
    lines = []
    for k, v in obj.items():
        lines += _field(_key(k), v, depth)
    return lines


def _tabular(arr: list):
    """The header fields (the first element's order) when every element is a non-empty object with the same keys and primitive values."""
    if not all(isinstance(x, dict) and x for x in arr):
        return None
    fields = list(arr[0])
    if any(set(x) != set(fields) or not all(_primitive(v) for v in x.values()) for x in arr):
        return None
    return fields


def _array(key: str, arr: list, depth: int) -> list:
    pad = "  " * depth
    if not arr:
        return [f"{pad}{key}: []"] if key else [f"{pad}[]"]
    head = f"{pad}{key}[{len(arr)}]"
    if all(_primitive(x) for x in arr):
        return [f"{head}: {','.join(_scalar(x) for x in arr)}"]
    fields = _tabular(arr)
    if fields is not None:
        return [f"{head}{{{','.join(_key(f) for f in fields)}}}:"] + [f"{pad}  {','.join(_scalar(x[f]) for f in fields)}" for x in arr]
    lines = [f"{head}:"]
    for x in arr:
        lines += _item(x, depth + 1)
    return lines


def _item(x, depth: int) -> list:
    """One list-form item: ``- value``; an object's first field sits on the hyphen line, its siblings one level in."""
    pad = "  " * depth
    if _primitive(x):
        return [f"{pad}- {_scalar(x)}"]
    if isinstance(x, dict) and not x:
        return [f"{pad}-"]
    if not isinstance(x, dict):                         # an array as a list item: `- [N]: a,b`, else `- [N]:` with its items one level in
        x = list(x)
        if all(_primitive(v) for v in x):
            return [f"{pad}- [{len(x)}]:" + (f" {','.join(_scalar(v) for v in x)}" if x else "")]
        lines = [f"{pad}- [{len(x)}]:"]                  # never tabular: a keyless fields-bearing header is valid only at the root
        for v in x:
            lines += _item(v, depth + 1)
        return lines
    inner = _object(x, depth + 1)
    first = inner[0][len("  " * (depth + 1)):]
    return [f"{pad}- {first}"] + inner[1:]


def dumps(obj: dict, indent: int = 0) -> str:
    return "\n".join(_object(obj, indent))
