# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Precise surfaces and intra-island folds, on an isolated source overlay."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import LOAD_OBJ


@pytest.mark.parametrize('section', ['relations', 'uv'])
def test_relations_and_uv_surface_falsifiers(tmp_path, section):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'geometry.py'
    script.write_text('''import sys,json
sys.path.insert(0,OVERLAY)
import bpy,mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar');mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api
from mixar.modules.lampway_tools.features import uv_check as UC
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
def mesh(name,vs,fs):
    m=bpy.data.meshes.new(name);m.from_pydata(vs,[],fs);o=bpy.data.objects.new(name,m);bpy.context.scene.collection.objects.link(o);return o
a=mesh('A',[(0,0,0),(2,0,0),(0,2,0)],[(0,1,2)])
b=mesh('B',[(2,2,.2),(1.5,2,.2),(2,1.5,.2)],[(0,1,2)])
bpy.context.view_layer.update()
def relation(names,deep=False,**kw):
    r=api.call('inspect',json.dumps(dict(view='relations',names=names,deep=deep,**kw)))
    assert r['ok'],r
    assert not r['skipped'],r
    return r['data']['pairs'][0]
# Their boxes overlap in XY; their surfaces remain sqrt(1.125+.2**2) apart.
r=relation(['A','B'],True)
assert abs(r['gap_m']-(1.125+.2**2)**.5)<.0001,r
assert r['relation']=='apart',r
# Base triangles are .2 apart in Z, evaluation raises the first by .1.
mod=a.modifiers.new('Raise','DISPLACE');mod.strength=.1;mod.mid_level=0;mod.direction='Z'
r=relation(['A','B'],True)
assert abs(r['gap_m']-(1.125+.1**2)**.5)<.0001,r
# Edge-interior minima: neither rectangle has a vertex over the other.
x=mesh('X',[(-2,-.1,0),(2,-.1,0),(2,.1,0),(-2,.1,0),(0,0,.2)],[(0,1,2,3)])
y=mesh('Y',[(-.1,-2,.2),(.1,-2,.2),(.1,2,.2),(-.1,2,.2)],[(0,1,2,3)])
bpy.context.view_layer.update()
r=relation(['X','Y'],True)
assert abs(r['gap_m']-.2)<.0001,r
# Metres apply before BVH construction, not after comparing tolerance.
bpy.context.scene.unit_settings.scale_length=.01
r=relation(['X','Y'],True,tolerance_m=.003)
assert r['gap_m']==.002 and r['relation']=='touching',r
bpy.context.scene.unit_settings.scale_length=1
# Bounds must remain unrounded through zero-tolerance classification.
x.data.vertices[-1].co.z=-.2;x.data.update()
y.location.z=-.19996
bpy.context.view_layer.update()
r=relation(['X','Y'],False,tolerance_m=0)
assert r['relation']=='near',r
# Closed volume containment uses parity, including reverse winding.
def cube(name,size):
    bpy.ops.mesh.primitive_cube_add(size=size)
    ob=bpy.context.object;ob.name=name;return ob
outer=cube('Outer',4);inner=cube('Inner',1)
r=relation(['Inner','Outer'],True)
assert r['relation']=='inside' and r['gap_m']==1.5,r
r=relation(['Outer','Inner'],True)
assert r['relation']=='overlaps' and r['gap_m']==1.5,r
side=cube('Side',1);side.location.x=1
bpy.context.view_layer.update()
r=relation(['Inner','Side'],True)
assert r['relation']=='touching' and r['gap_m']==0,r
# A face-interior crossing has no inside vertices but zero surface distance.
z=mesh('Cross',[(-3,0,-3),(3,0,-3),(3,0,3),(-3,0,3)],[(0,1,2,3)])
bpy.context.view_layer.update()
r=relation(['Outer','Cross'],True)
assert r['relation']=='overlaps' and r['gap_m']==0,r
# Connected fold: both triangles share the same UV corner identities.
o=mesh('Fold',[(0,0,0),(1,0,0),(0,1,0),(0,-1,0)],[(0,1,2),(1,0,3)])
u=o.data.uv_layers.new(name='UVMap')
coords=[(0,0),(1,0),(0,1),(0,1)]
for p in o.data.polygons:
    for l in p.loop_indices:u.data[l].uv=coords[o.data.loops[l].vertex_index]
r=api.call('inspect',json.dumps(dict(view='uv',name='Fold')))
assert r['ok'] and r['data']['islands_total']==1,r
assert r['data']['overlap_fraction']==1,r
# Shared edge alone owns each texel once under the canon half-open rule.
coords[3]=(0,-1)
for p in o.data.polygons:
    for l in p.loop_indices:u.data[l].uv=coords[o.data.loops[l].vertex_index]
r=api.call('inspect',json.dumps(dict(view='uv',name='Fold')))
assert r['data']['overlap_fraction']==0,r
# Deliberately stacked mirrored islands are reported by the shared overlap engine.
stack=mesh('Stack',[(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],[(0,1,2),(3,4,5)])
uv=stack.data.uv_layers.new(name='UVMap')
for index,coord in enumerate([(0,0),(1,0),(0,1),(0,0),(0,1),(1,0)]):uv.data[index].uv=coord
r=api.call('inspect',json.dumps(dict(view='uv',name='Stack')))
assert r['data']['overlap_fraction']==1 and r['data']['flipped_faces']==0,r
print('GEOMETRY_RESULT '+json.dumps(r))
'''.replace('OVERLAY',repr(overlay)))
    golden_root = Path(__file__).resolve().parents[2] / 'docs/canon/goldens/C09_uv'
    script.write_text(script.read_text() + LOAD_OBJ + f"\nGOLD={str(golden_root)!r}\n" + '''
for name, coverage, overlap in [('three_islands',.4375,0),('overlap',.3125,.4)]:
    ob=load_obj(GOLD+'/'+name+'.obj','Golden'+name)
    r=api.call('inspect',json.dumps(dict(view='uv',name=ob.name)))
    assert r['ok'] and not r['skipped'],r
    assert r['data']['utilization']==coverage and r['data']['overlap_fraction']==overlap,r
''')
    if section == 'uv':
        source = script.read_text()
        start = source.index("# Their boxes")
        end = source.index("# Connected fold")
        script.write_text(source[:start] + source[end:])
    env = os.environ.copy()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        path=tmp_path/key.lower();path.mkdir();env[key]=str(path)
    env['LAMPWAY_PROJECT_ROOT']=str(tmp_path/'project')
    run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    assert run.returncode==0,run.stdout[-10000:]
    assert 'GEOMETRY_RESULT ' in run.stdout
