# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every failure is RED; the baseline attributes known failures and shrinks only with affirmative PASS evidence."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("test_all", ROOT / "scripts/lampway/test_all.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


@pytest.mark.parametrize("empty", [False, True])
def test_the_baseline_is_well_formed_and_every_line_has_a_class_and_a_reason(empty):
    b = {} if empty else T.load_baseline()
    assert all(cls in ("env", "inherited", "stale", "broken", "unknown") and reason for cls, reason in b.values())


def test_parse_reads_ids_and_counts():
    log = "x\nFAILED tests/a.py::t1 - boom\nERROR tests/b.py\nERROR    some.logger:mod.py:1 noise\n= 1 failed, 3 passed, 2 skipped, 1 error in 1.0s =\n"
    ids, counts = T.parse(log, "server/")
    assert ids == {"server/tests/a.py::t1", "server/tests/b.py"} and counts == {"failed": 1, "passed": 3, "skipped": 2, "error": 1, "env_skipped": 0}


def test_judge_new_fixed_known():
    j = T.judge({"a", "b", "c"}, {"b": ("env", "x"), "d": ("env", "y")}, {"d"})
    assert j == {"new": ["a", "c"], "fixed": ["d"], "known": ["b"], "unverified": []}


def test_pass_evidence_preserves_class_and_parameter_identity():
    log = "PASSED tests/a.py::TestGroup::test_case[value with space]\nSKIPPED tests/a.py::test_skip - absent\n"
    assert T.parse_passed(log, "server/") == {"server/tests/a.py::TestGroup::test_case[value with space]"}


def test_teardown_failure_keeps_the_complete_parameter_node_id():
    node = "tests/a.py::TestGroup::test_case[value with space]"
    log = f"PASSED {node}\nERROR {node} - teardown failed\n"
    failing, _ = T.parse(log)
    assert failing == {node}
    assert T.judge(failing, {node: ("broken", "reason")}, T.parse_passed(log))["fixed"] == []


def test_failure_reason_separator_inside_parameter_id_keeps_exact_identity():
    node = "tests/a.py::TestGroup::test_case[value - with space]"
    log = f"PASSED {node}\nFAILED {node} - AssertionError: detail - text\n"
    failing, _ = T.parse(log)
    assert failing == {node}
    assert T.judge(failing, {node: ("broken", "reason")}, T.parse_passed(log))["fixed"] == []


def test_uncertain_parameter_syntax_is_not_a_pass_receipt():
    node = "tests/a.py::test_case[unclosed - value"
    log = f"PASSED {node}\nFAILED {node} - reason\n"
    assert T.parse_passed(log) == set()
    assert T.judge(T.parse(log)[0], {node: ("broken", "reason")}, T.parse_passed(log))["fixed"] == []


@pytest.mark.parametrize("status", ["FAILED", "ERROR", "PASSED"])
def test_actual_ansi_warning_does_not_become_part_of_a_node_id(status):
    node = "tests/test_cat_activity_events.py::test_history_content_while_idle_does_not_reanimate_cat"
    warning = "\x1b[33m⚠\x1b[0m \x1b[33m[WARNING]\x1b[0m Token refresh error: object supporting the buffer API required"
    log = f"{status} {node}{warning}\n"
    if status == "PASSED":
        assert T.parse_passed(log) == {node}
    else:
        failing, _ = T.parse(log)
        assert failing == {node}
        assert T.judge(failing, {node: ("inherited", "reason")}, {node})["fixed"] == []


def test_colored_summary_preserves_parameter_spaces_brackets_and_reason_separator():
    node = "tests/a.py::TestGroup::test_case[value [nested] - with space]"
    log = f"\x1b[31mFAILED\x1b[0m \x1b[1m{node}\x1b[0m - AssertionError: [detail]\n"
    assert T.parse(log, "server/")[0] == {"server/" + node}
    assert T.parse_passed(f"\x1b[32mPASSED\x1b[0m {node}\x1b[0m\n") == {node}


def test_warning_marker_inside_a_parameter_is_preserved():
    node = "tests/a.py::test_case[value ⚠ [WARNING] - [nested]]"
    assert T.parse(f"FAILED {node} - reason\n")[0] == {node}
    assert T.parse_passed(f"PASSED {node}\n") == {node}


def _mock_runner(tmp_path, monkeypatch, log, suite_rc):
    class FakeProc:
        def __init__(self, cmd, cwd, stdout, stderr, start_new_session, env=None):
            stdout.write(log)
            stdout.close()

        def wait(self):
            return suite_rc

    monkeypatch.setattr(T, "verify_env", lambda *a, **k: [])
    monkeypatch.setattr(T, "load_baseline", lambda: {})
    monkeypatch.setattr(T, "binary_gate", lambda *a, **k: ("gated", "sha"))
    monkeypatch.setattr(T, "head_sha", lambda root: "aaa1111")
    monkeypatch.setattr(T.subprocess, "Popen", FakeProc)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_TEST_OUT", str(tmp_path / "out"))


@pytest.mark.parametrize("suite", ["client", "server"])
@pytest.mark.parametrize("status", ["FAILED", "ERROR"])
@pytest.mark.parametrize("shrink", [False, True])
def test_known_failure_is_red_even_when_the_baseline_attributes_it(tmp_path, monkeypatch, suite, status, shrink):
    node = "tests/a.py::test_inherited[value with [brackets] - spaces]"
    count = "1 error" if status == "ERROR" else "1 failed"
    _mock_runner(tmp_path, monkeypatch, f"{status} {node} - inherited defect\n= {count} in 1.0s =\n", 1)
    identity = ("server/" if suite == "server" else "") + node
    baseline = tmp_path / "known_red.tsv"
    original = f"{identity}\tinherited\trecorded defect\n"
    baseline.write_text(original)
    monkeypatch.setattr(T, "BASELINE", baseline)
    monkeypatch.setattr(T, "load_baseline", lambda: {identity: ("inherited", "recorded defect")})
    assert T.main(["--only", suite] + (["--shrink-baseline"] if shrink else [])) == 1
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["verdict"] == "RED"
    assert summary["known_red_seen"] == 1 and summary["new_failures"] == []
    assert summary["baseline_now_passing"] == [] and summary["baseline_unverified"] == []
    assert baseline.read_text() == original


@pytest.mark.parametrize("suite_rc", [1, 3])
def test_suite_process_crash_without_test_ids_is_red(tmp_path, monkeypatch, suite_rc):
    _mock_runner(tmp_path, monkeypatch, "INTERNALERROR pytest crashed before reporting tests\n", suite_rc)
    assert T.main(["--only", "server"]) == 1
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["suite_errors"] == [f"server: pytest exited {suite_rc}"]


@pytest.mark.parametrize("retry_rc,retry_log", [(3, "INTERNALERROR pytest crashed during retry\n"),
                                                (0, "= 1 passed in 1.0s =\n")])
def test_crashed_retry_without_a_pass_receipt_cannot_make_a_failure_flaky(tmp_path, monkeypatch, retry_rc, retry_log):
    from types import SimpleNamespace
    _mock_runner(tmp_path, monkeypatch, "FAILED tests/a.py::test_new - defect\n= 1 failed in 1.0s =\n", 1)
    monkeypatch.setattr(T.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=retry_rc, stdout=retry_log, stderr=""))
    assert T.main(["--only", "client"]) == 1
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["new_failures"] == ["tests/a.py::test_new"]
    assert summary["flaky_passed_on_rerun"] == []


def test_successful_retry_with_an_exact_pass_receipt_is_reported_as_flaky(tmp_path, monkeypatch):
    from types import SimpleNamespace
    _mock_runner(tmp_path, monkeypatch, "FAILED tests/a.py::test_new - defect\n= 1 failed in 1.0s =\n", 1)
    monkeypatch.setattr(T.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="PASSED tests/a.py::test_new\n= 1 passed in 1.0s =\n", stderr=""))
    assert T.main(["--only", "client"]) == 0
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["flaky_passed_on_rerun"] == ["tests/a.py::test_new"]
    assert summary["new_failures"] == []


def test_missing_or_skipped_known_red_is_unverified_and_never_fixed():
    b = {name: ("inherited", "reason") for name in ("failed", "skipped", "uncollected", "passed")}
    assert T.judge({"failed"}, b, {"passed", "failed"}) == {
        "new": [], "fixed": ["passed"], "known": ["failed"], "unverified": ["skipped", "uncollected"],
    }


def test_failure_absence_alone_is_not_a_pass_receipt():
    assert T.judge(set(), {"tests/a.py::skipped": ("env", "missing")})["fixed"] == []


def test_shrink_requires_a_pass_and_keeps_skipped_uncollected_and_failed_rows(tmp_path, monkeypatch):
    baseline = tmp_path / "known_red.tsv"
    baseline.write_text("# retained header\n" + "".join(
        f"tests/a.py::{name}\tinherited\treason\n" for name in ("failed", "skipped", "uncollected", "passed")))

    class FakeProc:
        def __init__(self, cmd, cwd, stdout, stderr, start_new_session, env=None):
            assert "-rA" in cmd
            stdout.write("FAILED tests/a.py::failed - reason\nPASSED tests/a.py::passed\n"
                         "SKIPPED tests/a.py::skipped - missing prerequisite\n= 1 failed, 1 passed, 1 skipped in 1.0s =\n")
            stdout.close()

        def wait(self):
            return 1

    monkeypatch.setattr(T, "BASELINE", baseline)
    monkeypatch.setattr(T, "load_baseline", lambda: {
        line.split("\t")[0]: ("inherited", "reason") for line in baseline.read_text().splitlines() if not line.startswith("#")})
    monkeypatch.setattr(T, "verify_env", lambda *a, **k: [])
    monkeypatch.setattr(T, "binary_gate", lambda *a, **k: ("gated", "sha"))
    monkeypatch.setattr(T, "head_sha", lambda root: "aaa1111")
    monkeypatch.setattr(T.subprocess, "Popen", FakeProc)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_TEST_OUT", str(tmp_path / "out"))
    assert T.main(["--only", "client", "--shrink-baseline"]) == 1
    text = baseline.read_text()
    assert "::passed\t" not in text
    assert all(f"::{name}\t" in text for name in ("failed", "skipped", "uncollected"))
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["baseline_unverified"] == ["tests/a.py::skipped", "tests/a.py::uncollected"]


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


def _shelf(tmp_path):
    """A stand-in shelf holding the fixtures the reference environment requires (names only, empty files)."""
    shelf = tmp_path / "shelf"
    for rel in T.SHELF_FILES:
        f = shelf / "scratch" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
    return {"LAMPWAY_SHELF_DIR": str(shelf)}


def test_verify_env_names_a_missing_i18n_template(tmp_path):
    """b19 (2026-10-06): mixar.pot is git-ignored (generated), so a fresh worktree has none and tests/i18n's template check fails
    while the catalog check skips. The reference environment generates it (test_env.sh); verify_env says when it is missing."""
    problems = T.verify_env(tmp_path, packages={}, python=None, shelf={})
    assert any(T.I18N_TEMPLATE in p and "test_env.sh" in p for p in problems), problems


def test_verify_env_passes_when_everything_is_there(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "reference_fixtures", lambda env: [])
    monkeypatch.setattr(T, "reference_tools", lambda root, env: [])
    (tmp_path / T.I18N_TEMPLATE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / T.I18N_TEMPLATE).write_text("x")
    for rel in T.UPSTREAM_FILES:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    assert T.verify_env(tmp_path, packages={"json": "json"}, python=None, shelf=_shelf(tmp_path)) == []


def test_verify_env_requires_the_shelf_and_its_placement_fixtures(tmp_path):
    """the placement pins (tests/lampway_tools/test_wave2_fit_place.py) run in the reference environment: the shelf is part of it,
    named by LAMPWAY_SHELF_DIR (LAMPWAY_SHELF_SCRATCH when its scratch lives elsewhere); never a path written in the repository."""
    none = T.verify_env(tmp_path, packages={}, python=None, shelf={})
    assert any("LAMPWAY_SHELF_DIR" in p for p in none), none
    env = _shelf(tmp_path)
    (Path(env["LAMPWAY_SHELF_DIR"]) / "scratch" / T.SHELF_FILES[0]).unlink()
    gone = T.verify_env(tmp_path, packages={}, python=None, shelf=env)
    assert any(T.SHELF_FILES[0] in p for p in gone), gone
    moved = tmp_path / "elsewhere"
    (Path(env["LAMPWAY_SHELF_DIR"]) / "scratch").rename(moved)
    assert not any("shelf" in p for p in T.verify_env(tmp_path, packages={}, python=None, shelf=dict(env, LAMPWAY_SHELF_SCRATCH=str(moved))) if T.SHELF_FILES[0] not in p)


def test_the_shelf_is_read_only_a_write_during_the_run_is_named(tmp_path):
    env = _shelf(tmp_path)
    root = Path(env["LAMPWAY_SHELF_DIR"])
    before = T.shelf_snapshot(env)
    assert T.shelf_writes(before, T.shelf_snapshot(env)) == []
    (root / "scratch" / T.SHELF_FILES[0]).write_bytes(b"changed")
    (root / "new.txt").write_text("x")
    assert T.shelf_writes(before, T.shelf_snapshot(env)) == sorted(["new.txt", "scratch/" + T.SHELF_FILES[0]])


def test_the_shelf_tests_read_the_variables_the_environment_provides():
    """every test module that skips on the shelf reads LAMPWAY_SHELF_DIR or LAMPWAY_SHELF_SCRATCH, and SHELF_FILES covers the placement
    pins' own REAL condition (so a reference environment cannot verify while they would skip)."""
    sources = {p.name: p.read_text() for p in (ROOT / "tests/lampway_tools").glob("test_wave2_*.py")}
    for rel in T.SHELF_FILES:
        # Enumerated variants/masks are generated by the consumers' fixed loops.
        filename = rel.split("/")[-1]
        if filename in {"1.jpg", "2.jpg", "3.jpg", "4.jpg"}:
            assert '(1, 2, 3, 4)' in sources["test_wave2_plates.py"]
        elif filename.startswith("mask_"):
            assert filename[5:-4] in sources["test_wave2_palette_fit.py"]
        else:
            assert any(filename in src for src in sources.values()), rel


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
        def __init__(self, cmd, cwd, stdout, stderr, start_new_session, env=None):
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
    assert T.main(["--only", "client"]) == 1
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["sha"] == "aaa1111" and summary["head_at_end"] == "bbb2222"


def test_a_run_leaves_the_callers_environment_unchanged_and_hands_the_suites_the_flag(tmp_path, monkeypatch):
    """main() set os.environ["LAMPWAY_TEST_ALL"] = "1" in its own process: called in-process (as the test above does) it leaked into
    every later test, and the shelf tests after it errored instead of skipping (measured by order). The flag goes to the suites'
    environment only."""
    seen = []

    class FakeProc:
        def __init__(self, cmd, cwd, stdout, stderr, start_new_session, env=None):
            seen.append(env)
            stdout.write("= 2 passed in 1.0s =\n")
            stdout.close()

        def wait(self):
            return 0

    monkeypatch.setattr(T, "verify_env", lambda *a, **k: [])
    monkeypatch.setattr(T, "binary_gate", lambda *a, **k: ("gated", "sha"))
    monkeypatch.setattr(T, "load_baseline", lambda: {})
    monkeypatch.setattr(T, "head_sha", lambda root: "aaa1111")
    monkeypatch.setattr(T.subprocess, "Popen", FakeProc)
    monkeypatch.delenv("LAMPWAY_TEST_ALL", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_TEST_OUT", str(tmp_path / "out"))
    import os
    assert T.main(["--only", "client"]) == 0
    assert "LAMPWAY_TEST_ALL" not in os.environ
    assert seen and all(e is not None and e.get("LAMPWAY_TEST_ALL") == "1" for e in seen)
    import json
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["verdict"] == "GREEN" and summary["binary"]["state"] == "gated"
    assert summary["baseline"] == 0 and summary["known_red_seen"] == 0
    assert summary["new_failures"] == [] and summary["baseline_unverified"] == []


def test_complete_environment_requires_websocket_client():
    assert T.TEST_PACKAGES.get("websocket") == "websocket-client"


def test_reference_tools_refuse_full_chrome_and_missing_renderer(tmp_path, monkeypatch):
    browser = tmp_path / "chrome"
    browser.write_text("#!/bin/sh\necho Chrome\n")
    browser.chmod(0o700)
    monkeypatch.setattr(T.shutil, "which", lambda name: None)
    problems = T.reference_tools(tmp_path, {"LAMPWAY_CHROMIUM": str(browser)})
    assert any("chrome-headless-shell" in p for p in problems)
    assert any("SVG" in p for p in problems)


def test_reference_private_fixture_is_explicit_and_not_in_personal_home(tmp_path):
    problems = T.reference_fixtures({})
    assert any("LAMPWAY_V3_PLATES_DIR" in p for p in problems)
    assert "LAMPWAY_V3_PLATES_DIR" in (T.ROOT / "tests/lampway_tools/test_wave2_plates.py").read_text()


def test_suite_environment_isolates_outer_keyring_override():
    outer = {"PYTHON_KEYRING_BACKEND": "private.owner.backend", "LAMPWAY_KEYRING_FILE": "/private/keyring", "KEEP": "yes"}
    clean = T.suite_environment(outer)
    assert "PYTHON_KEYRING_BACKEND" not in clean and "LAMPWAY_KEYRING_FILE" not in clean
    assert clean["KEEP"] == "yes" and clean["LAMPWAY_TEST_ALL"] == "1"
    assert outer["PYTHON_KEYRING_BACKEND"] == "private.owner.backend"


def test_reference_tools_rejects_failed_actual_art_render(tmp_path, monkeypatch):
    browser = tmp_path / "chrome-headless-shell"
    browser.write_text("#!/bin/sh\necho 'HeadlessShell test'\n")
    browser.chmod(0o700)
    art = tmp_path / "scripts/dev/lampway_placeholder_art.py"
    art.parent.mkdir(parents=True)
    art.write_text("def render_splash():\n    raise RuntimeError('failed actual SVG delegate')\n")
    monkeypatch.setattr(T.shutil, "which", lambda name: "/test/installed/" + name)
    import os
    problems = T.reference_tools(tmp_path, dict(os.environ, LAMPWAY_CHROMIUM=str(browser)))
    assert any("actual authored SVG splash rendering failed" in p for p in problems)
    assert not any("chrome-headless-shell --version failed" in p for p in problems)


def test_reference_tools_rejects_shell_that_fails_to_execute(tmp_path, monkeypatch):
    browser = tmp_path / "chrome-headless-shell"
    browser.write_text("#!/bin/sh\nexit 1\n")
    browser.chmod(0o700)
    monkeypatch.setattr(T.shutil, "which", lambda name: None)
    assert "chrome-headless-shell --version failed" in T.reference_tools(tmp_path, {"LAMPWAY_CHROMIUM": str(browser)})


def test_private_v3_files_join_read_only_snapshot(tmp_path):
    env = _shelf(tmp_path)
    plates = tmp_path / "private-plates"
    (plates / "Chest1").mkdir(parents=True)
    fixture = plates / "Chest1/Front.png"
    fixture.write_bytes(b"original")
    env["LAMPWAY_V3_PLATES_DIR"] = str(plates)
    before = T.shelf_snapshot(env)
    fixture.write_bytes(b"mutated input")
    assert T.shelf_writes(before, T.shelf_snapshot(env)) == ["root1@Chest1/Front.png"]


def test_main_launch_scrubs_outer_keyring_environment(tmp_path, monkeypatch):
    _mock_runner(tmp_path, monkeypatch, "= 1 passed in 1.0s =\n", 0)
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "private.owner.backend")
    monkeypatch.setenv("LAMPWAY_KEYRING_FILE", "/private/keyring")
    original = T.subprocess.Popen
    seen = []

    def record(*args, **kwargs):
        seen.append(kwargs["env"])
        return original(*args, **kwargs)

    monkeypatch.setattr(T.subprocess, "Popen", record)
    assert T.main(["--only", "server"]) == 0
    assert len(seen) == 1
    assert "PYTHON_KEYRING_BACKEND" not in seen[0] and "LAMPWAY_KEYRING_FILE" not in seen[0]


def test_complete_preflight_refuses_missing_browser_and_authentic_plate(tmp_path):
    for rel in (*T.UPSTREAM_FILES, T.I18N_TEMPLATE):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("available source")
    problems = T.verify_env(tmp_path, packages={}, shelf=_shelf(tmp_path))
    assert any("chrome-headless-shell" in p for p in problems)
    assert any("LAMPWAY_V3_PLATES_DIR" in p for p in problems)


def test_suite_exports_default_scratch_for_consumers_requiring_explicit_variable(tmp_path):
    env = T.suite_environment({"LAMPWAY_SHELF_DIR": str(tmp_path)})
    assert env["LAMPWAY_SHELF_SCRATCH"] == str(tmp_path / "scratch")


def test_reference_browser_version_success_cannot_hide_startup_refusal(tmp_path, monkeypatch):
    browser = tmp_path / "chrome-headless-shell"
    browser.write_text("#!/bin/sh\nif [ \"$1\" = --version ]; then echo 'Google Chrome for Testing'; exit 0; fi\necho 'sandbox unavailable' >&2\nexit 1\n")
    browser.chmod(0o700)
    flags = tmp_path / "server/lampway_server/motion/frames.py"
    flags.parent.mkdir(parents=True)
    flags.write_text("CHROME_FLAGS = ['--headless', '--disable-background-networking']\n")
    monkeypatch.setattr(T.shutil, "which", lambda name: None)
    problems = T.reference_tools(tmp_path, {"LAMPWAY_CHROMIUM": str(browser), "TMPDIR": str(tmp_path)})
    assert any("default-flags sandbox startup probe failed" in p for p in problems)
    assert not list(tmp_path.glob("lampway-browser-preflight-*"))


def test_browser_startup_retains_production_network_flags_and_sandbox(tmp_path):
    browser = tmp_path / "chrome-headless-shell"
    browser.write_text('''#!/bin/sh
case " $* " in *" --no-sandbox "*) exit 1;; esac
case " $* " in *" --disable-background-networking "*) ;; *) exit 1;; esac
case " $* " in *" --proxy-server=127.0.0.1:9 "*) ;; *) exit 1;; esac
case " $* " in *" --dump-dom about:blank "*) echo '<html><head></head><body></body></html>';; *) exit 1;; esac
''')
    browser.chmod(0o700)
    assert T.browser_startup_probe(T.ROOT, str(browser), {"TMPDIR": str(tmp_path)}) is None
    assert not list(tmp_path.glob("lampway-browser-preflight-*"))
