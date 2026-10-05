# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway tool configuration. Every shelf path the tools used to hard-code is a setting now: the project root
(where a piece's meshes, rulings and rebuilds live) and the interpreters the batch tools run under. Environment
beats <lampway home>/settings.json beats the default; a tool path must stay inside the project root."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import settings as S  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for k in ("LAMPWAY_PROJECT_ROOT", "LAMPWAY_PYTHON_SCIENCE", "LAMPWAY_PYTHON_BROWSER", "LAMPWAY_BLENDER", "LAMPWAY_NICE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))


def test_defaults_live_under_the_lampway_home(tmp_path):
    s = S.load()
    assert s.project_root == tmp_path / "home" / "projects"
    assert s.nice == 15 and s.python_science is None and s.python_browser is None and s.blender is None


def test_the_settings_file_overrides_the_default_and_the_environment_overrides_the_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"project_root": "/data/p", "python_science": "/x/py", "nice": 10}))
    s = S.load()
    assert (s.project_root, s.python_science, s.nice) == (Path("/data/p"), Path("/x/py"), 10)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", "/env/root")
    monkeypatch.setenv("LAMPWAY_NICE", "5")
    s = S.load()
    assert (s.project_root, s.nice) == (Path("/env/root"), 5)


def test_a_corrupt_settings_file_is_ignored_not_fatal(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text("{nope")
    assert S.load().nice == 15


def test_save_round_trips_and_writes_only_what_is_set(tmp_path):
    s = S.load()
    s.project_root = tmp_path / "proj"
    s.python_science = Path("/opt/sci/bin/python")
    S.save(s)
    assert json.loads((tmp_path / "home" / "settings.json").read_text()) == {
        "project_root": str(tmp_path / "proj"), "python_science": "/opt/sci/bin/python", "nice": 15}
    assert S.load().python_science == Path("/opt/sci/bin/python")


def test_relative_paths_resolve_under_the_project_root(tmp_path):
    root = tmp_path / "proj"
    assert S.resolve_in_root("chest/mesh.fbx", root) == root / "chest" / "mesh.fbx"


def test_an_absolute_path_inside_the_root_is_allowed(tmp_path):
    root = tmp_path / "proj"
    assert S.resolve_in_root(str(root / "a" / "b.npy"), root) == root / "a" / "b.npy"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.txt", "chest/../../x"])
def test_a_path_outside_the_root_is_refused(tmp_path, bad):
    with pytest.raises(S.PathOutsideProject):
        S.resolve_in_root(bad, tmp_path / "proj")


def test_a_symlink_out_of_the_root_is_refused(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "secret").mkdir()
    (root / "link").symlink_to(tmp_path / "secret")
    with pytest.raises(S.PathOutsideProject):
        S.resolve_in_root("link/file", root)


def test_interpreter_report_says_which_exist(tmp_path):
    py = tmp_path / "py"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    s = S.load()
    s.python_science = py
    s.python_browser = tmp_path / "missing"
    rep = S.interpreter_report(s)
    assert rep["python_science"] == {"path": str(py), "exists": True}
    assert rep["python_browser"] == {"path": str(tmp_path / "missing"), "exists": False}
    assert rep["blender"]["exists"] is True or rep["blender"]["path"] is None


# ---- the argument jail of run_tool (every path-like token of a batch tool's arguments)

def test_jail_args_resolves_every_path_token_inside_the_root_and_refuses_one_outside(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    out = S.jail_args(["demo/mesh.fbx", "--out=demo/x.npy", "name=demo/p.npz:12", "bare.png", "--flag", "7"], root)
    assert out == [str(root / "demo/mesh.fbx"), f"--out={root / 'demo/x.npy'}", f"name={root / 'demo/p.npz'}:12", "bare.png",
                   "--flag", "7"]
    for bad in (["/etc/hosts"], ["--out=/tmp/x"], ["name=../p.npz:12"], ["~/x"], [".."]):
        with pytest.raises(S.PathOutsideProject):
            S.jail_args(bad, root)


def test_the_image_backend_is_a_setting_so_the_app_does_not_depend_on_the_launchers_environment(tmp_path, monkeypatch):
    """The mesh-paint image stage ran `lampway_server.imagegen` without --backend, so inside the app the backend was
    whatever LAMPWAY_IMAGE_BACKEND the LAUNCHER happened to export (unset = the Tripo driver, which refuses count 1).
    It is a setting now, like every other interpreter choice."""
    assert "image_backend" in S._FIELDS
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"image_backend": "openrouter"}))
    assert S.load().image_backend == "openrouter"
    monkeypatch.setenv("LAMPWAY_IMAGE_BACKEND", "codex_cli")
    assert S.load().image_backend == "codex_cli"
    assert S.load({"LAMPWAY_HOME": str(home)}).image_backend == "openrouter"
