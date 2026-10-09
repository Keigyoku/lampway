# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract tests for scripts/lampway/herdr_env.py: the pinned herdr build (docs/reports/agent-modes-spec.md A4).

herdr, the terminal server every Lampway agent pane runs in, is pinned as the ``third_party/herdr`` submodule at a release tag, the
way ``upstream/`` pins Blender. The script builds exactly that commit with herdr's own toolchain pin (``rust-toolchain.toml``)
and ``cargo build --release --locked``, out of the tree. These tests cover its AXI surface (``--plan``, ``--check-deps``,
refusals) on a throwaway superproject; none of them compiles or downloads anything. The real build was run by hand (herdr 0.9.3,
2026-10-07) and the server's live herdr tests drive its binary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = Path("scripts/lampway/herdr_env.py")
SUB = "third_party/herdr"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def fake_root(tmp_path):
    """A superproject with the script and a herdr submodule whose checkout is a tiny git repo tagged like a release."""
    root = tmp_path / "repo"
    (root / "scripts/lampway").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / SCRIPT_REL, root / SCRIPT_REL)
    src = root / SUB
    src.mkdir(parents=True)
    _git(src, "init", "-q")
    (src / "Cargo.toml").write_text('[package]\nname = "herdr"\nversion = "0.9.3"\n')
    (src / "Cargo.lock").write_text("version = 4\n")
    (src / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.96.1"\n')
    (src / "LICENSE").write_text("Apache License\n")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "release")
    _git(src, "tag", "v0.9.3")
    _git(root, "init", "-q")
    pin = _git(src, "rev-parse", "HEAD")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{pin},{SUB}")
    return root


def run(root, *args, env=None):
    e = {k: v for k, v in os.environ.items() if k not in ("LAMPWAY_HERDR_BUILDS", "ZIG")}
    e.update(env or {})
    return subprocess.run([sys.executable, str(root / SCRIPT_REL), *args], cwd=root, capture_output=True, text=True, env=e, timeout=60)


def plan(root, *args, **kw):
    r = run(root, "--plan", *args, **kw)
    assert r.returncode == 0, r.stdout + r.stderr
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def test_plan_resolves_the_pin_and_the_toolchain_and_touches_nothing(fake_root, tmp_path):
    dest = tmp_path / "builds"
    p = plan(fake_root, env={"LAMPWAY_HERDR_BUILDS": str(dest)})
    pin = _git(fake_root / SUB, "rev-parse", "HEAD")
    assert p["tool"] == "herdr" and p["tag"] == "v0.9.3" and p["commit"] == pin
    assert p["dest"] == str(dest / "v0.9.3")
    assert p["rust"] == "1.96.1", "herdr's own toolchain pin (rust-toolchain.toml)"
    assert p["zig"] == "0.16.0", "the Zig herdr's vendored libghostty-vt build requires"
    assert p["cargo"] == "cargo build --release --locked"
    assert not dest.exists(), "--plan must not create anything"


def test_the_default_destination_is_under_build(fake_root):
    assert plan(fake_root)["dest"] == str(fake_root / "build" / "herdr" / "v0.9.3")


def test_the_record_names_the_binary_and_the_pin(fake_root, tmp_path):
    """--plan prints the herdr.json a build would write, so the server's lookup can be tested against it."""
    record = json.loads(plan(fake_root, env={"LAMPWAY_HERDR_BUILDS": str(tmp_path / "b")})["record"])
    assert record == {"tool": "herdr", "tag": "v0.9.3", "commit": _git(fake_root / SUB, "rev-parse", "HEAD"), "binary": "herdr",
                      "rust": "1.96.1", "zig": "0.16.0"}


def test_a_checkout_that_is_not_the_pinned_commit_is_refused(fake_root):
    src = fake_root / SUB
    (src / "drift.txt").write_text("x")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "drift")
    r = run(fake_root, "--plan")
    assert r.returncode == 1
    assert r.stdout.startswith("error: ") and "pinned" in r.stdout and "help[" in r.stdout
    assert f"git submodule update --init {SUB}" in r.stdout


def test_a_missing_checkout_is_refused_with_how_to_get_it(fake_root):
    shutil.rmtree(fake_root / SUB)
    r = run(fake_root, "--plan")
    assert r.returncode == 1 and f"git submodule update --init {SUB}" in r.stdout


def test_check_deps_names_a_missing_cargo_and_zig(fake_root, tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    r = run(fake_root, "--check-deps", env={"PATH": str(empty)})
    assert r.returncode == 2 and "cargo" in r.stdout and "zig" in r.stdout


def test_check_deps_refuses_a_zig_that_is_not_the_version_herdr_needs(fake_root, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_zig = bindir / "zig"
    fake_zig.write_text("#!/bin/sh\necho 0.13.0\n")
    fake_zig.chmod(0o755)
    r = run(fake_root, "--check-deps", env={"PATH": str(bindir), "ZIG": str(fake_zig)})
    assert r.returncode == 2 and "0.16.0" in r.stdout and "0.13.0" in r.stdout


def test_an_unknown_flag_exits_2(fake_root):
    assert run(fake_root, "--frobnicate").returncode == 2


@pytest.mark.parametrize("tags", [[], ["v99.0.0"], ["v0.9.3", "v99.0.0"]])
def test_pinned_manifest_version_does_not_depend_on_local_release_tags(fake_root, tags):
    src = fake_root / SUB
    _git(src, "tag", "-d", "v0.9.3")
    for tag in tags:
        _git(src, "tag", tag)
    p = plan(fake_root)
    assert p["tag"] == "v0.9.3", "Cargo package version at the verified pin controls binary verification"
    assert json.loads(p["record"])["commit"] == _git(src, "rev-parse", "HEAD")


def test_uncommitted_cargo_version_is_refused(fake_root):
    (fake_root / SUB / "Cargo.toml").write_text('[package]\nname = "herdr"\nversion = "99.0.0"\n')
    r = run(fake_root, "--plan")
    assert r.returncode == 1 and "Cargo.toml" in r.stdout and "help[" in r.stdout


@pytest.mark.parametrize("binary_version, accepted", [("0.9.3", True), ("0.9.30", False)])
def test_real_shallow_no_tag_checkout_build_checks_exact_cargo_version(fake_root, tmp_path, binary_version, accepted):
    src = fake_root / SUB
    origin = tmp_path / "origin"
    src.rename(origin)
    _git(fake_root, "clone", "--quiet", "--depth=1", "--no-tags", origin.as_uri(), str(src))
    assert _git(src, "rev-parse", "--is-shallow-repository") == "true"
    assert not _git(src, "tag", "--list")
    tools = tmp_path / "tools"
    tools.mkdir()
    cargo = tools / "cargo"
    cargo.write_text(f"""#!/bin/sh
mkdir -p "$CARGO_TARGET_DIR/release"
cat > "$CARGO_TARGET_DIR/release/herdr" <<'SCRIPT'
#!/bin/sh
echo "herdr {binary_version}"
SCRIPT
chmod +x "$CARGO_TARGET_DIR/release/herdr"
""")
    cargo.chmod(0o755)
    zig = tools / "zig"
    zig.write_text("#!/bin/sh\necho 0.16.0\n")
    zig.chmod(0o755)
    builds = tmp_path / "builds"
    r = run(fake_root, env={"PATH": f"{tools}:/usr/bin:/bin", "LAMPWAY_HERDR_BUILDS": str(builds)})
    assert r.returncode == (0 if accepted else 1), r.stdout + r.stderr
    record = builds / "v0.9.3/herdr.json"
    assert record.exists() == accepted, "wrong binary version never leaves a completed build record"
    if accepted:
        assert json.loads(record.read_text())["commit"] == _git(src, "rev-parse", "HEAD")
