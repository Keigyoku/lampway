# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real metric/evaluated geometry falsifiers, with no installed app sync."""
import os
from pathlib import Path
import subprocess
import pytest


def test_metric_defects_and_exact_orientation(tmp_path):
    binary = os.environ.get('LAMPWAY_INSPECT_BIN')
    if not binary:
        pytest.skip('LAMPWAY_INSPECT_BIN required; no installed app sync')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'defects.py'
    script.write_text('''import sys
sys.path.insert(0, OVERLAY)
import bpy,bmesh,mixar,mixar.modules
mixar.__path__.insert(0,OVERLAY+'/mixar');mixar.modules.__path__.insert(0,OVERLAY+'/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0,OVERLAY+'/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools.inspect import mesh
from mixar.modules.lampway_tools.features import workflows as W, defect_scan as DS
ob=bpy.data.objects['Cube']
before=(tuple(v.co[:] for v in ob.data.vertices),tuple(tuple(p.vertices) for p in ob.data.polygons),len(bpy.data.meshes),[o.name for o in bpy.context.selected_objects])
result=mesh.measure(ob,scale=0.01,deep=True)
assert result['skipped']==[] and result['defects']['flipped_shells']==0,result
assert result['intersections']==[] and result['thin_regions']==[],result
# A perimeter just below a half step must never round through five decimals.
data=bpy.data.meshes.new('rounding-rim')
d=0.113747/4;data.from_pydata([(0,0,0),(d,0,0),(d,d,0),(0,d,0)],[],[(0,1,2,3)])
rim=bpy.data.objects.new('rounding-rim',data);bpy.context.scene.collection.objects.link(rim)
inspected=mesh.measure(rim)['holes'][0]
scanned=DS.run(rim.name,kinds=['open_loop'])['candidates'][0]['descriptor']
assert inspected['rim_length_m']==0.1137 and scanned['rim_length_m']==0.1137,(inspected,scanned)
# Nonuniform reflection preserves the authored orientation, canon 01 D.4.
ob.scale=(-2,3,0.0005);bpy.context.view_layer.update()
result=mesh.measure(ob,deep=True)
assert result['defects']['flipped_shells']==0 and len(result['thin_regions'])==2,result
assert {tuple(row['descriptor']['bbox']) for row in result['thin_regions']}=={(-2.0,-3.0,-0.0005,2.0,3.0,-0.0005),(-2.0,-3.0,0.0005,2.0,3.0,0.0005)},result
# Flip authored winding and retain all six exact face votes.
bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free()
result=mesh.measure(ob)
assert result['defects']['flipped_shells']==1 and result['skipped']==[],result
assert W.shell_orientation(ob)==[{'shell':0,'faces':6,'outward_fraction':0.0}],W.shell_orientation(ob)
assert DS.run(ob.name,kinds=['flipped_shell'])['counts']=={'flipped_shell':1}
# Open shells retain the exact existing ray vote and every boundary loop.
bm=bmesh.new();bmesh.ops.create_cone(bm,cap_ends=False,cap_tris=False,segments=24,radius1=0.5,radius2=0.5,depth=1)
bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
data=bpy.data.meshes.new('open-tube');bm.to_mesh(data);bm.free()
tube=bpy.data.objects.new('open-tube',data);bpy.context.scene.collection.objects.link(tube)
result=mesh.measure(tube,scale=0.01)
assert result['defects']['flipped_shells']==1 and len(result['holes'])==2 and all(h['edges']==24 for h in result['holes']),result
assert DS.run(tube.name,kinds=['open_loop','flipped_shell'])['counts']=={'open_loop':2,'flipped_shell':1}

# Evaluated subdivision changes the topology; never look up the source by name.
modifier=ob.modifiers.new('detail','SUBSURF');modifier.levels=1
bpy.context.view_layer.update()
evaluated=ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
result=mesh.measure(evaluated,scale=0.01,deep=True)
assert result['counts']['faces']==24 and result['defects']['flipped_shells']==1 and result['skipped']==[],result
# Crossing disconnected surfaces: BVH intersection groups and descriptor units.
data=bpy.data.meshes.new('crossing');data.from_pydata([(-100,-100,0),(100,-100,0),(0,100,0),(0,-50,-100),(0,-50,100),(0,50,0)],[],[(0,1,2),(3,4,5)])
cross=bpy.data.objects.new('crossing',data);bpy.context.scene.collection.objects.link(cross)
result=mesh.measure(cross,scale=0.01,deep=True)
assert len(result['intersections'])==1 and result['intersections'][0]['descriptor']['bbox']==[-1.0,-1.0,-1.0,1.0,1.0,1.0],result
# More than the public scanner's 500 row cap: aggregates remain exact.
vertices=[];faces=[]
for i in range(501):
    x=i*4;base=len(vertices)
    vertices.extend([(x-1,-1,0),(x+1,-1,0),(x,1,0),(x,-0.5,-1),(x,-0.5,1),(x,0.5,0)])
    faces.extend([(base,base+1,base+2),(base+3,base+4,base+5)])
data=bpy.data.meshes.new('many-crossings');data.from_pydata(vertices,[],faces)
many=bpy.data.objects.new('many-crossings',data);bpy.context.scene.collection.objects.link(many)
result=mesh.measure(many,deep=True)
assert result['intersections_total']==501 and len(result['intersections'])==501,result
# Read-only measurements leave data, active object, mode and selection unchanged.
snapshot=lambda:(tuple(v.co[:] for v in ob.data.vertices),tuple(tuple(p.vertices) for p in ob.data.polygons),len(bpy.data.meshes),[o.name for o in bpy.context.selected_objects],bpy.context.view_layer.objects.active.name,ob.mode)
state=snapshot();mesh.measure(evaluated,scale=0.01,deep=True);assert snapshot()==state
assert len(ob.data.polygons)==6 and len(ob.modifiers)==1
# Cancellation during traversal frees the temporary BMesh and leaves scene data intact.
created=[];real_new=bmesh.new
class Cancel:
    calls=0
    def admit_geometry(self,data): pass
    def check(self):
        self.calls+=1
        if self.calls==30: raise TimeoutError('fixture deadline')
def tracked_new():
    bm=real_new();created.append(bm);return bm
bmesh.new=tracked_new
try:
    try: mesh.measure(evaluated,scale=0.01,deep=True,budget=Cancel())
    except TimeoutError: pass
    else: raise AssertionError('cancellation did not propagate')
finally: bmesh.new=real_new
assert created and all(not bm.is_valid for bm in created)
assert snapshot()==state
print('DEFECT_METRIC_OK')
'''.replace('OVERLAY', repr(overlay)))
    env=os.environ.copy()
    for key in ('HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME','XDG_CACHE_HOME','LAMPWAY_HOME','LAMPWAY_LEGACY_HOME','TMPDIR'):
        folder=tmp_path/key.lower();folder.mkdir();env[key]=str(folder)
    env['LAMPWAY_PROJECT_ROOT']=str(tmp_path/'project')
    run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    assert run.returncode==0,run.stdout[-6000:]
    assert 'DEFECT_METRIC_OK' in run.stdout
