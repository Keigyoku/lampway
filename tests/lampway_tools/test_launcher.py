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
    (t / "build/Prod/bin/mixar.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>"
        "<rect width='32' height='32'/></svg>")
    return t


@pytest.fixture
def env(tmp_path):
    port = _free_port()
    stub = exe(tmp_path / "stub_server.sh", f'echo $$ > {tmp_path}/server.pid; echo "provider=$LAMPWAY_PROVIDER port=$LAMPWAY_PORT state=$LAMPWAY_STATE_DIR" > {tmp_path}/server.txt; env | sort > {tmp_path}/server_env.txt; exec sleep 600')
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


KEY = "sk-or-v1-" + "9a8b" * 16


def test_openrouter_takes_the_key_by_file_reference_sets_the_budget_and_starts_a_fresh_spend_log(tree, env, tmp_path):
    e, port = env
    keyfile = tmp_path / "keys.env"
    keyfile.write_text(f"OPENROUTER_API_KEY={KEY}\n")
    log = tmp_path / "home/server-state/openrouter_spend.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"t": 1, "label": "old", "cost_usd": 9}\n')
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"x")
    r = lampway(tree, e, "--env", "Prod", "--provider", "openrouter", "--openrouter-key-file", str(keyfile), "--budget", "2.5",
                "--image-backend", "openrouter", str(blend))
    assert r.returncode == 0, r.stdout + r.stderr
    server_env = (tmp_path / "server_env.txt").read_text()
    app = (tmp_path / "app.txt").read_text()
    for text in (server_env, app):
        assert f"LAMPWAY_OPENROUTER_KEY_FILE={keyfile}" in text and f"LAMPWAY_SPEND_LOG={log}" in text
        assert "LAMPWAY_OPENROUTER_BUDGET_USD=2.5" in text
    assert "LAMPWAY_PROVIDER=openrouter" in server_env and "LAMPWAY_IMAGE_BACKEND=openrouter" in app
    assert not log.exists() or log.read_text() == "", "a new session starts with an empty spend log"
    assert (log.parent / "openrouter_spend.jsonl.prev").read_text().startswith('{"t": 1')
    for text in (r.stdout, r.stderr, server_env, app):
        assert KEY not in text, "the key value must never appear in anything the launcher prints or exports"


def test_openrouter_without_any_key_reference_is_refused_without_starting_anything(tree, env, tmp_path):
    e, _ = env
    r = lampway(tree, e, "--env", "Prod", "--provider", "openrouter")
    assert r.returncode == 1 and "error:" in r.stdout and "OPENROUTER_API_KEY" in r.stdout
    assert not (tmp_path / "server.pid").exists() and not (tmp_path / "app.txt").exists()


def test_the_plan_names_the_models_and_the_budget_but_never_a_key(tree, env, tmp_path):
    e, _ = env
    keyfile = tmp_path / "keys.env"
    keyfile.write_text(f"OPENROUTER_API_KEY={KEY}\n")
    r = lampway(tree, e, "--plan", "--env", "Prod", "--provider", "openrouter", "--openrouter-key-file", str(keyfile))
    assert r.returncode == 0, r.stdout
    for needle in ("main_model: anthropic/claude-sonnet-5.5", "swarm_model: deepseek/deepseek-v4.1-flash", "budget_usd: 3", f"key_file: {keyfile}"):
        assert needle in r.stdout, needle
    assert KEY not in r.stdout


def test_the_app_is_told_which_python_and_directory_run_the_servers_image_backend(tree, env, tmp_path):
    e, _ = env
    py = tmp_path / "serverpy"
    py.write_text("")
    (tree / "server").mkdir()
    e = dict(e, LAMPWAY_SERVER_PYTHON=str(py))
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"x")
    r = lampway(tree, e, "--env", "Prod", str(blend))
    assert r.returncode == 0, r.stdout + r.stderr
    app = (tmp_path / "app.txt").read_text()
    assert f"LAMPWAY_PYTHON_SERVER={py}" in app and f"LAMPWAY_SERVER_DIR={tree}/server" in app


def test_the_server_is_pointed_at_the_models_the_build_bundled(tree, env, tmp_path):
    e, _ = env
    models = tree / "build/Prod/bin/5.2/datafiles/lampway/models"
    r = lampway(tree, e, "--plan", "--env", "Prod")
    assert f"models: {models} (absent: the Vault offers the one-click fetch)" in r.stdout
    models.mkdir(parents=True)
    r = lampway(tree, e, "--plan", "--env", "Prod")
    assert f"models: {models} (bundled)" in r.stdout
    r = lampway(tree, e, "--env", "Prod")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"LAMPWAY_MODELS_DIR={models}\n" in (tmp_path / "server_env.txt").read_text()


def test_without_bundled_models_the_server_gets_no_models_dir(tree, env, tmp_path):
    e, _ = env
    assert lampway(tree, e, "--env", "Prod").returncode == 0
    assert "LAMPWAY_MODELS_DIR=" not in (tmp_path / "server_env.txt").read_text()


# ------------------------------------------------------------------------------------------------ Connections, migration step 2 (C7)
def _state_env(env, tmp_path):
    e, port = env
    e = dict(e, XDG_STATE_HOME=str(tmp_path / "xdgstate"))
    e.pop("LAMPWAY_KEYRING_FILE", None)
    e.pop("LAMPWAY_SECRETS_DIR", None)
    return e, port


def test_old_keyring_file_moved_once(tree, env, tmp_path):
    """The client's login pair leaves the agent sandbox's roots: $LAMPWAY_HOME/keyring.json moves to the state dir, once, verified."""
    e, _ = _state_env(env, tmp_path)
    old = tmp_path / "home" / "keyring.json"
    old.parent.mkdir(parents=True)
    pair = '{"LampwaySafeStorage": {"AccessToken": "tok-FAKE", "RefreshToken": "ref-FAKE"}}'
    old.write_text(pair)
    old.chmod(0o600)
    new = tmp_path / "xdgstate" / "lampway" / "keyring.json"
    r = lampway(tree, e, "--env", "Prod", "--no-server")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not old.exists() and new.read_text() == pair
    assert stat.S_IMODE(new.stat().st_mode) == 0o600 and stat.S_IMODE(new.parent.stat().st_mode) == 0o700
    assert f"LAMPWAY_KEYRING_FILE={new}" in (tmp_path / "app.txt").read_text()
    log = (tmp_path / "home" / "server-state" / "connections" / "log.jsonl").read_text()
    assert '"action": "moved"' in log and "tok-FAKE" not in log and "tok-FAKE" not in r.stdout
    r2 = lampway(tree, e, "--env", "Prod", "--no-server")
    assert r2.returncode == 0 and new.read_text() == pair and log == (tmp_path / "home" / "server-state" / "connections" / "log.jsonl").read_text()


def test_an_existing_new_keyring_is_never_overwritten(tree, env, tmp_path):
    e, _ = _state_env(env, tmp_path)
    old = tmp_path / "home" / "keyring.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"a": {"u": "OLD"}}')
    new = tmp_path / "xdgstate" / "lampway" / "keyring.json"
    new.parent.mkdir(parents=True)
    new.write_text('{"a": {"u": "NEW"}}')
    r = lampway(tree, e, "--env", "Prod", "--no-server")
    assert r.returncode == 0 and new.read_text() == '{"a": {"u": "NEW"}}' and old.exists()


def test_the_server_gets_a_secrets_dir_outside_the_lampway_home(tree, env, tmp_path):
    e, _ = _state_env(env, tmp_path)
    r = lampway(tree, e, "--env", "Prod", "--provider", "mock")
    assert r.returncode == 0, r.stdout + r.stderr
    server_env = (tmp_path / "server_env.txt").read_text()
    assert f"LAMPWAY_SECRETS_DIR={tmp_path}/xdgstate/lampway-secrets" in server_env
    plan = lampway(tree, e, "--env", "Prod", "--plan").stdout
    assert f"secrets_dir: {tmp_path}/xdgstate/lampway-secrets" in plan and f"keyring_file: {tmp_path}/xdgstate/lampway/keyring.json" in plan


@pytest.mark.parametrize('flag', ['--help', '-h'])
def test_help_is_successful_without_build_or_launch_and_prints_no_secret(tree, env, tmp_path, flag):
    e, _ = env
    shutil.rmtree(tree / 'build')
    e['OPENROUTER_API_KEY'] = 'help-secret-fixture'
    r = lampway(tree, e, flag)
    assert r.returncode == 0, r.stdout + r.stderr
    for option in ('--env', '--copy', '--provider', '--port', '--bridge-port', '--openrouter-key-file', '--budget', '--image-backend', '--no-server', '--system-keyring', '--plan', '--install-desktop', '--uninstall-desktop'):
        assert option in r.stdout
    assert 'Usage:' in r.stdout and 'help-secret-fixture' not in r.stdout + r.stderr
    assert not (tmp_path / 'home').exists()
    assert not (tmp_path / 'server.pid').exists() and not (tmp_path / 'app.txt').exists()
