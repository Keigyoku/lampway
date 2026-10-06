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


# ---- the binary rule: a gated client run tests the binary built from the batch's own native sources
import subprocess  # noqa: E402


def _repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src" / "source").mkdir(parents=True)
    (r / "src" / "source" / "a.cc").write_text("int a;\n")
    (r / "scripts").mkdir()
    (r / "scripts" / "x.py").write_text("x = 1\n")
    g = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com"]
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "one"], check=True)
    return r, g


def _bin(tmp_path, built_from=None):
    prod = tmp_path / "Prod"
    (prod / "bin").mkdir(parents=True)
    (prod / "bin" / "mixar").write_text("")
    if built_from is not None:
        (prod / "BUILT_FROM").write_text(built_from + "\n")
    return prod / "bin" / "mixar"


def test_a_binary_built_from_the_same_native_sources_is_gated(tmp_path):
    r, g = _repo(tmp_path)
    sha = subprocess.run(g + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (r / "scripts" / "x.py").write_text("x = 2\n")                         # a Python-only change after the build: still the same native sources
    subprocess.run(g + ["commit", "-qam", "py"], check=True)
    assert T.binary_gate(r, _bin(tmp_path, sha))[0] == "gated"


def test_a_binary_whose_native_sources_differ_is_refused(tmp_path):
    r, g = _repo(tmp_path)
    sha = subprocess.run(g + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (r / "src" / "source" / "a.cc").write_text("int b;\n")
    subprocess.run(g + ["commit", "-qam", "native"], check=True)
    state, msg = T.binary_gate(r, _bin(tmp_path, sha))
    assert state == "refused" and "native sources" in msg


def test_a_binary_without_built_from_runs_ungated_and_says_so(tmp_path):
    r, _ = _repo(tmp_path)
    state, msg = T.binary_gate(r, _bin(tmp_path))
    assert state == "ungated" and "UNGATED binary" in msg
    assert T.binary_gate(r, None)[0] == "ungated"
