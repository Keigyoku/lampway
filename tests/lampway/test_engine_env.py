# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract tests for scripts/lampway/engine_env.py: the pinned Hermes engine environment (docs/reports/agent-modes-spec.md E1.1).

The engine is Hermes Agent, pinned as the ``third_party/hermes-agent`` submodule. Hermes refuses wheel builds by design, so the
environment is the source checkout copied out of the tree plus ``uv sync --frozen --extra acp --no-dev`` from its own lock. These
tests cover the script's AXI surface (``--plan``, ``--check-deps``, refusals) on a throwaway superproject; none of them downloads
anything. The real build is exercised by hand and in the engine conformance suite (E1.8)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = Path("scripts/lampway/engine_env.py")


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def fake_root(tmp_path):
    """A superproject with the script and a Hermes submodule whose checkout is a tiny git repo tagged like a release."""
    root = tmp_path / "repo"
    (root / "scripts/lampway").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / SCRIPT_REL, root / SCRIPT_REL)
    src = root / "third_party/hermes-agent"
    src.mkdir(parents=True)
    _git(src, "init", "-q")
    (src / "pyproject.toml").write_text('[project]\nname = "hermes-agent"\nrequires-python = ">=3.11,<3.15"\n')
    (src / "uv.lock").write_text("version = 1\n")
    (src / "LICENSE").write_text("MIT License\n")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "release")
    _git(src, "tag", "v2026.9.24")
    _git(root, "init", "-q")
    pin = _git(src, "rev-parse", "HEAD")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{pin},third_party/hermes-agent")
    return root


def run(root, *args, env=None):
    e = {**os.environ, **(env or {})}
    e.pop("LAMPWAY_ENGINES_DIR", None)
    if env and "LAMPWAY_ENGINES_DIR" in env:
        e["LAMPWAY_ENGINES_DIR"] = env["LAMPWAY_ENGINES_DIR"]
    return subprocess.run([sys.executable, str(root / SCRIPT_REL), *args], cwd=root, capture_output=True, text=True, env=e, timeout=60)


def plan(root, *args, **kw):
    r = run(root, "--plan", *args, **kw)
    assert r.returncode == 0, r.stdout + r.stderr
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def test_plan_resolves_the_pin_and_touches_nothing(fake_root, tmp_path):
    dest = tmp_path / "engines"
    p = plan(fake_root, env={"LAMPWAY_ENGINES_DIR": str(dest)})
    pin = _git(fake_root / "third_party/hermes-agent", "rev-parse", "HEAD")
    assert p["engine"] == "hermes" and p["tag"] == "v2026.9.24" and p["commit"] == pin
    assert p["dest"] == str(dest / "hermes" / "v2026.9.24")
    assert p["python"] == "3.13" and p["extras"] == "acp,mcp"          # mcp carries Lampway's tools in (E1.6)
    assert not dest.exists(), "--plan must not create anything"


def test_the_default_destination_is_under_build(fake_root):
    assert plan(fake_root)["dest"] == str(fake_root / "build" / "engines" / "hermes" / "v2026.9.24")


def test_a_checkout_that_is_not_the_pinned_commit_is_refused(fake_root):
    src = fake_root / "third_party/hermes-agent"
    (src / "drift.txt").write_text("x")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "drift")
    r = run(fake_root, "--plan")
    assert r.returncode == 1
    assert r.stdout.startswith("error: ") and "pinned" in r.stdout and "help[" in r.stdout
    assert "git submodule update --init third_party/hermes-agent" in r.stdout


def test_a_missing_checkout_is_refused_with_how_to_get_it(fake_root):
    shutil.rmtree(fake_root / "third_party/hermes-agent")
    r = run(fake_root, "--plan")
    assert r.returncode == 1 and "git submodule update --init third_party/hermes-agent" in r.stdout


def test_check_deps_names_a_missing_uv(fake_root, tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    r = run(fake_root, "--check-deps", env={"PATH": str(empty)})
    assert r.returncode == 2 and "uv" in r.stdout


def test_an_unknown_flag_exits_2(fake_root):
    assert run(fake_root, "--frobnicate").returncode == 2


def test_the_engine_record_names_the_entry_point(fake_root, tmp_path):
    """--plan prints the engine.json a build would write, so the server's engine manager can be tested against it."""
    p = plan(fake_root, env={"LAMPWAY_ENGINES_DIR": str(tmp_path / "e")})
    record = json.loads(p["record"])
    assert record["engine"] == "hermes" and record["tag"] == "v2026.9.24"
    assert record["entry"] == "env/bin/hermes-acp" and record["source"] == "src"
