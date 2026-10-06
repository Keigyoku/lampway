"""Scaffold the project folders and instruction files, NEVER overwriting. `.env` is never created: the project `.env.example` lists names with empty values only."""
from __future__ import annotations

from pathlib import Path

from . import generate as GEN

ENV_EXAMPLE = """# Names only: copy to .env and fill in YOUR keys. Nothing here is a secret and nothing is read from this file.
OPENROUTER_API_KEY=
FAL_KEY=
BOAT_API_KEY=
RUNPOD_API_KEY=
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
"""
STUBS = {
    "context/preferences.md": "# Preferences\n\nYour own preferences go here: how you want reports written, naming, units. This file is yours; Lampway never invents a biography.\n",
    "knowledge/README.md": "# Knowledge\n\nReliable methods you want agents to reuse: one note per method.\n",
    "processes/README.md": "# Processes\n\nRepeatable procedures: what to do, in order, and what to check.\n",
    "projects/README.md": "# Projects\n\nOne note per project: goals, decisions, open questions.\n",
    ".env.example": ENV_EXAMPLE,
}


class ScaffoldError(ValueError):
    pass


def scaffold(root, overwrite=False, only=None, strict=False, rows=None) -> dict:
    root = Path(root)
    files = dict(STUBS)
    ra = GEN.render_all(rows)
    files["AGENTS.md"], files["CLAUDE.md"] = ra["files"]["AGENTS.md"], ra["files"]["CLAUDE.md"]
    created, skipped = [], []
    for rel, text in files.items():
        if only is not None and rel not in only:
            continue
        f = root / rel
        if f.exists() and not overwrite:
            if strict:
                raise ScaffoldError(f"{rel} exists: pass overwrite or pick another name")
            skipped.append(rel)
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        created.append(rel)
    return {"ok": True, "created": created, "skipped": skipped}


def status(root, rows=None) -> list:
    root = Path(root)
    ra = GEN.render_all(rows)
    out = []
    for rel in ("AGENTS.md", "CLAUDE.md", "context/preferences.md"):
        f = root / rel
        out.append({"path": rel, "state": _state(f, ra["files"].get(rel))})
    for rel, text in sorted(ra["files"].items()):
        if rel.startswith(".agents/skills/"):
            out.append({"path": rel, "state": _state(root / rel, text)})
            mirror = ".claude/skills/" + rel[len(".agents/skills/"):]
            m = root / mirror
            out.append({"path": mirror, "state": "missing" if not m.exists() else ("ok" if m.read_bytes() == (root / rel).read_bytes() and (root / rel).exists() else "differs")})
    return out


def _state(f: Path, expected):
    if not f.exists():
        return "missing"
    if expected is None:
        return "ok"
    cur = f.read_text()
    if cur == expected:
        return "ok"
    return "differs-user-owned" if GEN._marker_hash(cur) is None else "stale"
