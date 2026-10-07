# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T1 observes canonical placement and transactional import refusals on real Blender."""
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('case', ['translated_canonical', 'refused_file_counts'])
def test_inspection_canon_integration(case, tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required; never syncs an installed app')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'integration.py'
    script.write_text(_SCRIPT.replace('@OVERLAY@', repr(overlay)).replace('@CASE@', repr(case)))
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        directory = tmp_path / key.lower(); directory.mkdir(); env[key] = str(directory)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    run = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec',
                          '--python-exit-code', '1', '--python', str(script)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    rows = [line.removeprefix('INTEGRATION_RESULT ') for line in run.stdout.splitlines()
            if line.startswith('INTEGRATION_RESULT ')]
    if rows and os.environ.get('LAMPWAY_GEOMETRY_RECEIPTS'):
        receipt = Path(os.environ['LAMPWAY_GEOMETRY_RECEIPTS']); receipt.mkdir(parents=True, exist_ok=True)
        (receipt / (case + '.json')).write_text(json.dumps(json.loads(rows[-1]), indent=2) + '\n')
    assert run.returncode == 0, run.stdout[-10000:]
    assert len(rows) == 1 and json.loads(rows[0])['verified'], run.stdout[-10000:]


_SCRIPT = '''import sys,json,os
from pathlib import Path
OVERLAY=@OVERLAY@
sys.path.insert(0,OVERLAY)
import bpy,bmesh,mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar');mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api,canon_io
assert api.__file__.startswith(OVERLAY),api.__file__
root=Path(os.environ['LAMPWAY_PROJECT_ROOT']);root.mkdir(parents=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def call(tool_name,**args):return api.call(tool_name,json.dumps(args))
def inspect(**args):
    result=call('inspect',**args)
    assert result.get('ok') and not result.get('skipped'),result
    return result
case=@CASE@
outputs={}
if case=='translated_canonical':
    bm=bmesh.new();bmesh.ops.create_cube(bm,size=2)
    top=max(bm.faces,key=lambda face:face.calc_center_median().z)
    bmesh.ops.delete(bm,geom=[top],context='FACES_ONLY')
    data=bpy.data.meshes.new('OpenCube-data');bm.to_mesh(data);bm.free()
    ob=bpy.data.objects.new('OpenCube',data);bpy.context.scene.collection.objects.link(ob)
    normalized=call('normalize_mesh',input=ob.name,turn_deg=0,generator='lampway_tool',weld='never')
    assert normalized.get('ok'),normalized
    before_facts=canon_io.facts(ob)
    before_object=inspect(view='object',name=ob.name)['data']
    before_mesh=inspect(view='mesh',name=ob.name,fields=['*'])['data']
    stamp=ob['lw_canon']
    offset=(2.2,-0.4,0.3);ob.location=offset;bpy.context.view_layer.update()
    again=call('normalize_mesh',input=ob.name,turn_deg=0,generator='lampway_tool',weld='never')
    assert again.get('ok') and again.get('unchanged') is True,again
    assert ob['lw_canon']==stamp and max(abs(a-b) for a,b in zip(ob.location,offset))<1e-6
    after_facts=canon_io.facts(ob)
    assert after_facts['geometry_sha256']==before_facts['geometry_sha256']
    assert after_facts['bbox_min_m']==before_facts['bbox_min_m'] and after_facts['bbox_max_m']==before_facts['bbox_max_m']
    placed_object=inspect(view='object',name=ob.name)['data']
    placed_mesh=inspect(view='mesh',name=ob.name,fields=['*'])['data']
    assert placed_object['canon']==before_object['canon'] and placed_object['canon']['state']=='canonical'
    for endpoint in ('min','max'):
        expected=[round(a+b,4) for a,b in zip(before_object['bounds'][endpoint],offset)]
        assert placed_object['bounds'][endpoint]==expected,(endpoint,placed_object,expected)
    expected={axis:round(before_mesh['holes'][0]['centroid'][axis]+delta,4) for axis,delta in zip('xyz',offset)}
    assert placed_mesh['holes'][0]['centroid']==expected,(placed_mesh,expected)
    assert placed_mesh['holes'][0]['rim_length_m']==before_mesh['holes'][0]['rim_length_m']
    assert placed_mesh['defects']==before_mesh['defects']
    assert inspect(view='mesh',name=ob.name,fields=['*'])['data']==placed_mesh
    # A second placement must invalidate the geometry cache again.
    ob.location=(-3,1,2);bpy.context.view_layer.update()
    moved=inspect(view='mesh',name=ob.name,fields=['*'])['data']
    assert moved['holes'][0]['centroid']=={axis:round(before_mesh['holes'][0]['centroid'][axis]+delta,4) for axis,delta in zip('xyz',(-3,1,2))}
    outputs={'before':before_object,'placed':placed_object,'placed_holes':placed_mesh['holes'],'second_holes':moved['holes'],'unchanged_normalization':again['unchanged']}
elif case=='refused_file_counts':
    bpy.ops.mesh.primitive_cube_add();source=bpy.context.object;source.name='RefusedAsset'
    for polygon in source.data.polygons:polygon.use_smooth=True
    material=bpy.data.materials.new('RefusedMaterial');source.data.materials.append(material)
    bpy.ops.export_scene.gltf(filepath=str(root/'refused.glb'),use_selection=True)
    source_data=source.data;bpy.data.objects.remove(source,do_unlink=True);bpy.data.meshes.remove(source_data);bpy.data.materials.remove(material)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(4,0,0));anchor=bpy.context.object;anchor.name='Anchor'
    def counts():
        return {'home':inspect()['data']['counts'],'file':inspect(view='file')['data']['datablocks'],
                'objects':inspect(view='objects',names=['Anchor'],fields=['name'])['data']['objects']}
    before=counts()
    baseline={kind:sorted(block.name for block in getattr(bpy.data,kind)) for kind in ('objects','meshes','materials','images','collections')}
    refused=[]
    for _ in range(3):
        result=call('normalize_mesh',input='refused.glb')
        assert result.get('ok') is False and 'frame undecided' in result.get('error',''),result
        refused.append(result['error'])
        assert counts()==before,(before,counts())
        assert baseline=={kind:sorted(block.name for block in getattr(bpy.data,kind)) for kind in baseline}
        assert call('inspect',view='object',name='RefusedAsset')['code']=='not_found'
    after_refusal=counts()
    accepted=call('normalize_mesh',input='refused.glb',turn_deg=0,generator='captain_authored',weld='never')
    assert accepted.get('ok') and accepted['objects']==['RefusedAsset'],accepted
    after=counts()
    assert after['home']['objects']==before['home']['objects']+1 and after['home']['meshes']==before['home']['meshes']+1,(before,after)
    assert inspect(view='object',name='RefusedAsset')['data']['canon']['state']=='canonical'
    assert bpy.data.objects.get('Anchor') is anchor
    outputs={'before':before,'post_refusal':after_refusal,'accepted':after,'refusals':refused,'accepted_names':accepted['objects']}
print('INTEGRATION_RESULT '+json.dumps({'case':case,'verified':True,'outputs':outputs}))
'''
