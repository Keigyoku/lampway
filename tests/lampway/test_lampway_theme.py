# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 01: the Night and Paper themes are generated from one token file and gated (T1-T6, T10)."""

import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "scripts/lampway/facelift/theme"
PRESETS = ROOT / "src/scripts/presets/interface_theme"


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(THEME / script), *args], capture_output=True, text=True, cwd=cwd)


def test_theme_gate_has_no_findings():
    done = run("check_theme.py")
    assert done.returncode == 0, done.stdout + done.stderr


def test_theme_gate_catches_each_planted_offender():
    done = run("check_theme.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "MISSED" not in done.stdout


def test_cue_gate_passes_and_catches_its_plants():
    assert run("check_cues.py").returncode == 0
    done = run("check_cues.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr


def test_shipped_presets_are_the_generated_files(tmp_path):
    done = run("build_theme.py", "--out", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    for shipped, generated in (("Lampway_Night.xml", "lampway_dark.xml"), ("Lampway_Paper.xml", "lampway_light.xml")):
        assert (PRESETS / shipped).is_file(), shipped
        assert filecmp.cmp(PRESETS / shipped, tmp_path / generated, shallow=False), shipped
        assert filecmp.cmp(THEME / generated, tmp_path / generated, shallow=False), generated


def test_every_generated_file_is_committed_as_generated(tmp_path):
    """The provenance maps and the WezTerm config are generator outputs too: a hand edit or a stale copy fails."""
    done = run("build_theme.py", "--out", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    for name in ("lampway_dark.provenance.json", "lampway_light.provenance.json", "lampway.wezterm.lua"):
        assert filecmp.cmp(THEME / name, tmp_path / name, shallow=False), name


@pytest.mark.skipif(shutil.which("luajit") is None, reason="check_wezterm.py runs the config under luajit")
def test_wezterm_gate_passes_and_catches_its_plants():
    assert run("check_wezterm.py").returncode == 0
    done = run("check_wezterm.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "MISSED" not in done.stdout

