# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Issue 2 fixtures in a factory-startup binary, loading source without syncing."""
import json
import os
from pathlib import Path
import subprocess
import pytest


def run(tmp_path, body):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required for isolated real-input evidence')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    pre = '''import sys,json,bpy
OVERLAY=@OVERLAY@
sys.path.insert(0,OVERLAY)
import mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar')
mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
assert api.__file__.startswith(OVERLAY),api.__file__
def call(name,**args):return api.call(name,json.dumps(args))
'''.replace('@OVERLAY@', repr(overlay))
    script = tmp_path / 'issue2.py'; script.write_text(pre + body)
    env = os.environ.copy()
    for name in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME',
                 'LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        path = tmp_path / name.lower(); path.mkdir(); env[name] = str(path)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    p = subprocess.run([binary,'--background','--factory-startup','--disable-autoexec',
                        '--python-exit-code','1','--python',str(script)],env=env,
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    assert p.returncode == 0, p.stdout[-10000:]
    rows = [json.loads(line.removeprefix('RESULT ')) for line in p.stdout.splitlines() if line.startswith('RESULT ')]
    assert rows,p.stdout[-10000:]
    if destination := os.environ.get("LAMPWAY_ISSUE2_RECEIPTS"):
        target = Path(destination); target.mkdir(parents=True, exist_ok=True)
        (target / (tmp_path.name + ".json")).write_text(json.dumps({"binary": binary, "results": rows}, indent=2))
        (target / (tmp_path.name + ".log")).write_text(p.stdout)
    return rows
