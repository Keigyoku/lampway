"""A small TOON encoder (toonformat.dev): `key: value`, tables as `name[N]{f1,f2}:` rows, scalar lists as `name[N]: a,b`, and an explicit `name[0]:` for an empty list (AXI principle 5)."""
from __future__ import annotations

import json


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.6g}"
    s = str(v)
    return json.dumps(s) if any(c in s for c in ',"\n') or s != s.strip() or s == "" else s


def dumps(obj: dict, indent: int = 0) -> str:
    pad, lines = "  " * indent, []
    for k, v in obj.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(dumps(v, indent + 1))
        elif isinstance(v, (list, tuple)):
            if not v:
                lines.append(f"{pad}{k}[0]:")
            elif all(isinstance(x, dict) for x in v):
                cols = list(dict.fromkeys(c for x in v for c in x))
                lines.append(f"{pad}{k}[{len(v)}]{{{','.join(cols)}}}:")
                lines += [f"{pad}  {','.join(_scalar(x.get(c)) for c in cols)}" for x in v]
            else:
                lines.append(f"{pad}{k}[{len(v)}]: {','.join(_scalar(x) for x in v)}")
        else:
            lines.append(f"{pad}{k}: {_scalar(v)}")
    return "\n".join(lines)
