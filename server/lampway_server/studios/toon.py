# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A reader for the shelf drivers' output (AXI, TOON v4.1; tools/AXI.md, TOON-SPEC.md): ``key: value`` lines, one level of nested
``key:`` blocks, ``name[N]{f1,f2}:`` tables, ``error: why`` refusals and ``help[N]:`` next-step lists. Only what the Studio service
needs: it parses what the drivers print, it does not write TOON."""

import json
import re
from dataclasses import dataclass, field

_NUM = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.I)
_TABLE = re.compile(r"^([A-Za-z_][\w.]*|\"[^\"]*\")\[(\d+)\](?:\{([^}]*)\})?:\s*$")


@dataclass
class Parsed:
    kv: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)
    help: list = field(default_factory=list)
    error: str = None


def _unquote(s: str) -> str:
    return json.loads(s) if s.startswith('"') and s.endswith('"') and len(s) >= 2 else s


def _scalar(s: str):
    s = s.strip()
    if s == "null":
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if s.startswith('"'):
        try:
            return json.loads(s)
        except ValueError:
            return s
    if _NUM.match(s):
        return float(s) if ("." in s or "e" in s.lower()) else int(s)
    return s


def _split_row(line: str) -> list:
    out, cur, quoted, esc = [], "", False, False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\" and quoted:
            cur += ch
            esc = True
        elif ch == '"':
            cur += ch
            quoted = not quoted
        elif ch == "," and not quoted:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def parse(text: str) -> Parsed:
    p = Parsed()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.startswith(" "):
            continue
        m = _TABLE.match(line)
        if m:
            name, n, fields = _unquote(m.group(1)), int(m.group(2)), m.group(3)
            if name == "help":
                while i < len(lines) and lines[i].startswith("  - "):
                    item = lines[i][4:].strip()
                    p.help.append(_unquote(item) if item.startswith('"') else item)
                    i += 1
                p.help = [re.sub(r"^Run `|`$", "", h) for h in p.help]
                continue
            cols = [_unquote(c.strip()) for c in fields.split(",")] if fields else []
            rows = []
            while i < len(lines) and lines[i].startswith("  "):
                vals = [_scalar(v) for v in _split_row(lines[i].strip())]
                rows.append(dict(zip(cols, vals)))
                i += 1
            p.tables[name] = rows
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key = _unquote(key.strip())
        if key == "error" and p.error is None:
            p.error = rest.strip()
            continue
        if rest.strip() == "":                                         # a nested block, one level
            nested = {}
            while i < len(lines) and lines[i].startswith("  ") and not lines[i].startswith("  - "):
                k2, _, v2 = lines[i].strip().partition(":")
                nested[_unquote(k2.strip())] = _scalar(v2)
                i += 1
            p.kv[key] = nested
        else:
            p.kv[key] = _scalar(rest)
    return p
