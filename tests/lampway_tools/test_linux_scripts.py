# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scripts/unix/run.sh (the Linux launch + Wayland/X11 switch) and install_desktop_entry.sh, taken from Shiro836's
mixar-linux (16d7f0ed) and made Lampway's: the switch is LAMPWAY_LINUX_BACKEND (the fork's MIXAR_LINUX_BACKEND still
works as a fallback), the desktop entry is lampway.desktop with the icon name `lampway`, and it starts the Lampway
launcher, so a menu launch brings up the server too.

Each test runs the REAL script against a throwaway tree with a fake binary, so no display or build is needed."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tree(tmp_path, with_launcher=True):
    """A copy of the scripts around a fake build/Dev/bin/mixar that prints what it was started with."""
    t = tmp_path / "tree"
    (t / "scripts/unix").mkdir(parents=True)
    (t / "scripts/lampway").mkdir(parents=True)
    for name in ("run.sh", "install_desktop_entry.sh"):
        shutil.copy(ROOT / "scripts/unix" / name, t / "scripts/unix" / name)
    if with_launcher:
        (t / "scripts/lampway/lampway").write_text("#!/bin/sh\n")
        (t / "scripts/lampway/lampway").chmod(0o755)
    for env in ("Dev", "Prod"):
        bin_ = t / "build" / env / "bin"
        bin_.mkdir(parents=True)
        exe = bin_ / "mixar"
        exe.write_text('#!/bin/sh\necho "ARGS:$*"\nif [ "${WAYLAND_DISPLAY+set}" = set ]; then echo "WAYLAND_DISPLAY=[$WAYLAND_DISPLAY]"; else echo "WAYLAND_DISPLAY unset"; fi\n')
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        (bin_ / "mixar.desktop").write_text("[Desktop Entry]\nName=Lampway\nExec=mixar %f\nIcon=mixar\nType=Application\n")
        (bin_ / "mixar.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return t


def _run(tree, *args, env=None, script="run.sh"):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("MIXAR_", "LAMPWAY_", "WAYLAND", "DISPLAY"))}
    e.update(env or {})
    return subprocess.run([str(tree / "scripts/unix" / script), *args], capture_output=True, text=True, env=e)


def test_auto_leaves_the_wayland_display_alone(tmp_path):
    t = _tree(tmp_path)
    r = _run(t, "Dev", "a.blend", env={"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"})
    assert r.returncode == 0, r.stderr
    assert "ARGS:a.blend" in r.stdout and "WAYLAND_DISPLAY=[wayland-1]" in r.stdout


def test_x11_sets_wayland_display_to_empty_not_unset(tmp_path):
    t = _tree(tmp_path)
    r = _run(t, "Dev", env={"LAMPWAY_LINUX_BACKEND": "x11", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"})
    assert r.returncode == 0, r.stderr
    assert "WAYLAND_DISPLAY=[]" in r.stdout                      # unset would let libwayland default to wayland-0
    assert "LAMPWAY_LINUX_BACKEND=x11" in r.stdout


def test_x11_without_a_display_is_refused_naming_the_variable(tmp_path):
    r = _run(_tree(tmp_path), "Dev", env={"LAMPWAY_LINUX_BACKEND": "x11"})
    assert r.returncode == 1 and "LAMPWAY_LINUX_BACKEND=x11" in r.stderr and "DISPLAY" in r.stderr


def test_an_unknown_backend_is_refused(tmp_path):
    r = _run(_tree(tmp_path), "Dev", env={"LAMPWAY_LINUX_BACKEND": "wayland", "DISPLAY": ":0"})
    assert r.returncode == 1 and "must be 'auto' or 'x11'" in r.stderr and "LAMPWAY_LINUX_BACKEND" in r.stderr


def test_the_forks_old_variable_still_works_and_the_lampway_one_wins(tmp_path):
    t = _tree(tmp_path)
    old = _run(t, "Dev", env={"MIXAR_LINUX_BACKEND": "x11", "DISPLAY": ":0"})
    assert "WAYLAND_DISPLAY=[]" in old.stdout
    both = _run(t, "Dev", env={"MIXAR_LINUX_BACKEND": "x11", "LAMPWAY_LINUX_BACKEND": "auto", "DISPLAY": ":0", "WAYLAND_DISPLAY": "w"})
    assert "WAYLAND_DISPLAY=[w]" in both.stdout


def test_the_dot_env_key_is_read_and_nothing_else_from_it(tmp_path):
    t = _tree(tmp_path)
    (t / ".env").write_text('OTHER_SETTING=leaked\nLAMPWAY_LINUX_BACKEND="x11"   # force xwayland\n')
    r = _run(t, "Dev", env={"DISPLAY": ":0"})
    assert "WAYLAND_DISPLAY=[]" in r.stdout and "OTHER_SETTING" not in r.stdout


def test_a_missing_binary_is_reported(tmp_path):
    t = _tree(tmp_path)
    r = _run(t, "Nope")
    assert r.returncode == 1 and "binary not found" in r.stderr


# ---- the desktop entry

def _install(t, tmp_path, *args):
    data = tmp_path / "data"
    env = {"XDG_DATA_HOME": str(data), "HOME": str(tmp_path / "home")}
    return _run(t, *args, env=env, script="install_desktop_entry.sh"), data


def test_the_entry_is_lampway_desktop_starting_the_lampway_launcher(tmp_path):
    t = _tree(tmp_path)
    r, data = _install(t, tmp_path, "Dev")
    assert r.returncode == 0, r.stdout + r.stderr
    entry = (data / "applications" / "lampway.desktop").read_text()
    assert f'Exec="{t}/scripts/lampway/lampway" %f' in entry
    assert "Icon=lampway" in entry and "Name=Lampway" in entry
    assert (data / "icons/hicolor/scalable/apps/lampway.svg").exists()
    assert not (data / "applications" / "mixar.desktop").exists()      # never the Mixar names


def test_uninstall_removes_only_its_own_files(tmp_path):
    t = _tree(tmp_path)
    _, data = _install(t, tmp_path, "Dev")
    other = data / "applications" / "other.desktop"
    other.write_text("x")
    r, _ = _install(t, tmp_path, "--uninstall")
    assert r.returncode == 0
    assert other.exists()
    assert not (data / "applications" / "lampway.desktop").exists()
    assert not (data / "icons/hicolor/scalable/apps/lampway.svg").exists()


def test_the_installer_writes_nothing_outside_the_data_home(tmp_path):
    t = _tree(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _install(t, tmp_path, "Dev")
    assert list(home.iterdir()) == []


def test_a_missing_launcher_is_refused(tmp_path):
    t = _tree(tmp_path, with_launcher=False)
    r, _ = _install(t, tmp_path, "Dev")
    assert r.returncode == 1 and "launcher" in r.stderr
