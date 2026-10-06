# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""The one full-suite command judges against the known-red baseline: a new failure is red, a baseline entry that passes is red until removed."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("test_all", ROOT / "scripts/lampway/test_all.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def test_the_baseline_is_well_formed_and_every_line_has_a_class_and_a_reason():
    b = T.load_baseline()
    assert b and all(cls in ("env", "inherited", "stale", "broken", "unknown") and reason for cls, reason in b.values())


def test_parse_reads_ids_and_counts():
    log = "x\nFAILED tests/a.py::t1 - boom\nERROR tests/b.py\nERROR    some.logger:mod.py:1 noise\n= 1 failed, 3 passed, 2 skipped, 1 error in 1.0s =\n"
    ids, counts = T.parse(log, "server/")
    assert ids == {"server/tests/a.py::t1", "server/tests/b.py"} and counts == {"failed": 1, "passed": 3, "skipped": 2, "error": 1}


def test_judge_new_fixed_known():
    j = T.judge({"a", "b", "c"}, {"b": ("env", "x"), "d": ("env", "y")})
    assert j == {"new": ["a", "c"], "fixed": ["d"], "known": ["b"]}


def test_the_baseline_holds_no_absolute_path():
    """Reasons are copied from failure messages, which carry absolute paths: the published baseline keeps them repository-relative."""
    text = (ROOT / "tests" / "known_red.tsv").read_text()
    assert "/var/home/" not in text and "/home/" not in text and "/Users/" not in text
