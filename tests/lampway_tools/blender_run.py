# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run a script inside the real Lampway binary (headless) and read what it prints.

The binary is the build's own `mixar` (`build/<env>/bin/mixar`, or `$LAMPWAY_BIN`). Python-only changes reach it
through `scripts/lampway/sync_python.sh`; the helper syncs before every run so a test never reads a stale install.
A script reports by printing lines `RESULT {json}`.
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def lampway_bin() -> Path:
    return Path(os.environ.get("LAMPWAY_BIN") or ROOT / "build" / "Dev" / "bin" / "mixar")


@dataclass
class Run:
    rc: int
    out: str
    results: list = field(default_factory=list)


def require_binary():
    if not lampway_bin().exists():
        pytest.skip(f"no Lampway binary at {lampway_bin()} (build it: scripts/lampway/build_linux.sh)")


def run_script(source: str, *, scene: Path | None = None, args=(), env=None, timeout=240) -> Run:
    require_binary()
    bindir = lampway_bin().parent
    subprocess.run([str(ROOT / "scripts/lampway/sync_python.sh"), "--bin-dir", str(bindir)],
                   check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "t.py"
        script.write_text(source, encoding="utf-8")
        e = dict(os.environ)
        e.update({"XDG_CONFIG_HOME": str(Path(tmp) / "xdg"), "LAMPWAY_BACKEND_URL": "http://127.0.0.1:9",
                  "LAMPWAY_BRIDGE_PORT": "0",
                  # a profile per run: the default (~/.local/share/lampway) is shared by every lane's concurrent runs, and one run's
                  # settings_set(project_root=...) landed in another's (measured: "outside the project root .../tmp-vault-ops/...")
                  "LAMPWAY_HOME": str(Path(tmp) / "lampway_home")})
        e.update(env or {})
        cmd = ["nice", "-n", "15", str(lampway_bin()), "-b"]
        if scene:
            cmd.append(str(scene))
        cmd += ["--python-exit-code", "1", "-P", str(script), "--", *map(str, args)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=e)
    out = p.stdout + p.stderr
    results = [json.loads(line[len("RESULT "):]) for line in out.splitlines() if line.startswith("RESULT ")]
    return Run(p.returncode, out, results)
