# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crash-safe files (CONNECTIONS.md section 9): an atomic write (temp file in the same directory, fsync, os.replace, fsync of the
directory), a read that sets an unparseable file aside instead of treating it as empty, and a cross-process lock (fcntl)."""

import contextlib
import fcntl
import json
import os
import tempfile
import time
from pathlib import Path


class Unreadable(ValueError):
    """The file exists and does not parse: it was moved aside to ``<name>.corrupt-<time>`` and nothing replaced it."""


def ensure_dir(d: Path, mode: int = 0o700) -> None:
    d = Path(d)
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, mode)


def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path, data: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_dir(path.parent)


def atomic_write_json(path, data, mode: int = 0o600) -> None:
    atomic_write_bytes(path, json.dumps(data, indent=1, sort_keys=True).encode("utf-8"), mode)


def set_aside(path) -> Path:
    path = Path(path)
    aside = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}")
    os.replace(path, aside)
    return aside


def read_json(path) -> dict:
    """The file's JSON object; ``{}`` when it does not exist. A file that does not parse (or is not an object) is set aside and
    ``Unreadable`` is raised: the caller shows an error, it never writes an empty file over the user's data."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (ValueError, UnicodeDecodeError):
        aside = set_aside(path)
        raise Unreadable(f"{path.name} was unreadable and was set aside as {aside.name}") from None
    return data


@contextlib.contextmanager
def locked(lock_path):
    """An exclusive ``fcntl.flock`` on ``lock_path`` for the duration: one writer per secret across processes."""
    lock_path = Path(lock_path)
    ensure_dir(lock_path.parent)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
