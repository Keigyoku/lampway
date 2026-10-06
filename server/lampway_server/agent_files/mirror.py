"""The Claude copy of the maintained skills: byte-for-byte, no symlinks (Windows needs no privilege), dot-entries and caches skipped, and a destination-only skill is NEVER deleted."""
from __future__ import annotations

import shutil
from pathlib import Path

SKIP = {"__pycache__", "node_modules"}


def _files(root: Path) -> dict:
    out = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or p.is_symlink() or any(x.startswith(".") or x in SKIP for x in rel.parts) or p.suffix == ".pyc":
            continue
        out[rel.as_posix()] = p
    return out


def sync(project) -> dict:
    src, dst = Path(project) / ".agents" / "skills", Path(project) / ".claude" / "skills"
    copied = []
    for rel, p in _files(src).items():
        t = dst / rel
        if t.exists() and t.read_bytes() == p.read_bytes():
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, t)
        copied.append(rel)
    return {"ok": True, "copied": copied}


def check(project) -> dict:
    src, dst = _files(Path(project) / ".agents" / "skills"), _files(Path(project) / ".claude" / "skills")
    missing = sorted(r for r in src if r not in dst)
    differing = sorted(r for r in src if r in dst and src[r].read_bytes() != dst[r].read_bytes())
    ok = not missing and not differing
    return {"ok": ok, "missing": missing, "differing": differing,
            "message": "" if ok else f"{len(missing) + len(differing)} files differ: run action=sync; move an intended Claude-side edit into .agents/skills first"}
