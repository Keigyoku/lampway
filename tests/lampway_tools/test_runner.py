# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tool runner: which interpreter runs which ported tool, niced, with Lampway's configuration in its environment.

Kinds: 'blender' (blender -b -P tool -- args: the Lampway binary itself unless a Blender is configured),
'numpy' (numpy/Pillow only: the configured science python, else the app's bundled one), 'science' (scipy/OpenCV:
the configured science python, nothing else will do)."""

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import runner as R  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts"


def fake_exe(path, body='echo "ARGV:$@"; echo "NICE_OK"; env | grep ^LAMPWAY_ | sort'):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    for k in ("LAMPWAY_PROJECT_ROOT", "LAMPWAY_PYTHON_SCIENCE", "LAMPWAY_BLENDER"):
        monkeypatch.delenv(k, raising=False)
    s = S.load()
    s.project_root = tmp_path / "proj"
    s.blender = fake_exe(tmp_path / "blender")
    s.python_science = fake_exe(tmp_path / "sci")
    return s


def test_every_tool_names_an_existing_script():
    assert len(R.TOOLS) >= 17
    for name, t in R.TOOLS.items():
        assert (SCRIPTS / t.script).exists(), (name, t.script)
        assert t.kind in ("blender", "numpy", "science")


def test_a_blender_tool_runs_as_blender_dash_b_dash_P_with_args_after_the_double_dash(cfg):
    cmd = R.command("patch_holes", ["a", "b"], cfg)
    assert cmd[:3] == ["nice", "-n", "15"]
    assert cmd[3:6] == [str(cfg.blender), "-b", "--python-exit-code"]
    assert cmd[6] == "1" and cmd[7] == "-P" and cmd[8].endswith("scripts/partseg/patch_holes.py")
    assert cmd[9:] == ["--", "a", "b"]


def test_a_science_tool_runs_under_the_configured_python(cfg):
    cmd = R.command("relief_project", ["x"], cfg)
    assert cmd[3] == str(cfg.python_science) and cmd[4].endswith("scripts/texlib/relief_project.py") and cmd[5:] == ["x"]


def test_a_science_tool_without_a_science_python_is_refused_naming_the_setting(cfg):
    cfg.python_science = None
    with pytest.raises(R.ToolUnavailable) as e:
        R.command("material_masks", [], cfg)
    assert "LAMPWAY_PYTHON_SCIENCE" in str(e.value) and "scipy" in str(e.value)


def test_a_numpy_tool_falls_back_to_the_bundled_python(cfg):
    cfg.python_science = None
    cmd = R.command("place_piece", ["o"], cfg)
    assert cmd[3] == sys.executable


def test_the_run_captures_output_environment_and_exit_code(cfg, tmp_path):
    res = R.run("patch_holes", ["x"], cfg)
    assert res.rc == 0 and "ARGV:-b --python-exit-code 1 -P" in res.stdout
    assert "LAMPWAY_BRIDGE_PORT=0" in res.stdout            # a batch job never takes the live window's bridge port
    assert f"LAMPWAY_PROJECT_ROOT={cfg.project_root}" in res.stdout


def test_the_tool_environment_carries_the_texture_library_settings(cfg):
    cfg.tiles_dir = Path("/lib/tiles")
    cfg.ambientcg_dir = Path("/lib/acg")
    cfg.hdri = Path("/lib/studio.hdr")
    res = R.run("patch_holes", [], cfg)
    assert "LAMPWAY_TILES_DIR=/lib/tiles" in res.stdout and "LAMPWAY_AMBIENTCG_DIR=/lib/acg" in res.stdout
    assert "LAMPWAY_HDRI=/lib/studio.hdr" in res.stdout


def test_a_failing_tool_reports_rc_and_stays_a_result_not_an_exception(cfg, tmp_path):
    cfg.blender = fake_exe(tmp_path / "bad", 'echo "boom"; exit 3')
    res = R.run("patch_holes", [], cfg)
    assert res.rc == 3 and "boom" in res.stdout


@pytest.mark.parametrize("long_path", [False, True])
def test_long_output_is_cut_with_a_size_hint_and_the_full_log_is_kept(cfg, tmp_path, long_path):
    cfg.blender = fake_exe(tmp_path / "noisy", 'yes line | head -n 5000')
    log_dir = tmp_path / ("long-temp-path-" * 15) / "logs" if long_path else tmp_path / "logs"
    if long_path:
        assert len(str(log_dir)) > 200
    res = R.run("patch_holes", [], cfg, max_chars=300, log_dir=log_dir)
    hint, body = res.stdout.split("\n", 1)
    assert len(body) == 300 and body == ("\n".join(["line"] * 5000))[-300:]
    assert hint == f"(truncated, 24999 chars total - full log: {res.log})"
    log = Path(res.log)
    assert log.exists() and log.read_text().count("line") == 5000


def test_a_timeout_kills_the_tool_and_says_so(cfg, tmp_path):
    cfg.blender = fake_exe(tmp_path / "slow", "sleep 30")
    res = R.run("patch_holes", [], cfg, timeout=1)
    assert res.rc == -1 and res.timed_out is True


def test_unknown_tool_is_refused_with_the_known_names(cfg):
    with pytest.raises(R.ToolUnavailable) as e:
        R.command("nope", [], cfg)
    assert "patch_holes" in str(e.value)


def test_blender_start_up_noise_is_dropped_from_the_result_but_kept_in_the_log(cfg, tmp_path):
    noise = "\\033[32m✓\\033[0m \\033[32m[INFO]\\033[0m Network proxy: none"
    cfg.blender = fake_exe(tmp_path / "chatty", f'printf "{noise}\\n[agent_bubble] registered X\\nholes[0]:\\n"')
    res = R.run("patch_holes", [], cfg, log_dir=tmp_path / "logs")
    assert res.stdout.strip() == "holes[0]:"
    assert "agent_bubble" in Path(res.log).read_text()
