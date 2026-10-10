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
    shutil.copy2(REPO_ROOT / "scripts/lampway/engine_tui_compat.py", root / "scripts/lampway/engine_tui_compat.py")
    shutil.copytree(REPO_ROOT / "scripts/lampway/hermes_tui", root / "scripts/lampway/hermes_tui")
    src = root / "third_party/hermes-agent"
    src.mkdir(parents=True)
    _git(src, "init", "-q")
    (src / "pyproject.toml").write_text('[project]\nname = "hermes-agent"\nrequires-python = ">=3.11,<3.15"\n')
    (src / "uv.lock").write_text("version = 1\n")
    (src / "package.json").write_text(json.dumps({"engines": {"npm": "<11.10.0 || >=11.17.0"}}))
    (src / "LICENSE").write_text("MIT License\n")
    # The played dependency build still runs the real, hash-checked prebuild
    # against its two exact pinned source targets. No bypassed compatibility gate.
    for relative in ("ui-tui/src/app/createGatewayEventHandler.ts", "ui-tui/src/app/slash/commands/core.ts"):
        target = src / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / "third_party/hermes-agent" / relative, target)
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
    assert p["python"] == "3.13" and p["extras"] == "mcp"              # mcp carries Lampway's tools in (E1.6); ACP is gone (A5)
    # spec A1: the TUI is prebuilt at build time, in the engine's own copy of the source (never the pinned tree)
    assert p["tui_install"] == "npm ci --workspace ui-tui --include=dev --no-audit --no-fund (in src/)"
    assert p["tui_build"] == "npm run build (in src/ui-tui/)"
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


def test_check_deps_names_a_missing_node_and_npm(fake_root, tmp_path):
    """Spec A1: the TUI is built with npm and runs on Node; both are build-time dependencies, named when missing."""
    empty = tmp_path / "bin"
    empty.mkdir()
    r = run(fake_root, "--check-deps", env={"PATH": str(empty)})
    assert r.returncode == 2 and "node" in r.stdout and "npm" in r.stdout


FAKE_UV = """#!/bin/sh
# uv sync, played: the environment with a hermes that answers --version
mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
printf '#!/bin/sh\\necho "Hermes Agent (played)"\\n' > "$UV_PROJECT_ENVIRONMENT/bin/hermes"
chmod +x "$UV_PROJECT_ENVIRONMENT/bin/hermes"
echo "uv $*" >> "$TOOL_LOG"
"""
FAKE_NPM = """#!/bin/sh
# npm, played: records where it ran; `run build` leaves the bundle
if [ "$1" = "--version" ]; then echo 11.17.0; exit 0; fi
echo "npm $* @ $(pwd)" >> "$TOOL_LOG"
if [ "$1 $2" = "run build" ]; then mkdir -p dist && echo '// bundle' > dist/entry.js; fi
"""


def test_a_build_prebuilds_the_tui_in_the_engines_own_copy_and_records_it_last(fake_root, tmp_path):
    """Spec A1: ``npm ci --workspace ui-tui`` at the copy's root, then ``npm run build`` in its ui-tui, never in the pinned tree;
    engine.json, written last, names the hermes binary and the TUI directory."""
    src = fake_root / "third_party/hermes-agent"
    (src / "ui-tui").mkdir(exist_ok=True)
    (src / "ui-tui" / "package.json").write_text('{"name": "ui-tui"}')
    (src / "package-lock.json").write_text("{}")
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "tui")
    _git(src, "tag", "-f", "v2026.9.24")
    _git(fake_root, "update-index", "--cacheinfo", f"160000,{_git(src, 'rev-parse', 'HEAD')},third_party/hermes-agent")
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, body in (("uv", FAKE_UV), ("npm", FAKE_NPM), ("node", "#!/bin/sh\necho v22.22.0\n")):
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    log = tmp_path / "tools.log"
    engines = tmp_path / "engines"
    r = run(fake_root, env={"PATH": f"{tools}:/usr/bin:/bin", "TOOL_LOG": str(log), "LAMPWAY_ENGINES_DIR": str(engines)})
    assert r.returncode == 0, r.stdout + r.stderr
    dest = engines / "hermes" / "v2026.9.24"
    ran = log.read_text().splitlines()
    assert ran[0].startswith("uv sync --frozen --no-dev") and "--extra mcp" in ran[0] and "acp" not in ran[0]
    assert ran[1] == f"npm ci --workspace ui-tui --include=dev --no-audit --no-fund @ {dest / 'src'}"
    assert ran[2] == f"npm run build @ {dest / 'src' / 'ui-tui'}"
    assert (dest / "src/ui-tui/dist/entry.js").is_file() and not (src / "ui-tui" / "dist").exists(), "the pinned tree is never built in"
    record = json.loads((dest / "engine.json").read_text())
    assert record["entry"] == record["hermes"] == "env/bin/hermes" and record["tui"] == "src/ui-tui" and record["extras"] == ["mcp"]


def test_a_tui_build_that_leaves_no_bundle_is_refused_and_no_record_is_written(fake_root, tmp_path):
    src = fake_root / "third_party/hermes-agent"
    (src / "ui-tui").mkdir(exist_ok=True)
    (src / "ui-tui" / "package.json").write_text('{"name": "ui-tui"}')
    _git(src, "add", "-A")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "tui")
    _git(src, "tag", "-f", "v2026.9.24")
    _git(fake_root, "update-index", "--cacheinfo", f"160000,{_git(src, 'rev-parse', 'HEAD')},third_party/hermes-agent")
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, body in (("uv", FAKE_UV), ("npm", "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 11.17.0; fi\nexit 0\n"), ("node", "#!/bin/sh\necho v22.22.0\n")):
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    engines = tmp_path / "engines"
    r = run(fake_root, env={"PATH": f"{tools}:/usr/bin:/bin", "TOOL_LOG": str(tmp_path / "log"), "LAMPWAY_ENGINES_DIR": str(engines)})
    assert r.returncode == 1 and "\nerror: " in r.stdout and "entry.js" in r.stdout and "help[" in r.stdout
    assert not (engines / "hermes" / "v2026.9.24" / "engine.json").exists(), "an unfinished build has no record"


def test_an_unknown_flag_exits_2(fake_root):
    assert run(fake_root, "--frobnicate").returncode == 2


def test_the_engine_record_names_the_entry_point(fake_root, tmp_path):
    """--plan prints the engine.json a build would write, so the server's engine manager can be tested against it."""
    p = plan(fake_root, env={"LAMPWAY_ENGINES_DIR": str(tmp_path / "e")})
    record = json.loads(p["record"])
    assert record["engine"] == "hermes" and record["tag"] == "v2026.9.24"
    assert record["entry"] == "env/bin/hermes" and record["hermes"] == "env/bin/hermes" and record["source"] == "src"
    assert record["tui"] == "src/ui-tui", "the server finds the prebuilt TUI here (spec A1)"


@pytest.mark.parametrize("version, accepted", [("11.9.9", True), ("11.10.0", False), ("11.16.0", False), ("11.17.0", True), ("12.0.0", True), ("11.17.0-beta.1", False), ("not-a-version", False)])
def test_npm_engine_range_is_checked_before_any_build(fake_root, tmp_path, version, accepted):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("uv", "node", "npm"):
        body = "#!/bin/sh\n" + (f"echo {version}\n" if name == "npm" else "exit 0\n")
        (tools / name).write_text(body)
        (tools / name).chmod(0o755)
    env = {"PATH": f"{tools}:/usr/bin:/bin", "LAMPWAY_ENGINES_DIR": str(tmp_path / "engines")}
    result = run(fake_root, "--check-deps", env=env)
    assert result.returncode == (0 if accepted else 2), result.stdout + result.stderr
    if not accepted:
        assert "npm" in result.stdout and "<11.10.0 || >=11.17.0" in result.stdout
        result = run(fake_root, env=env)
        assert result.returncode == 1 and "help[" in result.stdout
        assert not (tmp_path / "engines").exists(), "incompatible npm is refused before build writes"


def test_npm_constraint_matches_actual_pinned_package():
    package = json.loads((REPO_ROOT / "third_party/hermes-agent/package.json").read_text())
    assert package["engines"]["npm"] == "<11.10.0 || >=11.17.0"


@pytest.mark.parametrize("constraint", ["garbage", "", "<11.10.0 || >=11.17.0 unexpected"])
def test_unverifiable_npm_constraint_refuses_without_build(fake_root, tmp_path, constraint):
    (fake_root / "third_party/hermes-agent/package.json").write_text(json.dumps({"engines": {"npm": constraint}}))
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("uv", "node", "npm"):
        (tools / name).write_text("#!/bin/sh\necho 11.17.0\n")
        (tools / name).chmod(0o755)
    r = run(fake_root, "--check-deps", env={"PATH": f"{tools}:/usr/bin:/bin"})
    assert r.returncode == 2 and "cannot verify" in r.stdout
