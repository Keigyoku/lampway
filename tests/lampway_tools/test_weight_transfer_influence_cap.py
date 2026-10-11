# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon07 B.9: real twelve-influence source survives omitted cap; explicit cap retained."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from isolated_binary import run
from test_wave3_weights import PRE
ARMATURE=PRE[PRE.index('def armature'):PRE.index('def tube')]

@pytest.mark.parametrize('entrypoint',['feature','public'])
@pytest.mark.parametrize('cap',[None,4])
def test_transfer_retains_all_twelve_native_influences_unless_caller_caps(tmp_path,cap,entrypoint):
    body=ARMATURE+'''
from mixar.modules.lampway_tools.features import weights as WT
api.settings_set(project_root=root)
bones=tuple(('bone_%02d'%i,(0,0,i*.1),(0,0,(i+1)*.1),None if i==0 else 'bone_%02d'%(i-1)) for i in range(12))
arm=armature(bones=bones)
def triangle(name):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)]);mesh.update()
    ob=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(ob);return ob
source=triangle('source');target=triangle('target')
for i in range(12):source.vertex_groups.new(name='bone_%02d'%i).add([0,1,2],1/12,'REPLACE')
mod=source.modifiers.new('Armature','ARMATURE');mod.object=arm
kwargs=CAP_ARGS
result=TRANSFER('target','source',**kwargs)
output=bpy.data.objects[result['object']]
rows=[{output.vertex_groups[g.group].name:float(g.weight) for g in v.groups if g.weight>0} for v in output.data.vertices]
print('RESULT '+json.dumps({'result':result,'rows':rows,'source_counts':[len(v.groups) for v in source.data.vertices],'target_counts':[len(v.groups) for v in target.data.vertices]}))
'''.replace('CAP_ARGS',repr({} if cap is None else {'limit_groups':cap})).replace('TRANSFER', 'WT.transfer' if entrypoint=='feature' else 'api.weight_transfer')
    result=run(tmp_path,body)
    assert result.rc==0,result.out[-3000:]
    d=result.results[-1]
    assert all(len(row)==(12 if cap is None else cap) for row in d['rows']),d
    assert all(abs(sum(row.values())-1)<1e-6 for row in d['rows']),d
    assert d['result']['influence_histogram'].get(str(12 if cap is None else cap))==3,d
    assert d['result']['max_influences']==(12 if cap is None else cap),d
    assert d['source_counts']==[12]*3 and d['target_counts']==[0]*3,d
