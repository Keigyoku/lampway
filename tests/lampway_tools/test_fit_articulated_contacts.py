# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded derived-contact authorization is independent of full fit review."""
import sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'tests/lampway_tools'))
from isolated_binary import run

SETUP = r'''
from pathlib import Path
from mixar.modules.lampway_tools.features import fit_bind as FB
from mixar.modules.lampway_tools.features.workflows import mesh_hash
me=bpy.data.meshes.new('gear')
me.from_pydata([(0,0,0),(1,0,0),(0,1,0),(-1,0,0),(0,-1,0),(0,0,1),(0,-1,1)],[],[(0,1,2),(0,3,4),(0,5,6)])
ob=link(bpy.data.objects.new('gear',me))
part=me.attributes.new('part','INT','FACE')
for i,x in enumerate(part.data): x.value=i
(Path(root)/'roles.json').write_text(json.dumps({'parts':{'torso':{},'pauldron':{},'sleeve':{}}}))
p=api.segment_mesh(object='gear',labels={'mode':'separate_parts','face_attribute':'part','part_names':{'0':'torso','1':'pauldron','2':'sleeve'},'recipe':'roles.json'})
copy=bpy.data.objects[p['object']]
ad=bpy.data.armatures.new('rig');arm=link(bpy.data.objects.new('rig',ad));bpy.context.view_layer.objects.active=arm
bpy.ops.object.mode_set(mode='EDIT')
a=ad.edit_bones.new('spine_01');a.head=(0,0,0);a.tail=(0,0,1)
b=ad.edit_bones.new('upperarm_l');b.head=(0,0,1);b.tail=(1,0,1);b.parent=a
bpy.ops.object.mode_set(mode='OBJECT')
roles={'torso':'metal','pauldron':'metal','sleeve':'cloth'}
overrides={'torso':{'bones':['spine_01'],'reason':'fixture'},'pauldron':{'bones':['upperarm_l'],'reason':'fixture'},'sleeve':{'bones':['spine_01'],'reason':'fixture'}}
identity=FB._band_identity(copy,FB._parts(copy))
contact={'schema':'lampway.articulated-contacts/1','source_sha256':mesh_hash(ob),'prepared_sha256':mesh_hash(copy),'prepared_identity':identity,
 'contacts':[{'parts':['pauldron','torso'],'source_vertices':[0],'retained_source_vertices':[]},{'parts':['pauldron','sleeve'],'source_vertices':[0],'retained_source_vertices':[]}],
 'authorization':{'decision':'release_derived_contacts','scope':'contact_pairs_only','declaration':'Fixture owner authorizes these copied contact pairs only.'}}
overrides['_articulated_contacts']=contact
'''


def execute(tmp_path, body):
    r = run(tmp_path, SETUP + body)
    assert r.rc == 0, r.out[-5000:]
    return r.results[-1]


def test_declared_three_way_contact_releases_pauldron_and_keeps_torso_sleeve(tmp_path):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps(p))
''')
    assert d['ok'],d
    assert not d['seam_opens'],d
    assert len(d['seams'])==3,d
    assert d['articulated_contacts']['physical_status']=='unreviewed',d
    assert d['articulated_contacts']['full_fit_owner_review_accepted'] is False,d


@pytest.mark.parametrize('mutation',[
 "contact['source_sha256']='0'*64", "contact['prepared_sha256']='0'*64", "contact['prepared_identity']='0'*64",
 "contact['contacts'][0]['source_vertices']=[True]", "contact['contacts'][0]['source_vertices']=[1]",
 "contact['contacts'][0]['source_vertices']=[0,0]", "contact['contacts'].append(contact['contacts'][0])",
 "contact['contacts'][0]['parts']=['torso','absent']", "contact['authorization']['scope']='full_fit'",
 "contact['authorization']['captain_seen']=True", "del overrides['pauldron']['bones']", "contact['contacts'][0]['source_vertices']=[]",
 "copy.data.vertices[3].co.x+=.01", "copy.vertex_groups['pauldron'].remove([3])",
])
def test_invalid_or_stale_declaration_refuses_before_publication(tmp_path,mutation):
    d=execute(tmp_path,mutation+r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps({'result':p,'published':(Path(root)/'bind'/'bind_state.json').exists()}))
''')
    assert not d['result']['ok'],d
    assert not d['published'],d


def test_missing_declaration_retains_original_seam_gate(tmp_path):
    d=execute(tmp_path,r'''
del overrides['_articulated_contacts']
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps(p))
''')
    assert d['ok'] and d['seam_opens'],d


def test_weights_releases_only_named_flexible_source_contact(tmp_path):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
 rows=np.zeros((len(idx),len(names)));rows[:,names.index('spine_01')]=1;return rows
FB._restrict_part=region
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
d={'plan':p,'weights':w,'source_unchanged':mesh_hash(ob)==contact['source_sha256']}
if w.get('ok'):
 fit=bpy.data.objects[w['object']];names,W=FB.WT._read(fit,{'spine_01','upperarm_l'})
 d['sleeve_contact_row']=W[6].tolist();d['names']=names
 a=api.fit_bind('apply',piece=copy.name,armature=arm.name,out_dir='bind');d['apply']=a
print('RESULT '+json.dumps(d))
''')
    assert d['weights']['ok'],d
    assert d['sleeve_contact_row'][d['names'].index('spine_01')]==1,d
    assert d['apply']['ok'] and d['source_unchanged'],d
    assert d['apply']['articulated_contacts']['full_fit_owner_review_accepted'] is False,d


def test_partial_original_contact_closure_refuses(tmp_path):
    setup=SETUP.replace('(0,3,4)', '(0,1,4)')
    r=run(tmp_path,setup+r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps({'result':p,'published':(Path(root)/'bind'/'bind_state.json').exists()}))
''')
    assert r.rc==0,r.out[-3000:]
    d=r.results[-1]
    assert not d['result']['ok'] and not d['published'],d
    assert 'closure' in d['result']['error'],d


def test_additional_coincident_contact_with_distinct_source_identity_refuses(tmp_path):
    setup=SETUP.replace('(-1,0,0)', '(1,0,0)')
    r=run(tmp_path,setup+r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps({'result':p,'published':(Path(root)/'bind'/'bind_state.json').exists()}))
''')
    assert r.rc==0,r.out[-3000:]
    d=r.results[-1]
    assert not d['result']['ok'] and not d['published'],d
    assert 'closure' in d['result']['error'],d


@pytest.mark.parametrize('mutation',[
 "copy.location.x+=.1;bpy.context.view_layer.update()",
 "copy.vertex_groups['sleeve'].remove([6])",
 "copy.data.vertices[0].co.x+=.01",
 "state=json.loads(path.read_text());state['plan']['articulated_contacts']['authorization']['declaration']='changed';path.write_text(json.dumps(state))",
 "state=json.loads(path.read_text());state['plan']['parts']['pauldron']['bones']=['spine_01'];path.write_text(json.dumps(state))",
 "me.vertices[0].co.x+=.01",
])
def test_stale_binding_refuses_weights_before_copy_and_state_change(tmp_path,mutation):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
path=Path(root)/'bind'/'bind_state.json'
'''+mutation+r'''
before=path.read_bytes()
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
print('RESULT '+json.dumps({'result':w,'unchanged':before==path.read_bytes(),'fit_exists':copy.name+'_fit' in bpy.data.objects}))
''')
    assert not d['result']['ok'] and d['unchanged'] and not d['fit_exists'],d


def test_undeclared_flexible_surface_collision_stays_strict(tmp_path):
    # Source ID5 lies inside both rigid faces without coinciding with their
    # vertices; only the declared original vertex0 contact is released.
    setup=SETUP.replace('(-1,0,0)', '(2,0,0)').replace('(0,-1,0)', '(0,2,0)').replace('(0,0,1)', '(.2,.2,0)', 1)
    r=run(tmp_path,setup+r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
 rows=np.zeros((len(idx),len(names)));rows[:,names.index('spine_01')]=1;return rows
FB._restrict_part=region
before=(Path(root)/'bind'/'bind_state.json').read_bytes()
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
print('RESULT '+json.dumps({'plan':p,'weights':w,'unchanged':before==(Path(root)/'bind'/'bind_state.json').read_bytes(),'fit_exists':copy.name+'_fit' in bpy.data.objects}))
''')
    assert r.rc==0,r.out[-3000:]
    d=r.results[-1]
    assert d['plan']['ok'],d
    assert not d['weights']['ok'] and d['unchanged'] and not d['fit_exists'],d
    assert 'two rigid' in d['weights']['error'],d


def test_undeclared_rigid_pair_still_refuses_apply(tmp_path):
    d=execute(tmp_path,r'''
contact['contacts']=contact['contacts'][1:]
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
 rows=np.zeros((len(idx),len(names)));rows[:,names.index('spine_01')]=1;return rows
FB._restrict_part=region
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
a=api.fit_bind('apply',piece=copy.name,armature=arm.name,out_dir='bind')
print('RESULT '+json.dumps({'plan':p,'weights':w,'apply':a}))
''')
    assert d['plan']['ok'] and d['plan']['seam_opens'],d
    assert d['weights']['ok'] and not d['apply']['ok'],d


def test_complete_partition_releases_only_one_contact_and_keeps_other_rigid_anchor(tmp_path):
    setup=SETUP.replace('(0,5,6)', '(0,3,6)')
    r=run(tmp_path,setup+r'''
contact['contacts'][1]['retained_source_vertices']=[3]
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
 rows=np.zeros((len(idx),len(names)));rows[:,names.index('spine_01')]=1;return rows
FB._restrict_part=region
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
d={'plan':p,'weights':w}
if w.get('ok'):
 fit=bpy.data.objects[w['object']];names,W=FB.WT._read(fit,{'spine_01','upperarm_l'})
 d.update(names=names,released_row=W[6].tolist(),retained_row=W[7].tolist())
print('RESULT '+json.dumps(d))
''')
    assert r.rc==0,r.out[-3000:]
    d=r.results[-1]
    assert d['plan']['ok'] and d['weights']['ok'],d
    assert d['released_row'][d['names'].index('spine_01')]==1,d
    assert d['retained_row'][d['names'].index('upperarm_l')]==1,d
    assert d['plan']['articulated_contacts']['released_contact_pairs']==2,d
    assert d['plan']['articulated_contacts']['retained_contact_pairs']==1,d


@pytest.mark.parametrize('stage',['return','apply'])
def test_stale_contact_source_refuses_later_stages_before_publication(tmp_path,stage):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece=copy.name,armature=arm.name,roles=roles,bind_overrides=overrides,out_dir='bind')
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
 rows=np.zeros((len(idx),len(names)));rows[:,names.index('spine_01')]=1;return rows
FB._restrict_part=region
w=api.fit_bind('weights',piece=copy.name,armature=arm.name,body_object=copy.name,out_dir='bind')
path=Path(root)/'bind'/'bind_state.json';before=path.read_bytes();objects=set(bpy.data.objects.keys())
me.vertices[0].co.x+=.01
r=api.fit_bind('''+repr(stage)+r''',piece=copy.name,armature=arm.name,out_dir='bind')
print('RESULT '+json.dumps({'result':r,'unchanged':before==path.read_bytes(),'objects_unchanged':objects==set(bpy.data.objects.keys()),'bound':bool(bpy.data.objects[w['object']].get('lw_bound',False))}))
''')
    assert not d['result']['ok'] and d['unchanged'] and d['objects_unchanged'] and not d['bound'],d
