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
    assert ids == {"server/tests/a.py::t1", "server/tests/b.py"} and counts == {"failed": 1, "passed": 3, "skipped": 2, "error": 1, "env_skipped": 0}


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


def test_the_stamp_build_linux_writes_is_read(tmp_path):
    """build_linux.sh stamps "UNPUSHED <sha>" for a commit no remote has (its native sources still decide the gate) and
    "UNCLEAN <sha>: ..." for a tree that was not the commit: an unclean binary is refused by name, not as an unknown sha."""
    r, g = _repo(tmp_path)
    sha = subprocess.run(g + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert T.binary_gate(r, _bin(tmp_path / "a", f"UNPUSHED {sha}")) == ("gated", sha)
    state, msg = T.binary_gate(r, _bin(tmp_path / "b", f"UNCLEAN {sha}: native sources differ from the commit (src/source/a.cc)"))
    assert state == "refused" and msg.startswith("the binary was built from an unclean tree:") and "src/source/a.cc" in msg, msg


def test_a_binary_without_built_from_runs_ungated_and_says_so(tmp_path):
    r, _ = _repo(tmp_path)
    state, msg = T.binary_gate(r, _bin(tmp_path))
    assert state == "ungated" and "UNGATED binary" in msg
    assert T.binary_gate(r, None)[0] == "ungated"


# ---- one test environment: test_all verifies it before it runs anything
def test_verify_env_names_a_missing_upstream_and_a_missing_package(tmp_path):
    (tmp_path / "upstream").mkdir()
    problems = T.verify_env(tmp_path, packages={"surely_not_a_module_xyz": "surely-not"}, python=None)
    assert any("upstream/" in p for p in problems) and any("surely-not" in p for p in problems)


def test_verify_env_passes_when_everything_is_there(tmp_path):
    for rel in T.UPSTREAM_FILES:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    assert T.verify_env(tmp_path, packages={"json": "json"}, python=None) == []


def test_the_test_requirements_cover_what_verify_env_checks():
    reqs = (ROOT / "tests" / "requirements-test.txt").read_text().lower() + (ROOT / "server" / "pyproject.toml").read_text().lower()
    for dist in T.TEST_PACKAGES.values():
        assert dist.lower() in reqs, dist


def test_a_run_is_judged_on_the_head_and_baseline_it_started_with(tmp_path, monkeypatch):
    """b11/b12: the baseline was read and the sha taken when the suites ENDED, so a commit or a baseline edit made during a run
    changed what the run claimed to have tested. Both are fixed at the start; a head that moved is reported beside it."""
    heads = iter(["aaa1111", "bbb2222"])
    started = []

    class FakeProc:
        def __init__(self, cmd, cwd, stdout, stderr, start_new_session):
            started.append(cmd)
            stdout.write("= 1 failed, 2 passed in 1.0s =\nFAILED tests/x.py::t - boom\n")
            stdout.close()

        def wait(self):
            return 1

    def baseline():
        assert not started, "the baseline must be read before the suites start"
        return {"tests/x.py::t": ("inherited", "r")}

    monkeypatch.setattr(T, "verify_env", lambda *a, **k: [])
    monkeypatch.setattr(T, "binary_gate", lambda *a, **k: ("gated", "sha"))
    monkeypatch.setattr(T, "load_baseline", baseline)
    monkeypatch.setattr(T, "head_sha", lambda root: next(heads))
    monkeypatch.setattr(T.subprocess, "Popen", FakeProc)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_TEST_OUT", str(tmp_path / "out"))
    assert T.main(["--only", "client"]) == 0
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["sha"] == "aaa1111" and summary["head_at_end"] == "bbb2222"
