# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect the exact lane overlay on a real isolated binary; never sync an install."""
import json
import os
from pathlib import Path
import subprocess

import pytest


def test_inspect_all_views_read_raw_synthetic_scene_without_edits(tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required; installed app is never synced')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'inspect.py'
    script.write_text('''import sys,json
sys.path.insert(0, OVERLAY)
import bpy,mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar')
mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
assert api.__file__.startswith(OVERLAY),api.__file__
assert 'inspect' in api.TOOL_FUNCS,api.TOOL_FUNCS
cube=bpy.data.objects['Cube']
cube['lw_raw']='synthetic raw fixture'
before=(len(bpy.data.objects),len(bpy.data.meshes),len(cube.data.vertices),len(cube.data.polygons),[o.name for o in bpy.context.selected_objects])
outputs={}
for view in ['home','scene','objects','object','mesh','uv','parts','layers','relations','file','schema','help']:
    args={} if view=='home' else {'view':view}
    if view in ['object','mesh','uv','parts','layers']:args['name']='Cube'
    if view in ['schema','help']:args['name']='mesh'
    output=api.call('inspect',json.dumps(args))
    assert output.get('ok'),(view,output)
    outputs[view]=output
assert outputs['mesh']['data']['holes']==[],outputs['mesh']
assert outputs['mesh']['count']==0,outputs['mesh']
assert outputs['object']['data']['canon']['state']=='raw',outputs['object']
assert outputs['objects']['data']['objects'][0]['name']=='Cube',outputs['objects']
assert api.call('inspect',json.dumps({'view':'objects','typo':1}))['code']=='unknown_argument'
assert api.call('inspect',json.dumps({'view':'objects','fields':['not_a_field']}))['code']=='unknown_field'
assert api.call('inspect',json.dumps({'view':'object','name':'Cube','fields':['not_a_field']}))['code']=='unknown_field'
scene_page=api.call('inspect',json.dumps({'view':'scene','limit':1,'offset':1}))
assert scene_page['data']['cameras']==[],scene_page
assert scene_page['data']['cameras_count']==0 and scene_page['data']['cameras_total']==1,scene_page
assert len(scene_page['data']['render']['resolution'])==2,scene_page
object_page=api.call('inspect',json.dumps({'view':'object','name':'Cube','limit':1,'offset':1}))
assert object_page['data']['materials_count']==0 and object_page['data']['materials_total']==1,object_page
assert len(object_page['data']['location'])==3,object_page
filtered=api.call('inspect',json.dumps({'view':'objects','match':'Cube','fields':['name'],'limit':1}))
assert filtered['data']['objects']==[{'name':'Cube'}],filtered
assert 'match=Cube' in filtered['help'][0] and 'fields=<fields>' in filtered['help'][0],filtered
assert api.call('inspect',json.dumps({'view':'mesh','name':'Camera'}))['code']=='wrong_type'
camera_detail=api.call('inspect',json.dumps({'view':'object','name':'Camera'}))
assert camera_detail['data']['layers']=={'count':0,'top':None},camera_detail
assert api.call('inspect',json.dumps({'view':'object','name':'Missing'}))['code']=='not_found'
after=(len(bpy.data.objects),len(bpy.data.meshes),len(cube.data.vertices),len(cube.data.polygons),[o.name for o in bpy.context.selected_objects])
assert after==before,(before,after)
# Change only our synthetic fixture and prove cache invalidation/definitive holes.
import bmesh
bm=bmesh.new();bm.from_mesh(cube.data);bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm,geom=[bm.faces[0]],context='FACES')
bm.to_mesh(cube.data);bm.free();cube.data.update()
opened=api.call('inspect',json.dumps({'view':'mesh','name':'Cube'}))
assert opened['count']==1,opened
assert opened['data']['holes'][0]['edges']==4,opened
assert opened['skipped']==[] and opened['data']['defects']['flipped_shells']==0,opened
scene_fields=api.call('inspect',json.dumps({'view':'scene','fields':['name']}))
print('INSPECT_RESULT '+json.dumps({'overlay':api.__file__,'outputs':outputs,'scene_fields':scene_fields}))
'''.replace('OVERLAY', repr(overlay)))
    env = os.environ.copy()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME',
                'LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        directory=tmp_path/key.lower()
        directory.mkdir()
        env[key]=str(directory)
    env['LAMPWAY_PROJECT_ROOT']=str(tmp_path/'project')
    run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec',
        '--python-exit-code','1','--python',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    assert run.returncode==0,run.stdout[-9000:]
    rows=[line.removeprefix('INSPECT_RESULT ') for line in run.stdout.splitlines() if line.startswith('INSPECT_RESULT ')]
    assert len(rows)==1,run.stdout[-9000:]
    output=json.loads(rows[0])
    assert len(output['outputs'])==12
    import jsonschema
    from mixar.modules.lampway_tools.inspect.schema import view_schema
    jsonschema.validate(output['scene_fields'], view_schema('scene'))
    for view, value in output['outputs'].items():
        jsonschema.validate(value, view_schema(view))
