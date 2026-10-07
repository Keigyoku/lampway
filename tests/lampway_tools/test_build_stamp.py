# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""build/<env>/BUILT_FROM: the commit a build was compiled from, written by build_linux.sh itself (the coordinator's build
rule, 2026-10-06). A build from a tree whose native sources differ from HEAD, or from a commit no remote has, or from a tree
that changed while it compiled, is stamped as such and never with a bare sha.

Each test runs the REAL scripts/lampway/built_from.sh against a throwaway repository with a bare remote."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/lampway/built_from.sh"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def repo(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    t = tmp_path / "tree"
    t.mkdir()
    git(t, "init", "-q", "-b", "main")
    for rel in ("src/source/a.cc", "src/CMakeLists.txt", "src/build_files/x.cmake", "src/release/datafiles/f.txt", "docs/notes.md"):
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text("one\n")
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "one")
    git(t, "remote", "add", "origin", str(remote))
    git(t, "push", "-q", "origin", "main")
    git(t, "fetch", "-q", "origin")
    return t


def run(*args):
    return subprocess.run(["bash", str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_a_clean_pushed_tree_states_its_bare_sha(tmp_path):
    t = repo(tmp_path)
    r = run("state", t)
    assert r.returncode == 0 and r.stdout.strip() == git(t, "rev-parse", "HEAD"), r


def test_a_native_edit_is_unclean_and_a_doc_edit_is_not(tmp_path):
    t = repo(tmp_path)
    sha = git(t, "rev-parse", "HEAD")
    (t / "docs/notes.md").write_text("two\n")
    assert run("state", t).stdout.strip() == sha, "only the native sources decide"
    for rel in ("src/source/a.cc", "src/CMakeLists.txt", "src/build_files/x.cmake", "src/release/datafiles/f.txt"):
        (t / rel).write_text("two\n")
        out = run("state", t).stdout.strip()
        assert out.startswith(f"UNCLEAN {sha}:") and rel in out, (rel, out)
        git(t, "checkout", "-q", "--", rel)
    (t / "src/source/new.cc").write_text("untracked\n")
    assert run("state", t).stdout.strip().startswith("UNCLEAN "), "an untracked source file is compiled too"


def test_a_commit_no_remote_has_is_unpushed(tmp_path):
    t = repo(tmp_path)
    (t / "docs/notes.md").write_text("two\n")
    git(t, "commit", "-q", "-am", "two")
    out = run("state", t).stdout.strip()
    assert out == f"UNPUSHED {git(t, 'rev-parse', 'HEAD')}", out


def test_stamp_writes_the_sha_only_when_the_tree_held_still(tmp_path):
    t = repo(tmp_path)
    sha = git(t, "rev-parse", "HEAD")
    out = tmp_path / "build" / "Prod"
    out.mkdir(parents=True)
    start = run("state", t).stdout.strip()
    assert run("stamp", t, out, start).returncode == 0
    assert (out / "BUILT_FROM").read_text().strip() == sha
    (t / "src/source/a.cc").write_text("edited during the build\n")
    assert run("stamp", t, out, start).returncode == 0
    stamp = (out / "BUILT_FROM").read_text()
    assert stamp.startswith(f"UNCLEAN {sha}: the native tree changed during the build"), stamp


def test_build_linux_stamps_every_build():
    src = (ROOT / "scripts/lampway/build_linux.sh").read_text()
    build = src[src.index("build() {"):src.index("usage()")]
    assert 'built_from.sh" state' in build and 'built_from.sh" stamp' in build, "state before compiling, stamp after"
    assert build.index('built_from.sh" state') < build.index("scripts/unix/build.sh") < build.index('built_from.sh" stamp')
