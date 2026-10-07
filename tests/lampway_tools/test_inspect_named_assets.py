# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original named-asset acceptance; public fixtures are external, never bundled."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('asset', ['DamagedHelmet', 'ABeautifulGame', 'StanfordBunny'])
def test_named_asset_contract(asset, tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    assets = os.environ.get('LAMPWAY_MCP_ACCEPTANCE_ASSETS')
    if not binary or not assets:
        pytest.skip('requires real binary and externally pinned public acceptance assets')
    root = Path(__file__).resolve().parents[2]
    script = tmp_path / 'named.py'
    script.write_text(_SCRIPT.replace('@OVERLAY@', repr(str(root / 'src/scripts')))
                      .replace('@ASSETS@', repr(assets)).replace('@ASSET@', repr(asset)))
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        directory = tmp_path / key.lower(); directory.mkdir(); env[key] = str(directory)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    run = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec',
                          '--python-exit-code', '1', '--python', str(script)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    rows = [line.removeprefix('NAMED_RESULT ') for line in run.stdout.splitlines()
            if line.startswith('NAMED_RESULT ')]
    if rows:
        result = json.loads(rows[-1])
        receipts = os.environ.get('LAMPWAY_MCP_ACCEPTANCE_RECEIPTS')
        if receipts:
            path = Path(receipts); path.mkdir(parents=True, exist_ok=True)
            (path / (asset + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    assert run.returncode == 0, run.stdout[-12000:]
    assert rows, run.stdout[-12000:]
    assert not result['failures'], result['failures']


_SCRIPT = '''import sys,json,time
from pathlib import Path
OVERLAY=@OVERLAY@
sys.path.insert(0, OVERLAY)
import bpy,mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar')
mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
from mixar.modules.lampway_tools.inspect import cache,schema
import mixar.modules.common
mixar.modules.common.__path__.insert(0,OVERLAY+'/mixar/modules/common')
from mixar.modules.common.toon.codec import encode,decode
from jsonschema import validate
asset=@ASSET@; assets=Path(@ASSETS@)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
if asset=='StanfordBunny': bpy.ops.wm.ply_import(filepath=str(assets/'bun_zipper.ply'))
else: bpy.ops.import_scene.gltf(filepath=str(assets/(asset+'.glb')))
mesh=max((ob for ob in bpy.context.scene.objects if ob.type=='MESH'), key=lambda ob:len(ob.data.polygons))
bpy.ops.object.select_all(action='DESELECT');mesh.select_set(True);bpy.context.view_layer.objects.active=mesh
failures=[]; timings={}; outputs={}
def call(key,args):
    start=time.perf_counter(); out=api.call('inspect',json.dumps(args));timings[key]=(time.perf_counter()-start)*1000
    outputs[key]=out
    if not out.get('ok'): failures.append(key+': '+str(out))
    return out
home=call('home',{})
if asset=='ABeautifulGame' and timings['home']>=200:failures.append('home >=200ms: '+str(timings['home']))
if asset=='DamagedHelmet':
    for view in ['mesh','uv']:
        cache._ENTRIES.clear()
        out=call(view+'_cold',{'view':view,'name':mesh.name})
        if out.get('skipped'):failures.append(view+' cold skipped '+str(out['skipped']))
        if timings[view+'_cold']>=2000:failures.append(view+' cold >=2000ms: '+str(timings[view+'_cold']))
        for index in range(3):
            key=view+'_cached_'+str(index)
            warm=call(key,{'view':view,'name':mesh.name})
            if warm.get('skipped'):failures.append(key+' skipped')
            if timings[key]>=50:failures.append(key+' >=50ms: '+str(timings[key]))
    for view in ['scene','objects','object','mesh','uv','parts','layers','relations','file','schema','help']:
        args={'view':view}
        if view in ['object','mesh','uv','parts','layers']:args['name']=mesh.name
        if view in ['schema','help']:args['name']='mesh'
        out=call('view_'+view,args)
        if out.get('ok'):
            validate(out,schema.view_schema(view))
            assert decode(encode(out))==out,view
if asset=='StanfordBunny':
    inspected=call('mesh',{'view':'mesh','name':mesh.name,'fields':['*'],'limit':1000,'budget_ms':60000})
    scanned=api.call('mesh_defect_scan',json.dumps({'object':mesh.name,'kinds':['open_loop'],'max_candidates':500}))
    if not scanned.get('ok'):failures.append('defect tool refusal '+str(scanned))
    else:
        a=sorted((row['edges'],row['rim_length_m']) for row in inspected['data']['holes'])
        b=sorted((row.get('edges',row.get('descriptor',{}).get('edges')), row.get('descriptor',row)['rim_length_m']) for row in scanned['candidates'])
        expected=[(22,0.0302),(39,0.0598),(40,0.0636),(42,0.0722),(80,0.1137)]
        if a!=expected:failures.append('bunny rim golden differs: '+str(a))
        if a!=b:failures.append('open-loop candidates differ: '+str((a,b)))
    outputs['defect_scan']=scanned
print('NAMED_RESULT '+json.dumps({'asset':asset,'mesh':mesh.name,'mesh_faces':len(mesh.data.polygons),'timings_ms':timings,'outputs':outputs,'failures':failures}))
'''
