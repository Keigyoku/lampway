# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract tests for scripts/lampway/build_linux.sh.

The script's testable surface is ``--plan``: it resolves everything the build
would use (pinned upstream commit, MIXAR_ENV, MIXAR_CUDA, binary path) and
prints it as ``key=value`` lines without touching the tree. The fixture repo
below is a throwaway git repository carrying only a gitlink for ``upstream``,
so the tests never read or write the real worktree's ``.env``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = Path("scripts/lampway/build_linux.sh")
FAKE_PIN = "fbe6228777e7d9afefcd61a413844e790ae75db7"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A minimal superproject: the script under test plus a pinned gitlink."""
    root = tmp_path / "repo"
    (root / "scripts/lampway").mkdir(parents=True)
    shutil.copy(REPO_ROOT / SCRIPT_REL, root / SCRIPT_REL)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(
        root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{FAKE_PIN},upstream",
    )
    _git(root, "add", str(SCRIPT_REL))
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _run(root: Path, verb: str, env_overrides: dict[str, str] | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MIXAR_")}
    env.update(env_overrides or {})
    return subprocess.run(
        [str(root / SCRIPT_REL), verb],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_plan(root: Path, env_overrides: dict[str, str] | None = None):
    # --plan is pure resolution: it must work on a host with no toolchain.
    return _run(root, "--plan", env_overrides)


def _kv(stdout: str) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in stdout.splitlines() if "=" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def test_plan_reports_the_pinned_upstream_commit(fake_root: Path) -> None:
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    assert _kv(result.stdout)["upstream_pin"] == FAKE_PIN


def test_plan_reports_an_unpopulated_submodule_dir_as_absent(fake_root: Path) -> None:
    # A fresh clone has an EMPTY upstream/ directory. `git -C upstream rev-parse
    # HEAD` there walks up to the superproject and answers with ITS head, which
    # would masquerade as a populated submodule.
    (fake_root / "upstream").mkdir()
    superproject_head = _git(fake_root, "rev-parse", "HEAD")
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["upstream_head"] == ""
    assert plan["upstream_head"] != superproject_head


def test_plan_reports_an_lfs_pointer_startup_blend(fake_root: Path) -> None:
    # blender.git keeps release/datafiles/startup.blend (and every bundled
    # asset) in Git LFS. A checkout made without `git lfs pull` leaves a
    # ~130-byte pointer that datatoc embeds as the factory startup file; the
    # app then crashes on first window. Upstream's CMake uses the same
    # 1024-byte floor; the plan must say which state the tree is in.
    datafiles = fake_root / "upstream/release/datafiles"
    datafiles.mkdir(parents=True)
    (datafiles / "startup.blend").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        "size 1234567\n"
    )
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    assert _kv(result.stdout)["upstream_lfs"] == "pointer"


def test_plan_reports_a_materialised_startup_blend(fake_root: Path) -> None:
    datafiles = fake_root / "upstream/release/datafiles"
    datafiles.mkdir(parents=True)
    (datafiles / "startup.blend").write_bytes(b"BLENDER" + b"\0" * 4096)
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    assert _kv(result.stdout)["upstream_lfs"] == "materialised"


def test_plan_defaults_to_dev_cpu_only(fake_root: Path) -> None:
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["mixar_env"] == "Dev"
    assert plan["mixar_cuda"] == "0"
    assert plan["binary"] == str(fake_root / "build/Dev/bin/mixar")


def test_plan_leaves_service_urls_to_the_tree_by_default(fake_root: Path) -> None:
    # Since lp/fork-patches the tree's own default is our server on loopback
    # (src/scripts/mixar/config/brand.py, mirrored by settings.sh), so the
    # script must not bake a different host behind the caller's back. Unset
    # means "whatever settings.sh/brand.py resolve", and the plan says so.
    result = _run_plan(fake_root)
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["mixar_backend_url"] == "(tree default)"
    assert plan["mixar_frontend_url"] == "(tree default)"


def test_plan_honours_explicit_service_urls(fake_root: Path) -> None:
    result = _run_plan(
        fake_root,
        {
            "MIXAR_BACKEND_URL": "https://api.example.test",
            "MIXAR_FRONTEND_URL": "https://www.example.test",
        },
    )
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["mixar_backend_url"] == "https://api.example.test"
    assert plan["mixar_frontend_url"] == "https://www.example.test"


def test_plan_honours_an_explicit_environment(fake_root: Path) -> None:
    result = _run_plan(fake_root, {"MIXAR_ENV": "Prod", "MIXAR_CUDA": "1"})
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["mixar_env"] == "Prod"
    assert plan["mixar_cuda"] == "1"
    assert plan["binary"] == str(fake_root / "build/Prod/bin/mixar")


def test_plan_refuses_a_dotenv_that_contradicts_the_requested_env(
    fake_root: Path,
) -> None:
    # settings.sh sources .env AFTER the caller's environment, so a stray
    # MIXAR_ENV=Prod in .env would silently win over the exported Dev.
    (fake_root / ".env").write_text("MIXAR_ENV=Prod\n")
    result = _run_plan(fake_root, {"MIXAR_ENV": "Dev"})
    assert result.returncode == 3
    assert ".env" in result.stderr
    assert "MIXAR_ENV" in result.stderr


def test_check_deps_fails_naming_missing_build_tools(fake_root: Path) -> None:
    empty_bin = fake_root / "emptybin"
    empty_bin.mkdir()
    # Keep the bare essentials bash itself needs; drop everything else.
    for tool in ("bash", "git", "dirname", "readlink", "basename", "cat", "env"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, empty_bin / tool)
    result = _run(fake_root, "--check-deps", {"PATH": str(empty_bin)})
    assert result.returncode == 2
    assert "missing" in result.stderr
    assert "cmake" in result.stderr


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def toolchain_bin(fake_root: Path) -> Path:
    """A PATH with every required command stubbed green except the compiler."""
    bin_dir = fake_root / "toolbin"
    bin_dir.mkdir()
    for tool in ("bash", "sh", "git", "dirname", "readlink", "basename", "cat",
                 "env", "sed", "tail", "head", "tr", "cut", "grep", "awk",
                 "stat", "df", "date", "mkdir", "nproc", "tee", "pwd"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, bin_dir / tool)
    for tool in ("cmake", "make", "python3", "rsync", "ninja"):
        _stub(bin_dir, tool, "exit 0")
    _stub(bin_dir, "pkg-config", "exit 0")
    return bin_dir


def test_check_deps_rejects_a_gcc_older_than_14(
    fake_root: Path, toolchain_bin: Path
) -> None:
    # Blender 5.2's CMakeLists.txt refuses GCC < 14; surface that before
    # configure instead of 3000 lines into the log.
    for name in ("gcc", "g++", "c++", "cc"):
        _stub(toolchain_bin, name, 'echo "13.3.0"')
    result = _run(fake_root, "--check-deps", {"PATH": str(toolchain_bin)})
    assert result.returncode == 2
    assert "gcc" in result.stderr.lower()
    assert "14" in result.stderr


def test_plan_prefers_a_versioned_gcc_14_when_the_default_is_older(
    fake_root: Path, toolchain_bin: Path
) -> None:
    for name in ("gcc", "g++", "c++", "cc"):
        _stub(toolchain_bin, name, 'echo "13.3.0"')
    _stub(toolchain_bin, "gcc-14", 'echo "14.2.0"')
    _stub(toolchain_bin, "g++-14", 'echo "14.2.0"')
    result = _run_plan(fake_root, {"PATH": str(toolchain_bin)})
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["cc"] == "gcc-14"
    assert plan["cxx"] == "g++-14"


def test_plan_honours_an_explicit_cc_and_cxx(
    fake_root: Path, toolchain_bin: Path
) -> None:
    _stub(toolchain_bin, "mycc", 'echo "15.0.0"')
    _stub(toolchain_bin, "mycxx", 'echo "15.0.0"')
    result = _run_plan(
        fake_root, {"PATH": str(toolchain_bin), "CC": "mycc", "CXX": "mycxx"}
    )
    assert result.returncode == 0, result.stderr
    plan = _kv(result.stdout)
    assert plan["cc"] == "mycc"
    assert plan["cxx"] == "mycxx"


def test_real_worktree_plan_matches_git_gitlink() -> None:
    pinned = _git(REPO_ROOT, "rev-parse", "HEAD:upstream")
    result = _run_plan(REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert _kv(result.stdout)["upstream_pin"] == pinned


# ---- the bundled embedding models (scripts/lampway/fetch_models.py) ------------------------------------------------------------
def test_plan_names_where_the_bundled_models_go(fake_root: Path) -> None:
    result = _run_plan(fake_root, {"MIXAR_ENV": "Prod"})
    assert result.returncode == 0, result.stderr
    assert _kv(result.stdout)["models_dir"] == str(fake_root / "build/Prod/bin/5.2/datafiles/lampway/models")


def test_models_only_runs_the_fetcher_into_the_builds_data_directory(fake_root: Path) -> None:
    log = fake_root / "fetch.log"
    fetcher = fake_root / "scripts/lampway/fetch_models.py"
    fetcher.write_text(f"import sys\nopen({str(log)!r}, 'w').write(' '.join(sys.argv[1:]))\n")
    result = _run(fake_root, "--models-only", {"MIXAR_ENV": "Prod"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text() == "--dest " + str(fake_root / "build/Prod/bin/5.2/datafiles/lampway/models")


def test_a_failed_model_fetch_fails_the_step(fake_root: Path) -> None:
    (fake_root / "scripts/lampway/fetch_models.py").write_text("import sys\nsys.exit(5)\n")
    result = _run(fake_root, "--models-only")
    assert result.returncode == 5
    assert "models" in result.stderr


def test_lampway_skip_models_leaves_the_build_without_weights(fake_root: Path) -> None:
    log = fake_root / "fetch.log"
    (fake_root / "scripts/lampway/fetch_models.py").write_text(f"open({str(log)!r}, 'w').write('ran')\n")
    result = _run(fake_root, "--models-only", {"LAMPWAY_SKIP_MODELS": "1"})
    assert result.returncode == 0 and not log.exists()
    assert "LAMPWAY_SKIP_MODELS" in result.stdout
