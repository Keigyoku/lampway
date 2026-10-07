# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run current source in the binary without installing or syncing its Python tree."""
import os
import json
import subprocess
from pathlib import Path
import pytest
from blender_run import Run
from features_support import PRE


def run(tmp_path, body):
    binary = os.environ.get("LAMPWAY_BIN")
    if not binary or not Path(binary).is_file():
        pytest.skip("LAMPWAY_BIN required for isolated current-source acceptance")
    overlay = str(Path(__file__).resolve().parents[2] / "src/scripts")
    prefix = f'''
import sys
sys.path.insert(0, {overlay!r})
import mixar, mixar.modules
mixar.__path__.insert(0, {overlay!r} + "/mixar")
mixar.modules.__path__.insert(0, {overlay!r} + "/mixar/modules")
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0, {overlay!r} + "/mixar/modules/lampway_tools")
'''
    script = tmp_path / "acceptance.py"
    script.write_text(prefix + PRE.replace("ROOT", repr(str(tmp_path))) + body)
    env = os.environ.copy()
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "LAMPWAY_HOME", "LAMPWAY_LEGACY_HOME", "TMPDIR"):
        path = tmp_path / key.lower()
        path.mkdir(mode=0o700)
        env[key] = str(path)
    env.update(LAMPWAY_PROJECT_ROOT=str(tmp_path), LAMPWAY_TEST_ROOT=str(tmp_path), LAMPWAY_BACKEND_URL="http://127.0.0.1:9", LAMPWAY_BRIDGE_PORT="0")
    process = subprocess.run([binary, "-b", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1", "--python", str(script)], env=env, capture_output=True, text=True, timeout=120)
    output = process.stdout + process.stderr
    (tmp_path / "binary.log").write_text(output)
    results = [json.loads(line[7:]) for line in output.splitlines() if line.startswith("RESULT ")]
    return Run(process.returncode, output, results)
