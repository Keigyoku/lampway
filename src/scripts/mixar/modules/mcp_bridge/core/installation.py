# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stable local entrypoint refreshed by the installed app, with no system Python."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

from mixar.modules.mcp_bridge.constants import LAUNCHER_NAME, LEGACY_LAUNCHER_NAME

from .discovery import discovery_directory


def directory():
    return discovery_directory().parent / "connector"


def legacy_directory():
    """Where a pre-Lampway install put its connector (~/.mixar/connector); never created by Lampway."""
    return Path.home() / ".mixar" / "connector"


def _atomic(path, data, mode=0o600):
    temporary = path.with_name("."+uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def provision(python, script, executable, enabled=True):
    root = directory()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise OSError("Connector directory must not be a symlink")
    if os.name != "nt":
        if root.stat().st_uid != os.getuid():
            raise OSError("Connector directory belongs to another user")
        root.chmod(0o700)
    manifest = {"version": 1, "python": str(python), "script": str(script),
                "executable": str(executable), "enabled": bool(enabled)}
    _atomic(root / "installation.json", json.dumps(manifest))
    if os.name == "nt":
        path = root / (LAUNCHER_NAME + ".cmd")
        command = subprocess.list2cmdline([str(python), str(script)]).replace('%', '%%')
        _atomic(path, "@echo off\n"+command+" %*\n")
    else:
        path = root / LAUNCHER_NAME
        _atomic(path, "#!/bin/sh\nexec "+shlex.join([str(python), str(script)])+' "$@"\n', 0o700)
    _legacy_shim(path)
    return path


def _legacy_shim(launcher):
    """For one release: an install that already had ~/.mixar/connector keeps a launcher at its old path that forwards to the new one, so an app configured with
    the old command line still works. Never creates the old folder on a fresh install."""
    old = legacy_directory()
    if not old.is_dir():
        return
    if os.name == "nt":
        _atomic(old / (LEGACY_LAUNCHER_NAME + ".cmd"), "@echo off\n"+subprocess.list2cmdline([str(launcher)])+" %*\n")
    else:
        _atomic(old / LEGACY_LAUNCHER_NAME, "#!/bin/sh\nexec "+shlex.join([str(launcher)])+' "$@"\n', 0o700)


def migrate():
    """Read the old ~/.mixar/connector/installation.json once and write it (and the new launcher) at the Lampway location. True when it did; the old file is left alone."""
    new = directory() / "installation.json"
    old = legacy_directory() / "installation.json"
    if new.exists() or not old.is_file():
        return False
    try:
        info = json.loads(old.read_text())
        if info.get("version") != 1 or not all(isinstance(info.get(k), str) for k in ("python", "script", "executable")):
            return False
    except (OSError, ValueError):
        return False
    provision(info["python"], info["script"], info["executable"], enabled=bool(info.get("enabled", True)))
    return True


# A first launch (Gatekeeper, shader cache, sign-in restore) can take well over
# a minute before the relay appears; until then Mixar counts as starting. The
# marker is removed as soon as an app publishes its relay or the launch fails,
# so a quit or crashed app is not "starting" for the rest of the window.
STARTING_SECONDS = 180
OPEN_WAIT_SECONDS = 5


def started():
    """A launched Mixar is up (its relay is published), or the launch failed."""
    try:
        (directory() / "starting").unlink()
    except OSError:
        pass


def start_in_progress():
    """An MCP host started Mixar within the last STARTING_SECONDS."""
    try:
        return time.time()-(directory() / "starting").stat().st_mtime <= STARTING_SECONDS
    except OSError:
        return False


def start_app():
    """At most one cold start across simultaneous MCP hosts; no repeated resurrection."""
    migrate()
    root = directory()
    try:
        info = json.loads((root / "installation.json").read_text())
    except (OSError, ValueError):
        return False
    if info.get("version") != 1 or info.get("enabled") is not True:
        return False
    executable = Path(info["executable"])
    if not executable.is_absolute() or not executable.is_file():
        return False
    marker = root / "starting"
    try:
        if marker.exists() and time.time()-marker.stat().st_mtime > STARTING_SECONDS:
            marker.unlink()
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    os.close(fd)
    command = [str(executable)]
    if sys.platform == "darwin":
        bundle = next((p for p in executable.parents if p.suffix == ".app"), None)
        if bundle:
            command = ["/usr/bin/open", "-a", str(bundle)]
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        started()
        return False
    if command[0] == "/usr/bin/open":
        # open hands the launch to LaunchServices and exits at once; a non-zero
        # status means Mixar could not be opened, so nothing is starting.
        try:
            if process.wait(timeout=OPEN_WAIT_SECONDS) != 0:
                started()
                return False
        except subprocess.TimeoutExpired:
            pass
    return True
