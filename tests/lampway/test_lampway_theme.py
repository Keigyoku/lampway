# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 01: the Night and Paper themes are generated from one token file and gated (T1-T6, T10)."""

import filecmp
import subprocess
import sys
from pathlib import Path

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
