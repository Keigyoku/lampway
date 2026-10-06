"""The adapter contract: a match, and the capabilities an adapter reports. Commands are DESCRIPTIONS (inert data for the UI and the user's explicit click): nothing in this package starts a process."""
import os
from pathlib import Path

CAPABILITIES = ("files", "commands", "artifacts", "context")
MAX_ANCESTORS = 12
MAX_FILES = 2000
SKIP_DIRS = {".git", ".godot", "node_modules", "Intermediate", "Saved", "DerivedDataCache", "Binaries", ".vs", ".idea"}


class ProjectError(ValueError):
    pass


def match(adapter_id, root, confidence, reason, name, metadata=None) -> dict:
    return {"adapter_id": adapter_id, "root": str(root), "confidence": confidence, "reason": reason, "name": name, "metadata": metadata or {}}


def ancestors(start: Path, stop: Path = None):
    """The folder itself, then at most MAX_ANCESTORS parents, never above ``stop`` (the enrolled root)."""
    cur = Path(start)
    for _ in range(MAX_ANCESTORS + 1):
        yield cur
        if cur == cur.parent or (stop is not None and cur == stop):
            return
        cur = cur.parent


def ini_section(text: str, section: str) -> dict:
    """A minimal reader: the key=value pairs of one [section] (later duplicates win; comments are ; or #)."""
    out, inside = {}, False
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("["):
            inside = line.strip("[] ") == section
            continue
        if inside and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def walk_files(root: Path, depth: int, allow, cap=MAX_FILES) -> list:
    out = []
    root = Path(root)
    base = len(root.parts)
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        if len(Path(dp).parts) - base >= depth:
            dn[:] = []
        for f in sorted(fn):
            rel = (Path(dp) / f).relative_to(root).as_posix()
            if allow(rel):
                out.append({"path": rel})
                if len(out) >= cap:
                    return out
    return out
