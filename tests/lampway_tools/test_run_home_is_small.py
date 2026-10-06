# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A test run's Lampway home stays small, and never holds the person's real data.

Measured: every run_script with a fresh LAMPWAY_HOME started at ~105 MB, because the first-run migration copied the person's real ~/.mixar (their chat
history and checkpoints) into it. A test must never read that; run_script points the legacy home at an empty place (LAMPWAY_LEGACY_HOME)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

LIMIT = 10 * 1024 * 1024


def test_a_fresh_run_home_is_under_ten_megabytes_and_holds_nothing_migrated():
    r = run_script("import json, os\nh = os.environ['LAMPWAY_HOME']\ntotal = 0\nnames = []\n"
                   "for root, dirs, files in os.walk(h):\n    for f in files:\n        st = os.lstat(os.path.join(root, f))\n        total += st.st_blocks * 512\n        names.append(f)\n"
                   "print('RESULT ' + json.dumps({'bytes': total, 'migrated': 'MIGRATED-FROM-MIXAR.json' in names and json.load(open(os.path.join(h, 'app', 'MIGRATED-FROM-MIXAR.json'))).get('copied')}))\n",
                   env={"LAMPWAY_HOME": "@RUN_TMP@/home"})
    got = r.results[0]
    assert got["bytes"] < LIMIT, f"the run's home allocates {got['bytes'] / 1e6:.1f} MB"
    assert not got["migrated"], f"the run's home copied the person's real data: {got['migrated']}"
