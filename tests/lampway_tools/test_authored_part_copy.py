# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact authored face ownership prepares a copy; source seam approval stays separate."""
import pytest
from features_support import run

SETUP = r'''
from pathlib import Path
me=bpy.data.meshes.new('gear')
me.from_pydata([(0,0,0),(1,0,0),(0,1,0),(-1,0,0),(0,-1,0),(9,9,9)],[],[(0,1,2),(0,3,4)])
ob=link(bpy.data.objects.new('gear',me))
part=me.attributes.new('part','INT','FACE');part.data[0].value=7;part.data[1].value=9
uv=me.uv_layers.new(name='authoredUV')
for i,u in enumerate(uv.data):u.uv=(i/8,i/12)
mark=me.attributes.new('marker','INT','POINT')
for i,x in enumerate(mark.data):x.value=100+i
for n in ('plate','skirt'):
 g=ob.vertex_groups.new(name=n);g.add([0,1,2] if n=='plate' else [0,3,4],1,'REPLACE')
for n in ('first','second'):me.materials.append(bpy.data.materials.new(n))
me.polygons[1].material_index=1
(Path(root)/'roles.json').write_text(json.dumps({'parts':{'plate':{'material_role':'metal'},'skirt':{'material_role':'cloth'}}}))
args={'mode':'separate_parts','face_attribute':'part','part_names':{'7':'plate','9':'skirt'},'recipe':'roles.json'}
'''


def test_exact_face_owners_split_point_contacts_preserve_corner_data_and_source(tmp_path):
    r=run(tmp_path,SETUP+r'''
before=[tuple(v.co) for v in me.vertices]
out=call('segment_mesh',object='gear',labels=args)
data={'out':out}
if out.get('ok'):
 copy=bpy.data.objects[out['object']];m=copy.data
 ids=[x.value for x in m.attributes['lw_part_source_vertex'].data]
 data.update(vertices=len(m.vertices),ids=ids,source_unchanged=before==[tuple(v.co) for v in me.vertices],
  corners=[[ids[i] for i in f.vertices] for f in m.polygons],uv=[tuple(x.uv) for x in m.uv_layers['authoredUV'].data],
  materials=[f.material_index for f in m.polygons],marker=[x.value for x in m.attributes['marker'].data],
  groups={g.name:[v.index for v in m.vertices if any(x.group==g.index and x.weight>0 for x in v.groups)] for g in copy.vertex_groups},
  receipt=json.loads(copy['lw_authored_part_copy']))
print('RESULT '+json.dumps(data))
''')
    assert r.rc==0,r.out[-2500:]
    d=r.results[-1];assert d['out']['ok'],d
    assert d['vertices']==6 and d['ids'].count(0)==2 and 5 not in d['ids'],d
    assert d['corners']==[[0,1,2],[0,3,4]] and d['materials']==[0,1] and d['source_unchanged'],d
    assert all(abs(x[0]-i/8)<1e-7 and abs(x[1]-i/12)<1e-7 for i,x in enumerate(d['uv'])),d
    assert d['marker']==[100+i for i in d['ids']],d
    assert not set(d['groups']['plate'])&set(d['groups']['skirt']),d
    assert d['receipt']['source_seams'] and d['receipt']['physical_status']=='unreviewed',d


@pytest.mark.parametrize('bad', [{'part_names':{'7':'plate'}},{'part_names':{'7':'plate','9':'plate'}},{'face_attribute':'missing'}])
def test_invalid_authored_ownership_refuses_without_publication(tmp_path,bad):
    r=run(tmp_path,SETUP+'\nargs.update('+repr(bad)+r''')
objects=set(bpy.data.objects.keys());meshes=set(bpy.data.meshes.keys())
out=call('segment_mesh',object='gear',labels=args)
print('RESULT '+json.dumps({'out':out,'objects_unchanged':set(bpy.data.objects.keys())==objects,'meshes_unchanged':set(bpy.data.meshes.keys())==meshes}))
''')
    assert r.rc==0,r.out[-1500:]
    d=r.results[-1];assert not d['out']['ok'] and d['objects_unchanged'] and d['meshes_unchanged'],d


def test_shared_edge_copy_transports_normal_vectors_not_old_packed_fan_coordinates(tmp_path):
    setup=SETUP.replace("(0,3,4)","(1,0,3)").replace("(-1,0,0)","(0,0,1)")
    r=run(tmp_path,setup+r'''
for f in me.polygons:f.use_smooth=True
me.normals_split_custom_set([(0.37139067,0.21930185,0.90209798)]*len(me.loops))
original=np.array([n.vector[:] for n in me.corner_normals],dtype=np.float32)
packed=np.empty(len(me.loops)*2,dtype=np.int32);me.attributes['custom_normal'].data.foreach_get('value',packed)
out=call('segment_mesh',object='gear',labels=args)
data={'out':out}
if out.get('ok'):
 copy=bpy.data.objects[out['object']].data
 preserved=np.array([n.vector[:] for n in copy.attributes['lw_part_source_normal'].data],dtype=np.float32)
 wrong=copy.copy();wrong.attributes['custom_normal'].data.foreach_set('value',packed);wrong.update()
 wrong_normals=np.array([n.vector[:] for n in wrong.corner_normals],dtype=np.float32)
 data.update(source_normals_exact=bool(np.array_equal(preserved,original)),
  wrong_packed_delta=float(np.linalg.norm(wrong_normals-original,axis=1).max()),
  transported_delta=out['native_decoded_normal_max_vector_delta'])
 bpy.data.meshes.remove(wrong)
print('RESULT '+json.dumps(data))
''')
    assert r.rc==0,r.out[-2500:]
    d=r.results[-1];assert d['out']['ok'] and d['source_normals_exact'],d
    assert d['wrong_packed_delta']>d['transported_delta'],d


def test_source_seam_ledger_survives_changed_copy_coordinates(tmp_path):
    r=run(tmp_path,SETUP+r'''
out=call('segment_mesh',object='gear',labels=args);copy=bpy.data.objects[out['object']]
group=copy.vertex_groups['skirt'].index
for v in copy.data.vertices:
 if any(g.group==group for g in v.groups):v.co.x+=.1
copy.data.update()
ad=bpy.data.armatures.new('rig');arm=link(bpy.data.objects.new('rig',ad));bpy.context.view_layer.objects.active=arm
bpy.ops.object.mode_set(mode='EDIT')
a=ad.edit_bones.new('spine_01');a.head=(0,0,0);a.tail=(0,0,1)
b=ad.edit_bones.new('spine_03');b.head=(0,0,1);b.tail=(0,0,2);b.parent=a
bpy.ops.object.mode_set(mode='OBJECT')
plan=call('fit_bind',stage='plan',piece=copy.name,armature=arm.name,roles={'plate':'metal','skirt':'metal'},
 bind_overrides={'plate':{'bones':['spine_01'],'reason':'fixture'},'skirt':{'bones':['spine_03'],'reason':'fixture'}},out_dir='bind')
print('RESULT '+json.dumps(plan))
''')
    assert r.rc==0,r.out[-2500:]
    d=r.results[-1];assert d['ok'] and d['seam_opens'],d
    assert d['seam_opens'][0]['parts']==['plate','skirt'],d


@pytest.mark.parametrize('mutation', [
    "copy.data.attributes['lw_part_source_vertex'].data[0].value=4",
    "copy.vertex_groups['plate'].remove([0])",
    "me.attributes['part'].data[0].value=9",
    "me.vertices[0].co.x+=1",
    "record=json.loads(copy['lw_authored_part_copy']);record['source_seams']=[];copy['lw_authored_part_copy']=json.dumps(record)",
])
def test_stale_identity_ownership_and_seam_ledgers_refuse(mutation,tmp_path):
    r=run(tmp_path,SETUP+r'''
out=call('segment_mesh',object='gear',labels=args);copy=bpy.data.objects[out['object']]
''' +mutation+r'''
from mixar.modules.lampway_tools.features.authored_parts import source_seams
try:
 source_seams(copy,root);error=None
except Exception as e:error=str(e)
print('RESULT '+json.dumps({'error':error}))
''')
    assert r.rc==0,r.out[-2500:]
    d=r.results[-1];assert d['error'] and 're-run lampway_segment_mesh' in d['error'],d
