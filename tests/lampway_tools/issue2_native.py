# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable current-overlay runner; never synchronizes an installed application."""
import json
import os
from pathlib import Path
import subprocess
import pytest


def run_issue_case(tmp_path, body):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required for isolated native acceptance')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    pre = """import sys, os, json, math
sys.path.insert(0, OVERLAY)
import bpy, bmesh, numpy as np, mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY+'/mixar');mixar.modules.__path__.insert(0, OVERLAY+'/mixar/modules')
from mixar.modules import common
common.__path__.insert(0, OVERLAY+'/mixar/modules/common')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0, OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api, canon_io
assert api.__file__.startswith(OVERLAY),api.__file__
root=os.environ['LAMPWAY_PROJECT_ROOT'];os.makedirs(root,exist_ok=True)
def call(name, **args):return api.call(name,json.dumps(args))
def sphere(name='piece',subdiv=3):
    bm=bmesh.new();bmesh.ops.create_icosphere(bm,subdivisions=subdiv,radius=.5)
    me=bpy.data.meshes.new(name);bm.to_mesh(me);bm.free()
    ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);return ob
def ids():
    return {k:sorted(x.name for x in getattr(bpy.data,k)) for k in ('objects','meshes','armatures','actions','images','materials','curves','cameras','lights','node_groups','collections','scenes')}
"""
    script = tmp_path / 'acceptance.py'
    script.write_text('OVERLAY='+repr(overlay)+'\n'+pre+'\n'+body+'\nprint("ISSUE_RESULT "+json.dumps({"verified":True}))\n')
    env=os.environ.copy()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        d=tmp_path/key.lower();d.mkdir(exist_ok=True);env[key]=str(d)
    env['LAMPWAY_PROJECT_ROOT']=str(tmp_path/'project')
    run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300)
    receipt_root=os.environ.get("LAMPWAY_ISSUE2_GEOMETRY_RECEIPTS")
    if receipt_root:
        target=Path(receipt_root);target.mkdir(parents=True,exist_ok=True)
        (target/(tmp_path.name+".log")).write_text(run.stdout)
        for line in run.stdout.splitlines():
            if line.startswith("GEOMETRY_RECEIPT "):
                (target/(tmp_path.name+".json")).write_text(json.dumps(json.loads(line.removeprefix("GEOMETRY_RECEIPT ")),indent=2)+"\n")
    assert run.returncode==0,run.stdout[-14000:]
    assert 'ISSUE_RESULT {"verified": true}' in run.stdout,run.stdout[-9000:]
    return run.stdout
