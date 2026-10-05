# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pre-publish gate sees what it must (self-test plants one of each offender) and the hook and workflow point at the file that ships."""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/lampway/prepublish_gate.py"


def test_the_gate_sees_every_planted_offender():
    p = subprocess.run([sys.executable, str(GATE), "--self-test"], capture_output=True, text=True)
    assert p.returncode == 0 and "every planted offender was seen" in p.stdout, p.stdout + p.stderr


def test_the_hook_and_the_workflow_run_the_shipped_gate_and_the_allow_list_has_reasons():
    assert "scripts/lampway/prepublish_gate.py" in (ROOT / ".githooks/pre-push").read_text()
    assert "scripts/lampway/prepublish_gate.py" in (ROOT / ".github/workflows/pii-gate.yml").read_text()
    for line in (ROOT / "scripts/lampway/pii_allow.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert "#" in line, f"an allow-list value without a reason: {line!r}"
