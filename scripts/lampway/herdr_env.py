#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pinned herdr (docs/reports/agent-modes-spec.md A4).

herdr is the terminal server every Lampway agent pane runs in, in both modes. It is pinned as the ``third_party/herdr`` submodule at a
release tag, the way ``upstream/`` pins Blender, and built from exactly that commit:
- herdr's own toolchain pin (``rust-toolchain.toml``, which rustup honours);
- ``cargo build --release --locked`` against herdr's own ``Cargo.lock``;
- Zig 0.16.0 for its vendored ``libghostty-vt``.

The result lives at ``<builds>/<tag>/``:

    herdr         the binary
    herdr.json    what the server's herdr lookup reads: tool, tag, commit, binary, rust, zig
    target/       cargo's build directory (kept, so a rebuild is incremental)

``herdr.json`` is written last: a directory without it is an unfinished build and the server ignores it. ``<builds>`` is
``LAMPWAY_HERDR_BUILDS``, else ``build/herdr`` in this repository. The server then runs this herdr ahead of one on PATH
(``server/lampway_server/herdr/launcher.py``); ``LAMPWAY_HERDR_BIN`` still overrides both.

Building downloads herdr's locked crates and its Zig packages: a build-time step, like ``engine_env.py``'s. Zig's own fetcher may fail
behind an HTTPS proxy. Then download each ``.url`` named by herdr's ``build.zig.zon`` files with curl (or git, for a ``git+https`` one),
and run ``zig fetch <file>`` inside any directory holding a ``build.zig``; the package's hash must match the manifest's.

    scripts/lampway/herdr_env.py --plan          every resolved setting; touches nothing
    scripts/lampway/herdr_env.py --check-deps    names what is missing (exit 2)
    scripts/lampway/herdr_env.py                 build (or rebuild) the pinned herdr
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBMODULE = "third_party/herdr"
ZIG_VERSION = "0.16.0"               # crates/ghostty-vt/build.rs at the pin: "Building Herdr requires Zig 0.16.0"
CARGO = ("cargo", "build", "--release", "--locked")


class Refusal(Exception):
    def __init__(self, why, helps):
        super().__init__(why)
        self.helps = helps


def refuse(why, helps, code=1):
    print(f"error: {why}")
    print(f"help[{len(helps)}]:")
    for h in helps:
        print(f"  {h}")
    return code


def _git(*args, cwd=ROOT):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _rust_channel(src: Path) -> str:
    m = re.search(r'^\s*channel\s*=\s*"([^"]+)"', (src / "rust-toolchain.toml").read_text(), re.M) if (src / "rust-toolchain.toml").is_file() else None
    return m.group(1) if m else ""


def resolve() -> dict:
    src = ROOT / SUBMODULE
    init = f"git submodule update --init {SUBMODULE}"
    staged = _git("ls-files", "-s", SUBMODULE).stdout.split()          # the index: the committed pin, or a bump being made
    committed = _git("ls-tree", "HEAD", SUBMODULE).stdout.split()
    commit = staged[1] if len(staged) >= 2 else (committed[2] if len(committed) >= 3 else "")
    if not commit:
        raise Refusal(f"{SUBMODULE} is not a submodule of this repository", ["git status"])
    if not (src / "Cargo.toml").is_file():
        raise Refusal(f"the herdr checkout at {SUBMODULE} is missing", [init])
    head = _git("rev-parse", "HEAD", cwd=src).stdout.strip()
    if head != commit:
        raise Refusal(f"{SUBMODULE} is at {head[:12] or 'nothing'}, not the pinned {commit[:12]}", [init, f"git -C {SUBMODULE} status"])
    # A shallow checkout need not include tags. Cargo embeds this pinned package
    # version in the stable binary; local tag names are not build identity.
    manifest = _git("show", f"{commit}:Cargo.toml", cwd=src)
    try:
        text = (src / "Cargo.toml").read_text()
        if manifest.returncode != 0 or text != manifest.stdout:
            raise ValueError("Cargo.toml differs from the pin")
        package = tomllib.loads(text)["package"]
        version = package["version"]
        if package["name"] != "herdr" or not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("invalid herdr package version")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refusal("cannot resolve the pinned herdr Cargo.toml package version", [init, f"git -C {SUBMODULE} diff -- Cargo.toml"]) from exc
    tag = f"v{version}"
    builds = Path(os.environ.get("LAMPWAY_HERDR_BUILDS") or ROOT / "build" / "herdr")
    rust = _rust_channel(src)
    record = {"tool": "herdr", "tag": tag, "commit": commit, "binary": "herdr", "rust": rust, "zig": ZIG_VERSION}
    return {"tool": "herdr", "tag": tag, "commit": commit, "src": str(src), "dest": str(builds / tag), "rust": rust,
            "zig": ZIG_VERSION, "cargo": " ".join(CARGO), "record": json.dumps(record, sort_keys=True)}


def zig_path() -> str:
    return os.environ.get("ZIG") or shutil.which("zig") or ""


def missing_deps() -> list:
    out = []
    if shutil.which("cargo") is None:
        out.append("cargo (Rust, through rustup: herdr's rust-toolchain.toml names the toolchain, which rustup installs)")
    if shutil.which("git") is None:
        out.append("git")
    zig = zig_path()
    if not zig:
        out.append(f"zig {ZIG_VERSION} (on PATH, or ZIG=<path>): herdr builds its vendored libghostty-vt with it")
    else:
        r = subprocess.run([zig, "version"], capture_output=True, text=True)
        have = (r.stdout or r.stderr).strip()
        if r.returncode != 0 or have != ZIG_VERSION:
            out.append(f"zig {ZIG_VERSION}: {zig} is {have or 'not runnable'}")
    return out


def build(p: dict) -> int:
    """``herdr.json`` is written last, so a directory without it is an unfinished build that the server ignores."""
    dest, src = Path(p["dest"]), Path(p["src"])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "herdr.json").unlink(missing_ok=True)
    env = {**os.environ, "CARGO_TARGET_DIR": str(dest / "target"), "ZIG": zig_path()}
    print("run: " + " ".join(CARGO), flush=True)
    if subprocess.run(list(CARGO), cwd=src, env=env).returncode != 0:
        return refuse("cargo build failed (see above)", ["scripts/lampway/herdr_env.py --check-deps",
                                                          "behind a proxy, seed Zig's packages by hand: see this script's docstring"])
    shutil.copy2(dest / "target" / "release" / "herdr", dest / "herdr")
    ver = subprocess.run([str(dest / "herdr"), "--version"], capture_output=True, text=True)
    want = p["tag"].lstrip("v")
    if ver.returncode != 0 or ver.stdout.strip() != f"herdr {want}":
        return refuse(f"the built herdr says {(ver.stdout + ver.stderr).strip()[:200]!r}, not {want}", ["scripts/lampway/herdr_env.py"])
    (dest / "herdr.json").write_text(p["record"] + "\n")
    print(f"built: {dest / 'herdr'}")
    print(f"version: {ver.stdout.strip()}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="print every resolved setting; touch nothing")
    ap.add_argument("--check-deps", action="store_true", help="name what is missing (exit 2)")
    args = ap.parse_args(argv)           # an unknown flag exits 2 (argparse)
    if args.check_deps:
        miss = missing_deps()
        if miss:
            print("missing:")
            for m in miss:
                print(f"  {m}")
            return 2
        print("deps: ok")
        return 0
    try:
        p = resolve()
    except Refusal as exc:
        return refuse(str(exc), exc.helps)
    if args.plan:
        for k, v in p.items():
            print(f"{k}={v}")
        return 0
    miss = missing_deps()
    if miss:
        return refuse("missing: " + "; ".join(miss), ["scripts/lampway/herdr_env.py --check-deps"])
    return build(p)


if __name__ == "__main__":
    sys.exit(main())
