# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scripts/lampway/lampway: the one command. It starts our server on localhost, starts Lampway pointed at it with the tools and
the bridge enabled (through scripts/unix/run.sh, which owns the Wayland/X11 switch), opens a given .blend (a COPY with --copy: his
file is never saved over), and stops the server it started when the app exits. Tested with a fake binary and a stub server."""

import os
import shutil
import stat
import subprocess
import sys
import time
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def exe(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def tree(tmp_path):
    """The scripts around a fake build and a stub server command."""
    t = tmp_path / "tree"
    for d in ("scripts/lampway", "scripts/unix"):
        (t / d).mkdir(parents=True)
    for name in ("lampway",):
        shutil.copy(ROOT / "scripts/lampway" / name, t / "scripts/lampway" / name)
    for name in ("run.sh", "install_desktop_entry.sh"):
        shutil.copy(ROOT / "scripts/unix" / name, t / "scripts/unix" / name)
    (t / "build/Prod/bin").mkdir(parents=True)
    exe(t / "build/Prod/bin/mixar", f'echo "APP argv: $@" > {tmp_path}/app.txt; env | sort >> {tmp_path}/app.txt; '
                                    f'[ -f "$LAMPWAY_SERVER_PID_FILE" ] && echo "server_alive_at_start=yes" >> {tmp_path}/app.txt; sleep "${{APP_SLEEP:-0}}"')
    (t / "build/Prod/bin/mixar.desktop").write_text("[Desktop Entry]\nName=Lampway\nExec=mixar %f\nIcon=mixar\nType=Application\n")
    (t / "build/Prod/bin/mixar.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return t


@pytest.fixture
def env(tmp_path):
    port = _free_port()
    stub = exe(tmp_path / "stub_server.sh", f'echo $$ > {tmp_path}/server.pid; echo "provider=$LAMPWAY_PROVIDER port=$LAMPWAY_PORT state=$LAMPWAY_STATE_DIR" > {tmp_path}/server.txt; exec sleep 600')
    e = {k: v for k, v in os.environ.items() if not k.startswith(("LAMPWAY_", "MIXAR_", "DISPLAY", "WAYLAND"))}
    e.update({"LAMPWAY_HOME": str(tmp_path / "home"), "LAMPWAY_SERVER_CMD": str(stub), "LAMPWAY_SERVER_PORT": str(port),
              "LAMPWAY_SKIP_SERVER_WAIT": "1", "HOME": str(tmp_path / "userhome")})
    return e, port


def lampway(tree, env, *args, check=False):
    return subprocess.run([str(tree / "scripts/lampway/lampway"), *args], capture_output=True, text=True, env=env, timeout=60)


def test_plan_shows_what_a_run_would_use_and_changes_nothing(tree, env, tmp_path):
    e, port = env
    r = lampway(tree, e, "--plan", "--env", "Prod", "scene.blend")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for needle in (f"server_url: http://127.0.0.1:{port}", "build_env: Prod", f"binary: {tree}/build/Prod/bin/mixar", "bridge_port: 9876",
                   "keyring: file", "provider: mock", "blend: scene.blend"):
        assert needle in out, needle
    assert not (tmp_path / "server.pid").exists() and not (tmp_path / "app.txt").exists()
    assert not (tmp_path / "home").exists()


def test_unknown_flags_exit_2_and_a_missing_build_is_refused_on_stdout(tree, env):
    e, _ = env
    assert lampway(tree, e, "--nope").returncode == 2
    shutil.rmtree(tree / "build")
    r = lampway(tree, e)
    assert r.returncode == 1 and "error:" in r.stdout and "build_linux.sh" in r.stdout


def test_a_run_starts_the_server_then_the_app_with_the_clients_environment_then_stops_only_its_own_server(tree, env, tmp_path):
    e, port = env
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"x")
    r = lampway(tree, e, "--env", "Prod", "--bridge-port", "19999", "--provider", "mock", str(blend))
    assert r.returncode == 0, r.stdout + r.stderr
    app = (tmp_path / "app.txt").read_text()
    assert f"APP argv: {blend}" in app
    assert f"LAMPWAY_BACKEND_URL=http://127.0.0.1:{port}" in app and "LAMPWAY_BRIDGE_PORT=19999" in app
    assert "PYTHON_KEYRING_BACKEND=mixar.modules.lampway_tools.keyring_file.FileKeyring" in app
    assert f"LAMPWAY_BRIDGE_DIR={tmp_path}/home/bridge" in app and f"LAMPWAY_PROJECT_ROOT={tmp_path}/home/projects" in app
    assert f"XDG_CONFIG_HOME={tmp_path}/home/config" in app                        # an isolated profile: his stock Mixar profile is untouched
    assert "LAMPWAY_KEYRING_FILE=" in app
    assert "provider=mock" in (tmp_path / "server.txt").read_text() and f"port={port}" in (tmp_path / "server.txt").read_text()
    pid = int((tmp_path / "server.pid").read_text())
    time.sleep(0.3)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)                                                                # the server we started is gone with the app


def test_copy_opens_a_copy_and_never_the_original(tree, env, tmp_path):
    e, _ = env
    blend = tmp_path / "his.blend"
    blend.write_bytes(b"BLENDER-v500original")
    r = lampway(tree, e, "--env", "Prod", "--copy", str(blend))
    assert r.returncode == 0, r.stdout + r.stderr
    argv = [l for l in (tmp_path / "app.txt").read_text().splitlines() if l.startswith("APP argv:")][0]
    opened = argv.split("APP argv: ")[1].strip()
    assert opened != str(blend) and opened.startswith(str(tmp_path / "home" / "copies")) and opened.endswith(".blend")
    assert Path(opened).read_bytes() == b"BLENDER-v500original"
    assert blend.read_bytes() == b"BLENDER-v500original"


def test_a_missing_blend_is_refused_before_anything_starts(tree, env, tmp_path):
    e, _ = env
    r = lampway(tree, e, "--env", "Prod", "--copy", str(tmp_path / "nope.blend"))
    assert r.returncode == 1 and "not found" in r.stdout
    assert not (tmp_path / "server.pid").exists()


def test_no_server_leaves_the_server_alone_and_still_points_the_app_at_it(tree, env, tmp_path):
    e, port = env
    r = lampway(tree, e, "--env", "Prod", "--no-server")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (tmp_path / "server.pid").exists()
    assert f"LAMPWAY_BACKEND_URL=http://127.0.0.1:{port}" in (tmp_path / "app.txt").read_text()


def test_the_backend_switch_goes_through_run_sh(tree, env, tmp_path):
    e, _ = env
    e = {**e, "LAMPWAY_LINUX_BACKEND": "x11", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}
    r = lampway(tree, e, "--env", "Prod", "--no-server")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WAYLAND_DISPLAY=\n" in (tmp_path / "app.txt").read_text()                  # run.sh's x11 branch: set but empty


def test_the_system_keyring_flag_leaves_the_keyring_alone(tree, env, tmp_path):
    e, _ = env
    r = lampway(tree, e, "--env", "Prod", "--no-server", "--system-keyring")
    assert r.returncode == 0
    assert "PYTHON_KEYRING_BACKEND" not in (tmp_path / "app.txt").read_text()


def test_install_desktop_hands_over_to_the_installer(tree, env, tmp_path):
    e, _ = env
    e["XDG_DATA_HOME"] = str(tmp_path / "data")
    r = lampway(tree, e, "--env", "Prod", "--install-desktop")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "data/applications/lampway.desktop").exists()


def test_a_port_already_serving_something_else_is_refused(tree, env, tmp_path):
    e, port = env
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.listen(1)
    try:
        r = lampway(tree, e, "--env", "Prod")
        assert r.returncode == 1 and "in use" in r.stdout and not (tmp_path / "app.txt").exists()
    finally:
        s.close()
