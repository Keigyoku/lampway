"""Skill roots, the listing, and the safe read. Refused: anything outside the skill roots and the project's knowledge folders, dot-folders, credential-looking names, extensions outside
md/txt/json/toml/yaml, files over 2 MB, and symlinks that leave their root (the real path is compared with the real root)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

FORBIDDEN = re.compile(r"(\.env(\..*)?|auth\.[^/\\]+|tokens?\.[^/\\]+|credentials\.[^/\\]+|settings\.local\.json)$")
ALLOWED_EXT = {".md", ".txt", ".json", ".toml", ".yaml", ".yml"}
MAX_BYTES = 2 * 1024 * 1024
PAGE = 24000
PROJECT_DIRS = ("knowledge", "processes", "context", "projects")
PROJECT_FILES = ("AGENTS.md", "CLAUDE.md")


class ReadRefused(ValueError):
    pass


def skill_roots(project) -> list:
    p, home = Path(project), Path(os.environ.get("HOME") or Path.home())
    return [p / ".agents" / "skills", p / ".claude" / "skills", home / ".agents" / "skills", home / ".codex" / "skills"]


def _front(text: str) -> dict:
    out = {}
    if text.startswith("---"):
        for line in text.split("---", 2)[1].splitlines():
            k, _, v = line.partition(":")
            if k.strip() in ("name", "description"):
                out[k.strip()] = v.strip()
    return out


def list_skills(project, query: Optional[str] = None) -> list:
    seen, out = set(), []
    for root in skill_roots(project):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            f = d / "SKILL.md"
            try:
                if d.name.startswith(".") or not f.is_file() or f.stat().st_size > MAX_BYTES:
                    continue
                meta = _front(f.read_text(errors="replace"))
            except OSError:
                continue
            name = meta.get("name") or d.name
            if name in seen or (query and query.lower() not in (name + " " + meta.get("description", "")).lower()):
                continue
            seen.add(name)
            out.append({"name": name, "description": meta.get("description", "")[:260], "root": str(root), "path": str(f)})
    return out


def _check(real: Path, base: Path, rel: Path) -> None:
    rb = Path(os.path.realpath(base))
    if real != rb and rb not in real.parents:
        raise ReadRefused("that path leaves the allowed folders (a symlink or '..' escape is refused)")
    if any(part.startswith(".") for part in rel.parts):
        raise ReadRefused("dot-folders and dot-files are never read")
    if FORBIDDEN.search(rel.name):
        raise ReadRefused("that file name looks like a credential store and is never read")
    if real.suffix.lower() not in ALLOWED_EXT:
        raise ReadRefused(f"only {', '.join(sorted(ALLOWED_EXT))} files are read, not {real.suffix or 'files without an extension'}")


def read_skill(project, path: str, offset: int = 0) -> dict:
    project = Path(project)
    if not path or ".." in Path(path).parts or os.path.isabs(path):
        raise ReadRefused("give a skill name or a path inside a skill root or the project's knowledge folders (no '..', no absolute paths)")
    cands = []                                                                    # (base, rel)
    for sub in (".agents/skills", ".claude/skills"):
        if path.startswith(sub + "/"):
            cands.append((project / sub, Path(path[len(sub) + 1:])))
    if not cands:
        parts = Path(path).parts
        if parts[0] in PROJECT_DIRS or path in PROJECT_FILES:
            cands.append((project, Path(path)))
        for root in skill_roots(project):
            cands.append((root, Path(path) / "SKILL.md" if len(parts) == 1 and "." not in path else Path(path)))
    last = None
    for base, rel in cands:
        full = base / rel
        if not full.exists():
            continue
        real = Path(os.path.realpath(full))
        try:
            _check(real, base, rel)
            if real.stat().st_size > MAX_BYTES:
                raise ReadRefused("that file is over 2 MB")
        except ReadRefused as exc:
            last = exc
            continue
        text = real.read_text(errors="replace")
        offset = max(0, int(offset))
        chunk = text[offset:offset + PAGE]
        nxt = offset + PAGE if offset + PAGE < len(text) else None
        return {"path": str(rel), "text": chunk, "next_offset": nxt, "total_chars": len(text)}
    if last is not None:
        raise last
    raise ReadRefused(f"no readable skill or note {path!r}: the skills are {[s['name'] for s in list_skills(project)]}")
