"""The ONE launcher through which every herdr invocation passes (specs/mrmak/01 + the captain's isolation ruling): Lampway runs its OWN herdr server on its own socket, every spawn carries the
full Lampway environment, nothing can reach the fleet's server, and the server is detached so Lampway or Blender dying never touches it."""
import os
import subprocess
from pathlib import Path

import pytest

from lampway_server.herdr import launcher as L

from .herdr_support import fleet_witness, lroot, needs_herdr, short_root, wait_for  # noqa: F401

pytestmark = needs_herdr


def test_the_environment_carries_every_variable_under_the_lampway_root_and_scrubs_the_fleets(monkeypatch, lroot):
    root = lroot
    for k, v in {"HERDR_PANE_ID": "w22G:p1", "HERDR_ENV": "1", "HERDR_WORKSPACE_ID": "w22G", "HERDR_SOCKET_PATH": "/home/x/.config/herdr/herdr.sock", "HERDR_TAB_ID": "t1"}.items():
        monkeypatch.setenv(k, v)                                                    # this very test runs inside a fleet pane
    env = L.env_for(root)
    for k in ("HOME", "XDG_CONFIG_HOME", "HERDR_SOCKET_PATH", "HERDR_CLIENT_SOCKET_PATH", "HERDR_CONFIG_PATH"):
        assert str(env[k]).startswith(str(root)), (k, env[k])
    assert not {"HERDR_PANE_ID", "HERDR_ENV", "HERDR_WORKSPACE_ID", "HERDR_TAB_ID"} & set(env)
    assert len(env["HERDR_SOCKET_PATH"]) < 100 and len(env["HERDR_CLIENT_SOCKET_PATH"]) < 100


def test_a_root_whose_socket_path_is_too_long_gets_a_short_socket_dir_inside_the_runtime_dir(tmp_path):
    deep = tmp_path
    for _ in range(8):
        deep = deep / "a_very_long_directory_name"
    env = L.env_for(deep)
    assert len(env["HERDR_SOCKET_PATH"]) < 100 and "lampway-herdr-" in env["HERDR_SOCKET_PATH"]
    assert not Path(env["HERDR_SOCKET_PATH"]).parent.exists()                                  # computing the path creates nothing in the runtime dir


def test_every_spawn_carries_the_lampway_socket_and_none_reaches_the_fleet(monkeypatch, lroot):
    seen = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def spy_run(cmd, *a, **k):
        seen.append((cmd, k.get("env")))
        return real_run(cmd, *a, **k)

    def spy_popen(cmd, *a, **k):
        seen.append((cmd, k.get("env")))
        return real_popen(cmd, *a, **k)
    monkeypatch.setattr(subprocess, "run", spy_run)
    monkeypatch.setattr(subprocess, "Popen", spy_popen)
    root = lroot
    try:
        L.server_status(root)
        L.start_server(root)
        assert wait_for(lambda: L.server_status(root).get("running"))
        L.run(root, ["workspace", "list"])
        L.run(root, ["api", "snapshot"])
    finally:
        L.stop_server(root, confirmed=True)
    herdr_calls = [(c, e) for c, e in seen if str(c[0]).endswith("herdr") or "systemd-run" in str(c[0]) and "herdr" in " ".join(map(str, c))]
    assert herdr_calls, seen
    for cmd, env in herdr_calls:
        env = env or {}
        text = " ".join(map(str, cmd))
        assert str(root) in (env.get("HERDR_SOCKET_PATH") or text), (cmd, env.get("HERDR_SOCKET_PATH"))
        assert "HERDR_PANE_ID" not in env


def test_the_launcher_refuses_to_run_without_a_lampway_socket_in_its_env(tmp_path, monkeypatch, lroot):
    root = lroot
    monkeypatch.setattr(L, "env_for", lambda r: {"PATH": os.environ["PATH"]})                   # a broken environment: no socket variable
    with pytest.raises(L.HerdrError, match="refusing to run herdr without the Lampway socket environment"):
        L.run(root, ["workspace", "list"])
    monkeypatch.setattr(L, "env_for", lambda r: {"PATH": os.environ["PATH"], "HERDR_SOCKET_PATH": os.path.expanduser("~/.config/herdr/herdr.sock")})     # the FLEET's socket
    with pytest.raises(L.HerdrError, match="refusing to run herdr without the Lampway socket environment"):
        L.run(root, ["workspace", "list"])


def test_only_the_launcher_module_spawns_processes():
    pkg = Path(L.__file__).parent
    for f in pkg.rglob("*.py"):
        if f.name == "launcher.py":
            continue
        text = f.read_text()
        assert "subprocess" not in text and "os.system" not in text and "Popen" not in text and "os.exec" not in text, f"{f.name} must go through launcher.run"


def test_the_server_starts_detached_records_how_and_stopping_needs_the_users_confirm(lroot):
    root = lroot
    out = L.start_server(root)
    try:
        assert out["method"] in ("systemd", "setsid") and wait_for(lambda: L.server_status(root).get("running"))
        assert L.server_info(root)["method"] == out["method"]
        with pytest.raises(L.HerdrError, match="explicit user action"):
            L.stop_server(root, confirmed=False)
        assert L.server_status(root)["running"]
        again = L.start_server(root)
        assert again["already_running"] is True                                               # idempotent: never a second server
    finally:
        L.stop_server(root, confirmed=True)
    assert wait_for(lambda: not L.server_status(root).get("running"))


def test_the_lampway_server_never_changes_the_fleets_server_or_files(lroot):
    before = fleet_witness()
    assert before["running"], "the fleet's herdr is expected to be running on this machine"
    root = lroot
    try:
        L.start_server(root)
        assert wait_for(lambda: L.server_status(root).get("running"))
        L.run(root, ["workspace", "create", "--label", "lampway-isolation-marker-7731", "--no-focus"])
        snap = L.run(root, ["api", "snapshot"])
        assert "lampway-isolation-marker-7731" in snap
        after = fleet_witness()
    finally:
        L.stop_server(root, confirmed=True)
    assert after["running"] and after["socket"] == before["socket"] and after["socket_inode"] == before["socket_inode"] and after["version"] == before["version"]
    assert "lampway-isolation-marker-7731" not in after["raw"] and "lampway-isolation-marker-7731" not in after["labels"]
    fleet_dir = Path(os.path.expanduser("~/.config/herdr"))
    for f in fleet_dir.glob("*.json*"):
        assert "lampway-isolation-marker-7731" not in f.read_text(errors="replace")
    for f in list(fleet_dir.glob("*.log")):
        assert "lampway-isolation-marker-7731" not in f.read_text(errors="replace")[-200000:]
    assert (root / "home" / ".config" / "herdr").is_dir()                                     # the Lampway server's own state lives under the Lampway root
