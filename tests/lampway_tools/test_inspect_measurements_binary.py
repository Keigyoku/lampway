# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic T1 measurement falsifiers in the real binary, without installed Python sync."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('case', ['uv_flipped', 'uv_seam', 'uv_udim_overlap', 'uv_empty', 'rim_centroid', 'parts_rounding', 'parts_double_rounding', 'uv_degenerate', 'deep_scaled_skipped', 'deep_evaluated_skipped', 'mesh_empty'])
def test_measurement(case, tmp_path):
    binary = os.environ.get('LAMPWAY_VIEW_BIN')
    if not binary:
        pytest.skip('LAMPWAY_VIEW_BIN required; isolated background test never syncs installed app')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'measure.py'
    script.write_text('''import sys
sys.path.insert(0, OVERLAY)
import bpy, bmesh, mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY + '/mixar')
mixar.modules.__path__.insert(0, OVERLAY + '/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0, OVERLAY + '/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools.inspect import mesh, uv, parts
assert uv.__file__.startswith(OVERLAY)
def make(vertices, faces, coordinates=None):
    data=bpy.data.meshes.new('synthetic-data')
    data.from_pydata(vertices, [], faces)
    ob=bpy.data.objects.new('synthetic', data)
    bpy.context.scene.collection.objects.link(ob)
    if coordinates is not None:
        layer=data.uv_layers.new()
        for loop, coordinate in zip(layer.data, coordinates): loop.uv=coordinate
    return ob
case=CASE
if case == 'uv_flipped':
    ob=make([(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0),(4,0,0),(5,0,0),(4,1,0)],
            [(0,1,2),(3,4,5),(6,7,8)], [(0,0),(1,0),(0,1),(0,0),(1,0),(0,1),(0,0),(0,1),(1,0)])
    result=uv.measure(ob)
    assert type(result['flipped_faces']) is int and result['flipped_faces']==1, result
elif case == 'uv_seam':
    ob=make([(0,0,0),(0.003456,0,0),(0,1,0),(0,-1,0)],[(0,1,2),(1,0,3)],
            [(0,0),(1,0),(0,1),(0,0),(1,0),(0,1)])
    result=uv.measure(ob)
    assert result['seam_length_m']==0.0035, result
elif case == 'uv_udim_overlap':
    ob=make([(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],[(0,1,2),(3,4,5)],
            [(1.1,0.1),(1.9,0.1),(1.1,0.9)]*2)
    result=uv.measure(ob)
    assert result['overlap_fraction']==1.0 and result['tiles']==[1002],result
elif case == 'uv_empty':
    ob=make([],[],[])
    result=uv.measure(ob)
    assert result['flipped_faces']==0 and result['islands']==[],result
elif case == 'rim_centroid':
    bpy.ops.mesh.primitive_cube_add()
    ob=bpy.context.object
    bm=bmesh.new(); bm.from_mesh(ob.data)
    face=max(bm.faces,key=lambda f:f.calc_center_median().z)
    bmesh.ops.delete(bm,geom=[face],context='FACES_ONLY'); bm.to_mesh(ob.data);bm.free()
    result=mesh.measure(ob)
    assert result['holes'][0]['centroid']=={'x':0.0,'y':0.0,'z':1.0},result
    assert 'flipped_shells' in result['defects'],result
elif case == 'parts_rounding':
    ob=make([(0.123456,0,0),(1.123456,0,0),(0.123456,1,0)],[(0,1,2)])
    result=parts.measure(ob)
    assert result['parts'][0]['bounds']['min'][0]==0.1235,result
elif case == 'parts_double_rounding':
    ob=make([(0.123449,0,0),(1.123449,0,0),(0.123449,1,0)],[(0,1,2)])
    result=parts.measure(ob)
    assert result['parts'][0]['bounds']['min'][0]==0.1234,result
elif case == 'uv_degenerate':
    ob=make([(0,0,0),(0,0,0),(0,0,0)],[(0,1,2)],[(0,0),(0,0),(0,0)])
    result=uv.measure(ob)
    assert result['density']['mean_px_m'] is None and result['flipped_faces']==0,result
elif case == 'deep_scaled_skipped':
    result=mesh.measure(bpy.data.objects['Cube'],scale=0.01,deep=True)
    assert result['defects']['flipped_shells'] is None,result
    assert {row['section'] for row in result['skipped']}=={'flipped_shells','intersections','thin_regions'},result
elif case == 'deep_evaluated_skipped':
    ob=bpy.data.objects['Cube']
    modifier=ob.modifiers.new('detail','SUBSURF');modifier.levels=1
    evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result=mesh.measure(evaluated,deep=True)
    assert result['counts']['faces']==24,result
    assert result['defects']['flipped_shells'] is None,result
    assert {row['section'] for row in result['skipped']}=={'flipped_shells','intersections','thin_regions'},result
elif case == 'mesh_empty':
    result=mesh.measure(make([],[]),scale=0.01,deep=True)
    assert result['holes']==[] and result['intersections']==[] and result['thin_regions']==[],result
    assert result['defects']['flipped_shells']==0 and result['skipped']==[],result
print('MEASURE_OK',case)
'''.replace('OVERLAY', repr(overlay)).replace('CASE', repr(case)))
    env = os.environ.copy()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        folder=tmp_path/key.lower();folder.mkdir();env[key]=str(folder)
    env['LAMPWAY_PROJECT_ROOT']=str(tmp_path/'project')
    run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],
                       env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    assert run.returncode==0,run.stdout[-4500:]
    assert 'MEASURE_OK '+case in run.stdout
