# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rail as a gate: every finding code fires on its plant, the controls stay clean, the self-test itself can fail, and this
repository's own rail passes its check."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rail"))

import anneal  # noqa: E402
import railcore as R  # noqa: E402
import selftest as S  # noqa: E402


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    return S.build(tmp_path_factory.mktemp("rail"))


def _check_copy(fixture, tmp_path, fn):
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo, symlinks=True)
    fn(repo)
    return {f["code"] for f in R.check(repo)["findings"]}


@pytest.mark.parametrize("name,expected,fn", S.PLANTS, ids=[p[0] for p in S.PLANTS])
def test_each_planted_violation_is_caught(fixture, tmp_path, name, expected, fn):
    got = _check_copy(fixture, tmp_path, fn)
    assert expected <= got, f"{name}: expected {sorted(expected)}, got {sorted(got)}"


@pytest.mark.parametrize("name,fn", S.CONTROLS, ids=[c[0] for c in S.CONTROLS])
def test_each_control_stays_clean(fixture, tmp_path, name, fn):
    assert _check_copy(fixture, tmp_path, fn) == set(), name


def test_every_code_has_a_plant_and_every_plant_a_code():
    planted = {c for _, codes, _ in S.PLANTS for c in codes}
    assert planted == set(R.CODES)


def test_the_selftest_fails_when_a_rule_is_disabled(monkeypatch):
    """The self-test is itself an assertion: switch the anneal rule off and it must report the plants that went unseen."""
    monkeypatch.setattr(anneal, "assess", lambda before, after, triggers: [])
    result = S.run(names={"body change with no row", "trigger without its owner", "clean fixture"})
    assert result["verdict"] == "FAIL"
    assert set(result["failures"]) == {"body change with no row", "trigger without its owner"}


def test_the_cli_speaks_axi(tmp_path):
    cli = [sys.executable, str(ROOT / "rail" / "rail.py")]
    assert subprocess.run(cli + ["--version"], capture_output=True, text=True).stdout.startswith("rail ")
    bad = subprocess.run(cli + ["nonsense"], capture_output=True, text=True, cwd=ROOT)
    assert bad.returncode == 2 and bad.stdout.startswith("error:") and "help[" in bad.stdout
    codes = subprocess.run(cli + ["codes", "--json"], capture_output=True, text=True, cwd=ROOT)
    assert {c["code"] for c in json.loads(codes.stdout)["codes"]} == set(R.CODES)


def test_sync_writes_nothing_on_a_clean_tree(fixture, tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo, symlinks=True)
    assert R.sync(repo)["written"] == 0
    (repo / ".agents/skills/demo/SKILL.md").write_text("drifted\n")
    assert R.sync(repo)["written"] == 1
    assert R.check(repo)["findings"] == []


def test_this_repository_passes_its_own_rail():
    """The gate on the real tree, history included: red here means a rail, a skill or a trigger changed without its receipt."""
    result = R.check(ROOT)
    assert result["findings"] == [], json.dumps(result["findings"], indent=1)
    assert result["skills"] >= 1 and result["rails"] >= 2


def test_quick_mode_judges_only_what_the_push_brings(fixture, tmp_path):
    """The pre-push form: a commit no remote-tracking ref holds is judged; one already pushed is left to CI's full check."""
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo, symlinks=True)
    S.sh(tmp_path, "init", "-q", "--bare", "remote.git")
    S.sh(repo, "remote", "add", "origin", str(tmp_path / "remote.git"))
    S.sh(repo, "push", "-q", "origin", "main")
    S.p_no_row(repo)                                            # an unreceipted commit, not pushed yet
    assert {f["code"] for f in R.check(repo, quick=True)["findings"]} == {"RAIL-010"}
    S.sh(repo, "push", "-q", "origin", "main")
    assert R.check(repo, quick=True)["findings"] == []          # already on the remote: CI's full check owns it
    assert {f["code"] for f in R.check(repo)["findings"]} == {"RAIL-010"}


def test_quick_mode_leaves_the_generated_documents_to_ci(fixture, tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo, symlinks=True)
    S.p_generated(repo)
    assert R.check(repo, quick=True)["findings"] == []
    assert {f["code"] for f in R.check(repo)["findings"]} == {"RAIL-018"}


def test_a_generator_that_cannot_run_is_red_not_skipped(fixture, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    shutil.copytree(fixture, repo, symlinks=True)
    monkeypatch.setenv("LAMPWAY_SERVER_PYTHON", str(tmp_path / "no-such-python"))
    assert {f["code"] for f in R.check(repo)["findings"]} == {"RAIL-018"}
