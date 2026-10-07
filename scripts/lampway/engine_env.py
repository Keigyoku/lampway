#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pinned Hermes engine environment (docs/reports/agent-modes-spec.md E1.1).

Lampway's Mode 1 engine is Hermes Agent, pinned as the ``third_party/hermes-agent`` submodule (a release tag). Hermes refuses
wheel and sdist builds by design, so the environment is its source checkout copied out of the tree plus ``uv sync --frozen
--extra mcp --no-dev`` from Hermes's own lock, in its own interpreter. A Mode 1 pane runs ``hermes serve`` and Hermes's own TUI
(spec A1), so the TUI is prebuilt here too, in the engine's OWN copy of the source (the pinned tree is never written to):
``npm ci --workspace ui-tui --include=dev --no-audit --no-fund`` against the root ``package-lock.json`` (an npm workspace), then
``npm run build`` in ``ui-tui``, which leaves the self-contained ``ui-tui/dist/entry.js`` the pane runs as it is (no npm at run
time, law 2). The result lives at ``<engines>/hermes/<tag>/``:

    src/          the checkout (without .git, tests, website, evals), with ui-tui/dist/entry.js built
    env/          the virtual environment; the engine is env/bin/hermes
    engine.json   what the server reads, written LAST: engine, tag, commit, python, extras, entry, hermes, tui, source

It never touches the user's own ``~/.hermes`` or a Hermes the user installed. ``<engines>`` is ``LAMPWAY_ENGINES_DIR``, else
``build/engines`` in this repository. Building downloads Hermes's locked dependencies from PyPI and the TUI's from npm (build-time
steps, like the build's own pip installs); the engine at run time reaches nothing but Lampway's gateway and proxy (E1.4, E1.5), and
Node is found at run time, never fetched.

    scripts/lampway/engine_env.py --plan          every resolved setting; touches nothing
    scripts/lampway/engine_env.py --check-deps    names what is missing (exit 2)
    scripts/lampway/engine_env.py                 build (or rebuild) the environment
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBMODULE = "third_party/hermes-agent"
PYTHON = "3.13"                       # Hermes allows 3.11-3.14; 3.13 is the server's own and was measured to work (2026-10-07)
EXTRAS = ("mcp",)                      # mcp: Lampway's tools are an MCP server (A3); ACP is gone with the hidden children (A5)
TUI_INSTALL = ("npm", "ci", "--workspace", "ui-tui", "--include=dev", "--no-audit", "--no-fund")   # at src/: the root lock (A1)
TUI_BUILD = ("npm", "run", "build")                                                               # at src/ui-tui/
TUI_DIR = "src/ui-tui"
ENTRY = "env/bin/hermes"
SKIP = {".git", "tests", "website", "evals", "__pycache__", "node_modules"}


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


def resolve() -> dict:
    src = ROOT / SUBMODULE
    init = f"git submodule update --init {SUBMODULE}"
    staged = _git("ls-files", "-s", SUBMODULE).stdout.split()          # the index: the committed pin, or a bump being made
    committed = _git("ls-tree", "HEAD", SUBMODULE).stdout.split()
    commit = staged[1] if len(staged) >= 2 else (committed[2] if len(committed) >= 3 else "")
    if not commit:
        raise Refusal(f"{SUBMODULE} is not a submodule of this repository", ["git status"])
    if not (src / "pyproject.toml").is_file():
        raise Refusal(f"the Hermes checkout at {SUBMODULE} is missing", [init])
    head = _git("rev-parse", "HEAD", cwd=src).stdout.strip()
    if head != commit:
        raise Refusal(f"{SUBMODULE} is at {head[:12] or 'nothing'}, not the pinned {commit[:12]}", [init, f"git -C {SUBMODULE} status"])
    tags = [t for t in _git("tag", "--points-at", "HEAD", cwd=src).stdout.split() if t.startswith("v")]
    tag = sorted(tags)[-1] if tags else commit[:12]
    engines = Path(os.environ.get("LAMPWAY_ENGINES_DIR") or ROOT / "build" / "engines")
    dest = engines / "hermes" / tag
    record = {"engine": "hermes", "tag": tag, "commit": commit, "python": PYTHON, "extras": list(EXTRAS),
              "source": "src", "entry": ENTRY, "hermes": ENTRY, "tui": TUI_DIR}
    return {"engine": "hermes", "tag": tag, "commit": commit, "src": str(src), "dest": str(dest), "python": PYTHON,
            "extras": ",".join(EXTRAS), "tui_install": " ".join(TUI_INSTALL) + " (in src/)",
            "tui_build": " ".join(TUI_BUILD) + " (in src/ui-tui/)", "record": json.dumps(record, sort_keys=True)}


def missing_deps() -> list:
    out = []
    if shutil.which("uv") is None:
        out.append("uv (Astral's Python package manager): the engine environment is built from Hermes's own uv.lock")
    if shutil.which("git") is None:
        out.append("git")
    if shutil.which("node") is None:
        out.append("node (Node.js 22 or 24): Hermes's TUI runs on it in Lampway Agent's pane (spec A1)")
    if shutil.which("npm") is None:
        out.append("npm: the TUI is prebuilt at build time from Hermes's own package-lock.json (spec A1)")
    return out


def build(p: dict) -> int:
    """Built in place: a virtual environment's scripts carry absolute paths. ``engine.json`` is written last, so a directory
    without it is an unfinished build and the server's engine manager ignores it."""
    dest, src = Path(p["dest"]), Path(p["src"])
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(src, dest / "src", ignore=lambda d, names: [n for n in names if n in SKIP])
    cmd = ["uv", "sync", "--frozen", "--no-dev", "--python", p["python"]] + [a for e in EXTRAS for a in ("--extra", e)]
    print("run: " + " ".join(cmd), flush=True)
    if subprocess.run(cmd, cwd=dest / "src", env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(dest / "env")}).returncode != 0:
        return refuse("uv sync failed (see above)", ["scripts/lampway/engine_env.py --check-deps", "uv cache clean"])
    check = subprocess.run([str(dest / ENTRY), "--version"], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if not k.upper().endswith(("_KEY", "_TOKEN"))})
    if check.returncode != 0:
        return refuse(f"the built engine does not start: {(check.stdout + check.stderr).strip()[-400:]}",
                      ["scripts/lampway/engine_env.py"])
    for argv, cwd in ((TUI_INSTALL, dest / "src"), (TUI_BUILD, dest / TUI_DIR)):      # the engine's own copy, never the pin
        print("run: " + " ".join(argv) + f"  (in {cwd})", flush=True)
        if subprocess.run(list(argv), cwd=cwd).returncode != 0:
            return refuse(f"{' '.join(argv)} failed (see above)", ["scripts/lampway/engine_env.py --check-deps", "npm cache verify"])
    if not (dest / TUI_DIR / "dist" / "entry.js").is_file():
        return refuse(f"the TUI build left no {TUI_DIR}/dist/entry.js", ["scripts/lampway/engine_env.py --plan"])
    (dest / "engine.json").write_text(p["record"] + "\n")
    print(f"built: {dest}")
    print(f"entry: {dest / ENTRY}")
    print(f"tui: {dest / TUI_DIR / 'dist' / 'entry.js'}")
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
        return refuse("missing: " + "; ".join(miss), ["scripts/lampway/engine_env.py --check-deps"])
    return build(p)


if __name__ == "__main__":
    sys.exit(main())
