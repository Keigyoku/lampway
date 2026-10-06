# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A temp dir made INSIDE the binary by a test script lands in the run's own temp dir and is gone after the run (blender_run.run_script points TMPDIR there)."""
import os
import tempfile
from pathlib import Path

from blender_run import run_script


def test_a_temp_dir_made_inside_the_binary_is_under_the_run_and_removed_after_it():
    r = run_script("import json, os, tempfile\nd = tempfile.mkdtemp(prefix='lw_probe_')\nprint('RESULT ' + json.dumps({'d': d, 'home': os.environ.get('LAMPWAY_HOME')}))\n",
                   env={"LAMPWAY_HOME": "@RUN_TMP@/home"})
    got = r.results[0]
    shared = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()).resolve()
    assert Path(got["d"]).parent.resolve() != shared and not Path(got["d"]).exists(), got        # not in the shared temp dir, and gone with the run
    assert got["home"].endswith("/home") and "@RUN_TMP@" not in got["home"] and not Path(got["home"]).exists()
