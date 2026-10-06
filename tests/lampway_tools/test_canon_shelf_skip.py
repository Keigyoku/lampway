# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Inside test_all (LAMPWAY_TEST_ALL=1, the environment verified: the shelf present) a shelf test that would skip is a FAILURE, as an
upstream/ test is (conftest.py): a skipped placement pin would read as green while the MetaHuman-sized cases went unmeasured."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(tmp_path, env_extra):
    t = tmp_path / "tests" / "lampway_tools"
    t.mkdir(parents=True)
    (t / "test_shelf_probe.py").write_text(
        "import os\nimport pytest\nfrom pathlib import Path\n"
        "SHELF = Path(os.environ.get('LAMPWAY_SHELF_DIR') or '/nonexistent-shelf')\n"
        "@pytest.mark.skipif(not (SHELF / 'nothing_here.npz').exists(), reason=\"the shelf's fixture is not on this machine\")\n"
        "def test_pin():\n    pass\n")
    (tmp_path / "conftest.py").write_text((ROOT / "conftest.py").read_text())
    env = dict(os.environ, **env_extra)
    env.pop("PYTEST_ADDOPTS", None)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", str(t)], cwd=tmp_path, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout


def test_outside_test_all_a_shelf_test_skips(tmp_path):
    rc, out = _run(tmp_path, {"LAMPWAY_TEST_ALL": "0", "LAMPWAY_SHELF_DIR": str(tmp_path)})
    assert rc == 0 and "1 skipped" in out, out


def test_inside_test_all_a_shelf_skip_is_a_failure(tmp_path):
    rc, out = _run(tmp_path, {"LAMPWAY_TEST_ALL": "1", "LAMPWAY_SHELF_DIR": str(tmp_path)})
    assert rc == 1 and ("1 failed" in out or "1 error" in out) and "shelf is part of the environment" in out, out     # a setup-phase failure reads as an error; test_all counts ERROR ids as failing
