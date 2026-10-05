# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scripts/lampway/sync_python.sh copies the Python half of the tree into an
installed build, so a Python-only change needs no compile."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "lampway" / "sync_python.sh"


def _install(tmp_path):
    scripts = tmp_path / "bin" / "5.2" / "scripts"
    (scripts / "mixar" / "config").mkdir(parents=True)
    (scripts / "mixar" / "config" / "_build_env.py").write_text("BUILD_ENVIRONMENT = 'Dev'\n")
    (scripts / "mixar" / "stale_but_kept.py").write_text("x = 1\n")
    return tmp_path / "bin"


def test_sync_copies_the_mixar_package_and_keeps_generated_files(tmp_path):
    bindir = _install(tmp_path)
    run = subprocess.run([str(SCRIPT), "--bin-dir", str(bindir)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    cfg = bindir / "5.2" / "scripts" / "mixar" / "config"
    assert (cfg / "_build_env.py").read_text() == "BUILD_ENVIRONMENT = 'Dev'\n"      # generated at build time: never deleted
    assert (cfg / "brand.py").exists()                                              # a real tree file arrived


def test_sync_does_not_ship_test_directories(tmp_path):
    bindir = _install(tmp_path)
    subprocess.run([str(SCRIPT), "--bin-dir", str(bindir)], check=True, capture_output=True)
    assert not (bindir / "5.2" / "scripts" / "mixar" / "modules" / "testing").exists()


def test_sync_refuses_a_bin_dir_that_is_not_an_install(tmp_path):
    run = subprocess.run([str(SCRIPT), "--bin-dir", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode == 1
    assert "error:" in run.stdout


def test_sync_unknown_flag_exits_2(tmp_path):
    run = subprocess.run([str(SCRIPT), "--nope"], capture_output=True, text=True)
    assert run.returncode == 2
