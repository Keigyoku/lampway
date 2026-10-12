# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Two million actual grid triangles: deadline before atomic work, cold and warm."""
import json
import os
from pathlib import Path
import subprocess

import pytest


def test_two_million_triangles_within_twice_100ms(tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required; no installed app is synced')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    source = '''import sys,json,time
sys.path.insert(0,OVERLAY)
import bpy,mixar,mixar.modules,numpy as np
mixar.__path__.insert(0,OVERLAY+'/mixar')
mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
from mixar.modules.lampway_tools.inspect import cache
assert api.__file__.startswith(OVERLAY),api.__file__
n=1000
mesh=bpy.data.meshes.new('SyntheticGrid2M')
mesh.vertices.add((n+1)**2)
y,x=np.indices((n+1,n+1),dtype=np.float32)
points=np.zeros(((n+1)**2,3),dtype=np.float32)
points[:,0]=x.ravel();points[:,1]=y.ravel()
mesh.vertices.foreach_set('co',points.ravel())
y,x=np.indices((n,n),dtype=np.int32)
a=(y*(n+1)+x).ravel()
triangles=np.stack((a,a+1,a+n+2,a,a+n+2,a+n+1),axis=1).ravel()
mesh.loops.add(len(triangles));mesh.loops.foreach_set('vertex_index',triangles)
mesh.polygons.add(2*n*n)
mesh.polygons.foreach_set('loop_start',np.arange(2*n*n,dtype=np.int32)*3)
mesh.polygons.foreach_set('loop_total',np.full(2*n*n,3,dtype=np.int32))
mesh.update(calc_edges=True)
ob=bpy.data.objects.new('TwoMillion',mesh);bpy.context.scene.collection.objects.link(ob)
assert len(mesh.polygons)==2_000_000
# Import/registry setup and fixture construction are outside the timed tool call.
cache._ENTRIES.clear()
rows=[]
for state in ['cold','warm']:
    before=time.perf_counter()
    result=api.call('inspect',json.dumps({'view':'mesh','name':ob.name,'budget_ms':100}))
    elapsed=(time.perf_counter()-before)*1000
    rows.append({'state':state,'elapsed_ms':elapsed,'faces':len(mesh.polygons),'result':result})
    assert result.get('ok') and len(result['skipped'])==1,(elapsed,result)
    assert result['skipped'][0]['reason']=='budget_ms exceeded',result
    assert any('budget_ms=<more>' in hint for hint in result['help']),result
    assert elapsed<=200,(state,elapsed,result)
assert not cache._ENTRIES,'Refused geometry must never populate the cache'
print('BUDGET_RESULT '+json.dumps(rows))
'''.replace('OVERLAY', repr(overlay))
    script = tmp_path / 'budget.py'
    script.write_text(source)
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        directory = tmp_path / key.lower()
        directory.mkdir()
        env[key] = str(directory)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    run = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec',
                          '--python-exit-code', '1', '--python', str(script)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    assert run.returncode == 0, run.stdout[-12000:]
    outputs = [json.loads(line.removeprefix('BUDGET_RESULT ')) for line in run.stdout.splitlines()
               if line.startswith('BUDGET_RESULT ')]
    assert len(outputs) == 1, run.stdout[-12000:]
    print('BUDGET_RECEIPT ' + json.dumps(outputs[0]))
