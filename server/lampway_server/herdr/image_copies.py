# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private ownership receipts for project-local pane image copies, retained for 30 days.

Private per-session manifests outlive the pane registry; only files recorded at creation can expire.
Project image directories never establish ownership.
"""
import contextlib
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

RETENTION_SECONDS = 30 * 86400
_LOCK = threading.RLock()
log = logging.getLogger("lampway.herdr")
_NAMES = re.compile(r"image-\d{8}-\d{6}-[0-9a-f]{8}\.(png|jpg|gif|webp)\Z")


@contextlib.contextmanager
def _directory(root, parts):
    """Open each directory without following links; the resulting fd pins the deletion directory."""
    absolute = Path(os.path.abspath(root))
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in (*absolute.parts[1:], *parts):
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        yield fd
    finally:
        os.close(fd)


class ImageCopies:
    def __init__(self, root):
        self.root = Path(root)

    def _manifest(self, sid, create=False):
        if not sid or Path(sid).name != sid or sid in (".", ".."):
            raise ValueError("invalid image copy session")
        parent = self.root
        for part in ("panes", sid):
            parent = parent / part
            if create:
                parent.mkdir(mode=0o700, exist_ok=True)
            if parent.is_symlink():
                raise ValueError("image ownership directory is a symlink")
        return parent / "image-copies.json"

    def _load(self, sid):
        self._manifest(sid)  # validate the session name and reject linked metadata directories
        try:
            with _directory(self.root, ("panes", sid)) as directory:
                fd = os.open("image-copies.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    os.close(fd)
                    raise ValueError("image ownership metadata is not a regular file")
        except FileNotFoundError:
            return {"version": 1, "session_id": sid, "files": []}
        with os.fdopen(fd) as fh:
            data = json.load(fh)
        if (not isinstance(data, dict) or data.get("version") != 1 or data.get("session_id") != sid
                or not isinstance(data.get("files"), list)):
            raise ValueError("invalid image ownership metadata")
        return data

    def _save(self, sid, data):
        path = self._manifest(sid, create=True)
        fd, temporary = tempfile.mkstemp(prefix=".image-copies-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def remember(self, sid, project_root, paths, now):
        """Record only the exact freshly-created files, keeping metadata out of the harness image folder."""
        with _LOCK:
            data = self._load(sid)
            target = Path(project_root) / ".lampway" / "panes" / sid / "images"
            for path in map(Path, paths):
                if path.parent != target or not _NAMES.fullmatch(path.name):
                    raise ValueError("invalid owned image copy path")
                st = path.lstat()
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                    raise ValueError("image copy is not a private regular file")
                data["files"].append({"name": path.name, "project_root": str(project_root), "created_at": now,
                                      "dev": st.st_dev, "ino": st.st_ino, "size": st.st_size,
                                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            self._save(sid, data)

    def expire_all(self, now):
        """Reconcile private manifests even after a pane leaves the registry; never scan project image directories."""
        removed = []
        with _LOCK:
            try:
                with _directory(self.root, ("panes",)) as directory:
                    sessions = sorted(name for name in os.listdir(directory)
                                      if stat.S_ISDIR(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode))
            except OSError:
                return removed
            for sid in sessions:
                try:
                    removed.extend(self.expire(sid, None, now))
                except (OSError, ValueError, TypeError):
                    log.warning("pane image ownership metadata unavailable; copies retained")
        return removed

    def expire(self, sid, project_root, now):
        """Delete expired copies only when identity and bytes still prove ownership; leave replacements untouched."""
        with _LOCK:
            data = self._load(sid)
            keep, removed = [], []
            for row in data["files"]:
                if not isinstance(row, dict):
                    continue
                created = row.get("created_at")
                try:
                    valid_timestamp = isinstance(created, (int, float)) and math.isfinite(created)
                except OverflowError:
                    valid_timestamp = False
                if not valid_timestamp:
                    keep.append(row)  # corrupt timing cannot expire a copy or discard its ownership receipt
                    continue
                if now - created < RETENTION_SECONDS:
                    keep.append(row)
                    continue
                name = row.get("name", "")
                owned_root = row.get("project_root")
                if (not isinstance(name, str) or not _NAMES.fullmatch(name)
                        or not isinstance(owned_root, str) or not os.path.isabs(owned_root)
                        or os.path.normpath(owned_root) != owned_root):
                    continue
                if project_root is not None and owned_root != str(project_root):
                    keep.append(row)
                    continue
                try:
                    with _directory(owned_root, (".lampway", "panes", sid, "images")) as directory:
                        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                        with os.fdopen(fd, "rb") as fh:
                            st = os.fstat(fh.fileno())
                            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                                    or (st.st_dev, st.st_ino, st.st_size) != (row.get("dev"), row.get("ino"), row.get("size"))
                                    or hashlib.sha256(fh.read()).hexdigest() != row.get("sha256")):
                                continue
                            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                            if (current.st_dev, current.st_ino, current.st_nlink) != (st.st_dev, st.st_ino, 1):
                                continue
                            os.unlink(name, dir_fd=directory)
                            removed.append(str(Path(owned_root) / ".lampway" / "panes" / sid / "images" / name))
                except FileNotFoundError:
                    pass
                except OSError:
                    # A symlink, changed directory or inaccessible file is never deletion authority.
                    keep.append(row)
            if keep != data["files"]:
                data["files"] = keep
                self._save(sid, data)
            return removed
