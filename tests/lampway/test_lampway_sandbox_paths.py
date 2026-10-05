# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The sandbox's file-system gate: every path a script reads or writes is resolved (realpath) and must lie inside an
allowed root by common-path containment, so a prefix collision (``/tmp/root`` vs ``/tmp/rootx``) and a symlink that
points out of a root are refused. The same gate sits behind ``open()``, numpy's file functions and the file-bearing
``bpy.ops`` operators, which the old sandbox did not cover at all (``bpy.ops.wm.save_as_mainfile`` and
``numpy.load(allow_pickle=True)`` reached the real process)."""

import importlib
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import numpy
import pytest

_pkg = ModuleType("_sandbox_path_tests")
_pkg.__path__ = [str(Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/space_mixie_chat/core")]
sys.modules[_pkg.__name__] = _pkg
sandbox_paths = importlib.import_module("_sandbox_path_tests.sandbox_paths")
sandbox_modules = importlib.import_module("_sandbox_path_tests.sandbox_modules")


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """A temp dir and a Lampway home of this test's own; nothing else is readable or writable."""
    temp = tmp_path / "tmp"
    temp.mkdir()
    home = tmp_path / "home"
    (home / "projects").mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.setenv("LAMPWAY_HOME", str(home))
    monkeypatch.delenv("LAMPWAY_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("LAMPWAY_SANDBOX_READ_ROOTS", raising=False)
    return {"temp": temp, "project": home / "projects", "outside": tmp_path / "outside"}


def test_a_write_outside_every_root_is_refused_and_one_inside_the_temp_dir_is_not(roots):
    roots["outside"].mkdir()
    with pytest.raises(PermissionError):
        sandbox_paths.check_write(roots["outside"] / "f.txt")
    assert sandbox_paths.check_write(roots["temp"] / "f.txt") == os.path.realpath(roots["temp"] / "f.txt")


def test_a_prefix_collision_directory_is_not_inside_the_root(roots):
    twin = Path(str(roots["temp"]) + "x")
    twin.mkdir()
    with pytest.raises(PermissionError):
        sandbox_paths.check_write(twin / "f.txt")


def test_a_symlink_inside_a_root_that_points_out_is_refused(roots):
    roots["outside"].mkdir()
    (roots["temp"] / "link").symlink_to(roots["outside"], target_is_directory=True)
    with pytest.raises(PermissionError):
        sandbox_paths.check_write(roots["temp"] / "link" / "f.txt")


def test_a_read_outside_every_root_is_refused_and_the_project_root_is_readable(roots):
    roots["outside"].mkdir()
    secret = roots["outside"] / "secret"
    secret.write_text("x")
    with pytest.raises(PermissionError):
        sandbox_paths.check_read(secret)
    piece = roots["project"] / "piece.json"
    piece.write_text("{}")
    assert sandbox_paths.check_read(piece) == os.path.realpath(piece)


def test_restricted_open_refuses_a_read_outside_the_roots(roots):
    roots["outside"].mkdir()
    secret = roots["outside"] / "secret"
    secret.write_text("x")
    with pytest.raises(PermissionError):
        sandbox_modules.restricted_open(secret)


def test_numpy_load_with_pickles_allowed_is_refused_even_inside_the_temp_dir(roots):
    path = roots["temp"] / "a.npy"
    numpy.save(path, numpy.zeros(1))
    np = sandbox_modules.safe_module(numpy)
    with pytest.raises(PermissionError, match="pickle"):
        np.load(str(path), allow_pickle=True)
    assert np.load(str(path)).shape == (1,)


def test_numpy_save_outside_the_roots_is_refused(roots):
    roots["outside"].mkdir()
    np = sandbox_modules.safe_module(numpy)
    with pytest.raises(PermissionError):
        np.save(str(roots["outside"] / "a.npy"), numpy.zeros(1))
    assert not (roots["outside"] / "a.npy").exists()


def test_numpy_file_format_internals_are_not_reachable(roots):
    np = sandbox_modules.safe_module(numpy)
    with pytest.raises(AttributeError):
        np.lib.format
    with pytest.raises(AttributeError):
        np.lib.npyio


def test_an_array_method_that_writes_a_file_is_gated(roots):
    roots["outside"].mkdir()
    gated = sandbox_paths.guard_file_method(numpy.zeros(1).tofile)
    with pytest.raises(PermissionError):
        gated(str(roots["outside"] / "a.bin"))
    assert not (roots["outside"] / "a.bin").exists()
    assert sandbox_paths.guard_file_method(len) is len, "an unrelated callable passes through untouched"


class _Op:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"FINISHED"}


def test_a_saving_operator_with_a_filepath_outside_the_roots_is_refused_before_it_runs(roots):
    op = _Op()
    gated = sandbox_paths.guard_operator("wm.save_as_mainfile", op)
    with pytest.raises(PermissionError):
        gated(filepath=str(roots["outside"] / "x.blend"), copy=True)
    assert op.calls == []


def test_a_saving_operator_inside_the_temp_dir_runs(roots):
    op = _Op()
    gated = sandbox_paths.guard_operator("wm.save_as_mainfile", op)
    assert gated(filepath=str(roots["temp"] / "x.blend"), copy=True) == {"FINISHED"}
    assert len(op.calls) == 1


def test_an_operator_that_runs_python_from_a_file_is_refused_outright(roots):
    op = _Op()
    gated = sandbox_paths.guard_operator("script.python_file_run", op)
    with pytest.raises(PermissionError):
        gated(filepath=str(roots["temp"] / "x.py"))
    assert op.calls == []


def test_an_operator_without_a_path_argument_is_untouched(roots):
    op = _Op()
    gated = sandbox_paths.guard_operator("mesh.primitive_cube_add", op)
    assert gated(size=2) == {"FINISHED"}
    assert op.calls == [((), {"size": 2})]


def test_bpy_ops_resolve_through_the_gate(roots):
    """The proxy wraps every operator reached through ``bpy.ops.<mod>.<op>``: a stand-in bpy with the real
    module-and-getattr shape Blender's bpy/ops.py builds."""
    bpy = ModuleType("bpy")
    ops = ModuleType("bpy.ops")
    wm = ModuleType("bpy.ops.wm")
    op = _Op()
    wm.__getattr__ = lambda name: op if name == "save_as_mainfile" else (_ for _ in ()).throw(AttributeError(name))
    ops.wm = wm
    bpy.ops = ops
    proxied = sandbox_modules.safe_module(bpy)
    with pytest.raises(PermissionError):
        proxied.ops.wm.save_as_mainfile(filepath=str(roots["outside"] / "x.blend"))
    assert op.calls == []
