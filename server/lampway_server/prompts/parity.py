"""Clause parity between an original prompt and the template(s) made from it: "nothing can be lost" as a check that can fail.

An original is split into clauses (lines, list items, inline " - " items, sentences). Each clause must be found, after normalisation (case, curly
quotes, whitespace, trailing punctuation), in a field of one of its templates: a body part, a variable's enum value or default, a negative, an input's
description; template slots are read back as the original's placeholders (``{{asset_name}}`` -> ``[ASSET NAME]``, ``{{view}}`` -> ``[VIEW NAME]``).
A clause that was reworded is found through the parity map's alias: ``{clause: {"as": the new wording, "at": "<template id>:<field>"}}``, and the alias
holds only if that wording really is in that field. A clause split across fields lists ``{"parts": [{"as", "at"}, ...]}``, and every part must hold. The result is the parity map itself: every clause with the field it lives in, or None.

``python -m lampway_server.prompts.parity`` prints the map for the moodboard prompts."""

import json
import re
from pathlib import Path

MAP_PATH = Path(__file__).with_name("moodboard_parity.json")
PLACEHOLDERS = {"asset_name": "[ASSET NAME]", "view": "[VIEW NAME]"}
_SLOT = re.compile(r"\{\{(\w+)\}\}")


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.rstrip(" .:;,")


def clauses(text: str) -> list:
    out = []
    for line in text.replace("’", "'").splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^-\s+", "", line)
        for item in re.split(r"\s+-\s+", line):
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", item):
                c = norm(sent)
                if c and c not in out:
                    out.append(c)
    return out


def fields(t: dict) -> dict:
    """{"<id>:<field path>": text} with slots read back as the original placeholders."""
    back = lambda s: _SLOT.sub(lambda m: PLACEHOLDERS.get(m.group(1), m.group(0)), s)
    out = {f"{t['id']}:body.{k}": back(v) for k, v in (t.get("body") or {}).items()}
    for name, spec in (t.get("variables") or {}).items():
        for i, v in enumerate(spec.get("enum") or []):
            out[f"{t['id']}:variables.{name}.enum[{i}]"] = v
        if isinstance(spec.get("default"), str):
            out[f"{t['id']}:variables.{name}.default"] = spec["default"]
    for i, n in enumerate(t.get("negatives") or []):
        out[f"{t['id']}:negatives[{i}]"] = n
    for role, spec in (t.get("inputs") or {}).items():
        out[f"{t['id']}:inputs.{role}"] = spec.get("description", "")
    return out


def check(original: str, templates: list, aliases: dict) -> list:
    f = {}
    for t in templates:
        f.update(fields(t))
    nf = {k: norm(v) for k, v in f.items()}
    rows = []
    for c in clauses(original):
        loc = next((k for k, v in nf.items() if c in v), None)
        via = "verbatim" if loc else None
        if loc is None and c in {norm(k) for k in aliases}:
            a = next(v for k, v in aliases.items() if norm(k) == c)
            parts = a.get("parts") or [a]
            if parts and all(x.get("at") in nf and norm(x.get("as", "")) and norm(x["as"]) in nf[x["at"]] for x in parts):
                loc, via = " + ".join(x["at"] for x in parts), "alias"
        rows.append({"clause": c, "location": loc, "via": via})
    return rows


def load_map(path=MAP_PATH) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: dict(e, aliases={norm(k): v for k, v in (e.get("aliases") or {}).items()}) for name, e in raw.items()}


if __name__ == "__main__":
    from .library import Library
    lib = Library(user_dir=None, project_dir=None)
    fixtures = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "moodboard"
    for name, e in load_map().items():
        for r in check((fixtures / name).read_text(encoding="utf-8"), [lib.get(t) for t in e["templates"]], e["aliases"]):
            print(f"{name}\t{r['via'] or 'LOST'}\t{r['location']}\t{r['clause']}")
