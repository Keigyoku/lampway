# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where Lampway keeps per-user data, and the one-time copy from a stock Mixar install.

``app_home()`` is the ONE resolver: ``LAMPWAY_APP_HOME`` if set, else ``$LAMPWAY_HOME/app`` (the launcher always sets LAMPWAY_HOME, so everything
lives in the isolated profile it promises), else ``~/.lampway``. Free of ``bpy`` so any module and the build tools can import it.

``migrate_from_mixar()`` copies, once and without overwriting, the data a person would want to keep from ``~/.mixar``; it never touches the old
install, never copies loopback tokens or anything token-shaped, and writes ``MIGRATED-FROM-MIXAR.json`` saying what it did.
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

MARKER = "MIGRATED-FROM-MIXAR.json"

#: What is worth carrying over (directories and files directly under ~/.mixar).
COPY = ("chat_history", "chat_media", "checkpoints", "operation_history", "scenes-dossier", "agent_history", "onboarding_seen.json", "context_folders.json")

#: Never copied: loopback tokens are regenerated, the connector migrates itself, and a bearer token is a credential for another backend.
SKIP = ("mcp", "connector")
_SECRET_WORDS = ("token", "secret", "credential", "auth", "keyring")


_PLACEHOLDER = re.compile(r"@[A-Z_]+@")


def _absolute(var: str, value: str) -> Path:
    """A home from the environment, refused loudly unless it is an absolute path: an unexpanded placeholder or a relative value would put the
    home (and the first-run copy of the person's data) inside whatever directory the process happens to run in."""
    p = Path(value).expanduser()
    if _PLACEHOLDER.search(value) or not p.is_absolute():
        raise ValueError(f"{var}={value!r} is not an absolute path (an unexpanded placeholder or a relative path); refusing to put a Lampway home there")
    return p


def app_home() -> Path:
    explicit = os.environ.get("LAMPWAY_APP_HOME")
    if explicit:
        return _absolute("LAMPWAY_APP_HOME", explicit)
    profile = os.environ.get("LAMPWAY_HOME")
    if profile:
        return _absolute("LAMPWAY_HOME", profile) / "app"
    return Path.home() / ".lampway"


def legacy_home() -> Path:
    """The stock install's folder the first run copies from; ``LAMPWAY_LEGACY_HOME`` overrides it (the test harness points it at an empty place, so
    a test never reads the person's real chat history and checkpoints)."""
    explicit = os.environ.get("LAMPWAY_LEGACY_HOME")
    return _absolute("LAMPWAY_LEGACY_HOME", explicit) if explicit else Path.home() / ".mixar"


def _looks_secret(name: str) -> bool:
    return any(w in name.lower() for w in _SECRET_WORDS)


def _copy_tree(src: Path, dst: Path) -> None:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not _looks_secret(d)]
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            target = dst / rel / f
            if not _looks_secret(f) and not target.exists():
                shutil.copy2(Path(root) / f, target)


def migrate_from_mixar() -> dict:
    """Idempotent. Returns ``{"copied": [...], "skipped": [...], "already": bool}``."""
    new, old = app_home(), legacy_home()
    test_root = os.environ.get("LAMPWAY_TEST_ROOT")
    if test_root:                                   # set by the test harness and conftest: a test never migrates the person's real data
        real_root, real_old = os.path.realpath(test_root), os.path.realpath(old)
        if os.path.commonpath([real_root, real_old]) != real_root:
            raise PermissionError(f"refusing to migrate from {old}: it is outside the test root {test_root} (a test never reads the person's real home)")
    marker = new / MARKER
    if marker.is_file():
        return {"copied": [], "skipped": [], "already": True}
    if not old.is_dir():
        return {"copied": [], "skipped": [], "already": False}
    copied, skipped = [], []
    new.mkdir(parents=True, exist_ok=True)
    for entry in sorted(old.iterdir()):
        if entry.name in SKIP or _looks_secret(entry.name):
            skipped.append(entry.name)
        elif entry.name in COPY:
            if entry.is_dir():
                _copy_tree(entry, new / entry.name)
            elif not (new / entry.name).exists():
                shutil.copy2(entry, new / entry.name)
            copied.append(entry.name)
    report = {"copied": copied, "skipped": skipped, "already": False}
    marker.write_text(json.dumps({**report, "from": str(old), "when": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1), encoding="utf-8")
    return report


def migrate_if_launched_by_lampway() -> dict:
    """Silent first-run copy, only in a Lampway-launched session (LAMPWAY_HOME set). Anywhere else the person is asked first (not built yet), so nothing runs."""
    if not os.environ.get("LAMPWAY_HOME"):
        return {"copied": [], "skipped": [], "already": False}
    return migrate_from_mixar()
