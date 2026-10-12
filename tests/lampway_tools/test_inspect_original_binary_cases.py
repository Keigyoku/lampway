# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original T1 acceptance fixtures through the actual API on an isolated overlay."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('case', ['two_cube_shells', 'suzanne_uv_unwrap', 'cube_on_plane'])
def test_original_inspect_case(case, tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required; never syncs an installed app')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'original.py'
    script.write_text(_SCRIPT.replace('@OVERLAY@', repr(overlay)).replace('@CASE@', repr(case)))
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        directory = tmp_path / key.lower(); directory.mkdir(); env[key] = str(directory)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    run = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec',
                          '--python-exit-code', '1', '--python', str(script)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
    assert run.returncode == 0, run.stdout[-9000:]
    rows = [line.removeprefix('ORIGINAL_RESULT ') for line in run.stdout.splitlines()
            if line.startswith('ORIGINAL_RESULT ')]
    assert len(rows) == 1, run.stdout[-9000:]
    result = json.loads(rows[0])
    assert result['case'] == case and result['verified'], result


_SCRIPT = '''import sys,json
OVERLAY=@OVERLAY@
sys.path.insert(0,OVERLAY)
import bpy,bmesh,mixar,mixar.modules
from mathutils import Matrix
mixar.__path__.insert(0,OVERLAY+'/mixar');mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
assert api.__file__.startswith(OVERLAY),api.__file__
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def snapshot():
    return ([(ob.name,ob.data.name if ob.data else None,ob.hide_get(),ob.mode,
              tuple(tuple(v.co) for v in ob.data.vertices) if ob.type=='MESH' else ()) for ob in bpy.context.scene.objects],
            [ob.name for ob in bpy.context.selected_objects],
            bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
            len(bpy.data.meshes))
def inspect(**args):
    before=snapshot()
    result=api.call('inspect',json.dumps(args))
    assert result.get('ok') and not result.get('skipped'),result
    assert snapshot()==before,'inspection changed fixture state'
    return result
case=@CASE@
if case=='two_cube_shells':
    bm=bmesh.new()
    bmesh.ops.create_cube(bm,size=2)
    bmesh.ops.create_cube(bm,size=2,matrix=Matrix.Translation((4,0,0)))
    data=bpy.data.meshes.new('TwinCubes-data');bm.to_mesh(data);bm.free()
    ob=bpy.data.objects.new('TwinCubes',data);bpy.context.scene.collection.objects.link(ob)
    result=inspect(view='mesh',name=ob.name,fields=['*'])
    assert len(result['data']['shells'])==2,result
    assert sorted(row['faces'] for row in result['data']['shells'])==[6,6],result
    assert all(row['closed'] for row in result['data']['shells']),result
    assert result['data']['counts']['faces']==12 and result['data']['holes']==[] and result['count']==0,result
    assert result['data']['defects']['flipped_shells']==0,result
elif case=='suzanne_uv_unwrap':
    bpy.ops.mesh.primitive_monkey_add()
    source=bpy.context.object;source.name='Suzanne'
    # This fixture represents an untextured import with no UV layer.
    for layer in list(source.data.uv_layers):source.data.uv_layers.remove(layer)
    before=inspect(view='uv',name=source.name)
    assert before['data']['layers']==[],before
    assert any('lampway_uv_unwrap' in help for help in before['help']),before
    unwrapped=api.call('uv_unwrap',json.dumps({'object':source.name,'method':'smart','engine':'algorithmic','texture_size':256}))
    assert unwrapped.get('ok') and unwrapped['object']!=source.name,unwrapped
    target=bpy.data.objects[unwrapped['object']]
    assert target.data!=source.data and len(source.data.uv_layers)==0
    result=inspect(view='uv',name=target.name,budget_ms=60000)
    assert result['data']['layers'] and result['data']['islands_total']>0,result
    assert inspect(view='uv',name=source.name)['data']['layers']==[]
elif case=='cube_on_plane':
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,0,1))
    cube=bpy.context.object;cube.name='A_Cube'
    bpy.ops.mesh.primitive_plane_add(size=8,location=(0,0,0))
    plane=bpy.context.object;plane.name='B_Plane'
    bpy.context.view_layer.update()
    result=inspect(view='relations',names=[cube.name,plane.name],fields=['*'])
    assert result['count']==1,result
    pair=result['data']['pairs'][0]
    assert (pair['a'],pair['b'],pair['relation'],pair['gap_m'])==(cube.name,plane.name,'on_top_of',0),result
print('ORIGINAL_RESULT '+json.dumps({'case':case,'verified':True,'output':result}))
'''
