"""Safe note writes: the revision (sha256 of the bytes you read) must match, the previous bytes are backed up with a JSON sidecar, the new text goes to a temp file in the same folder and is renamed after the
revision is checked again, and writes are serialised by a lock (in-process and across processes)."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

DIRS = ("knowledge", "processes", "context", "projects")
MAX_BYTES = 2 * 1024 * 1024
_LOCK = threading.Lock()


class NoteRefused(ValueError):
    pass


class Stale(NoteRefused):
    pass


def revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(project, path: str) -> dict:
    full = _resolve(project, path)
    data = full.read_bytes()
    return {"text": data.decode("utf-8", "replace"), "revision": revision(data)}


def _resolve(project, path: str) -> Path:
    p = Path(path)
    if not path or p.is_absolute() or ".." in p.parts or p.parts[0] not in DIRS or p.suffix.lower() not in (".md", ".txt"):
        raise NoteRefused(f"notes live in {', '.join(d + '/' for d in DIRS)} as .md or .txt files, with no '..' and no absolute path")
    root = Path(os.path.realpath(project))
    full = Path(os.path.realpath(root / p))
    if root not in full.parents:
        raise NoteRefused("that path leaves the project")
    return full


def write(project, path: str, text: str, rev: Optional[str], state_dir) -> dict:
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise NoteRefused("a note is at most 2 MB")
    full = _resolve(project, path)
    full.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(state_dir) / "note-write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(lock_path, "a") as lk:
        if fcntl:
            fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            cur = full.read_bytes() if full.exists() else None
            if cur is not None and (rev is None or revision(cur) != rev):
                raise Stale("this file changed on disk; your draft is kept; read it again")
            if cur is None and rev is not None:
                raise Stale("this file no longer exists on disk; your draft is kept; read it again")
            if cur is not None:
                bdir = Path(state_dir) / "note-backups"
                bdir.mkdir(parents=True, exist_ok=True)
                stem = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
                (bdir / f"{stem}.md").write_bytes(cur)
                (bdir / f"{stem}.json").write_text(json.dumps({"path": path, "revision": revision(cur), "saved_at": time.time()}))
            tmp = full.with_name(f".{full.name}.{uuid.uuid4().hex[:6]}.tmp")
            tmp.write_bytes(data)
            if cur is not None and revision(full.read_bytes()) != revision(cur):          # re-check just before the rename
                tmp.unlink()
                raise Stale("this file changed on disk; your draft is kept; read it again")
            os.replace(tmp, full)
        finally:
            if fcntl:
                fcntl.flock(lk, fcntl.LOCK_UN)
    return {"ok": True, "path": path, "revision": revision(data), "created": cur is None}
