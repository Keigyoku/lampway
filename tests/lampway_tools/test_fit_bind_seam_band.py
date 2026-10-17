# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon07 B.6 through public fit_bind; exact source C03, isolated region fields."""
import sys
from pathlib import Path
import pytest
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'tests/lampway_tools'))
from isolated_binary import run
from canon_support import LOAD_OBJ
from test_wave3_weights import PRE
SETUP=PRE[PRE.index('def armature'):PRE.index('def tube')]+LOAD_OBJ+r'''
from mixar.modules.lampway_tools.features import fit_bind as FB
from mixar.modules.lampway_tools.features.workflows import mesh_hash
from mixar.modules.lampway_tools import canon_geom as G
from pathlib import Path
api.settings_set(project_root=root)
gold=Path('__C03_GOLD__')
piece=load_obj(str(gold/'piece.obj'),'piece')
part_vertices={}
for line in (gold/'piece.obj').read_text().splitlines():
    fields=line.split()
    if fields and fields[0]=='g': group=fields[1];part_vertices.setdefault(group,set())
    elif fields and fields[0]=='f':part_vertices[group].update(int(q.split('/')[0])-1 for q in fields[1:])
for name,ids in part_vertices.items():
    piece.vertex_groups.new(name=name).add(sorted(ids),1.0,'REPLACE')
rig=json.loads((gold/'rig.json').read_text())
arm=armature(bones=tuple((n,b['head'],b['tail'],b['parent']) for n,b in rig['bones'].items()))
pairs=rig['seam_pairs_source_ledger']
band={'parts':['lower','upper'],'bones':['spine_01','spine_03'], 'generated_same_shell':True,
      'source_sha256':mesh_hash(piece),'source_seam_pairs':pairs,'cut_point':[0,0,1.2],'axis':[0,0,1]}
overrides={'lower':{'bones':['spine_01']},'upper':{'bones':['spine_03']},'_seam_bands':[band]}
# Isolate the missing composition: exact compatible native-sidecar fields are
# piecewise single-bone here. No transfer/bar behavior is altered in production.
original_body_regions,original_restrict=FB._body_regions,FB._restrict_part
FB._body_regions=lambda *args:(None,None,None,None)
def region(ob,idx,plan,part,parents,names,*args):
    rows=np.zeros((len(idx),len(names)));rows[:,names.index(plan['bones'][0])]=1;return rows
FB._restrict_part=region
'''

def execute(tmp_path,body):
    setup=SETUP.replace('__C03_GOLD__',str(REPO/'docs/canon/goldens/C03_seam_tube'))
    r=run(tmp_path,setup+body)
    assert r.rc==0,r.out[-4000:]
    return r.results[-1]

def test_public_c03_position_band_closes_seam_and_keeps_exact_return(tmp_path):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece='piece',armature='rig',roles={'lower':'cloth','upper':'cloth'},bind_overrides=overrides,out_dir='bind')
w=api.fit_bind('weights',piece='piece',armature='rig',out_dir='bind',body_object='piece')
fit=bpy.data.objects[w['object']]
names,rows=FB.WT._read(fit,{'spine_01','spine_03'})
P=np.array([v.co[:] for v in fit.data.vertices]);head=np.array([0,0,1.2])
c,s=np.cos(np.radians(40)),np.sin(np.radians(40));M=np.eye(4);M[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]];M[:3,3]=head-M[:3,:3]@head
mats=np.array([np.eye(4) if n=='spine_01' else M for n in names])
posed=G.lbs(P,rows,mats)
returned=G.lbs_inverse(posed,rows,mats)
expected=G.band_weights(P,[0,0,1.2],[0,0,1],0.05)
expected=expected[:,[band['bones'].index(n) for n in names]]
print('RESULT '+json.dumps({'plan':p,'weights':w,'seam_gap':float(np.linalg.norm(posed[np.array(pairs)[:,0]]-posed[np.array(pairs)[:,1]],axis=1).max()),'rows_identical':all(np.array_equal(rows[a],rows[b]) for a,b in pairs),'return_error':float(np.abs(returned-P).max()),'analytic_max_error':float(np.abs(rows-expected).max())}))
''')
    assert d['rows_identical'],d
    assert d['seam_gap']<=1e-9,d
    assert d['return_error']<=1e-6,d
    assert d['analytic_max_error']<=1e-7,d
    assert d['weights']['seam_bands']['widths_m']==[0.05],d

@pytest.mark.parametrize('mutation',['rigid','authority','pairs','cut','width','bool_width','axis','overlap','bone','profile','endpoint_profile','reversed_axis'])
def test_band_recipe_refuses_missing_or_invalid_authority_before_plan_publication(tmp_path,mutation):
    edits={'rigid':"roles['lower']='metal'",'authority':"band['generated_same_shell']=False",'pairs':"band['source_seam_pairs']=pairs[:-1]",'cut':"band['cut_point']=[0,0,1.1]",'width':"band['width_m']=float('nan')",'bool_width':"band['width_m']=True",'axis':"band['axis']=[0,0,0]",'overlap':"overrides['_seam_bands'].append(dict(band))",'bone':"band['bones'][0]='absent'",'profile':"band['bones'][0]='spine_03'",'endpoint_profile':"overrides['lower']['bones']=['spine_01','spine_03']",'reversed_axis':"band['axis']=[0,0,-1]"}
    d=execute(tmp_path,"roles={'lower':'cloth','upper':'cloth'}\n"+edits[mutation]+r'''
p=api.fit_bind('plan',piece='piece',armature='rig',roles=roles,bind_overrides=overrides,out_dir='bind')
print('RESULT '+json.dumps({'result':p,'published':(Path(root)/'bind'/'bind_state.json').exists()}))
''')
    assert not d['result'].get('ok'),d
    assert not d['published'],d

def test_changed_source_refuses_before_copy_or_state_mutation(tmp_path):
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece='piece',armature='rig',roles={'lower':'cloth','upper':'cloth'},bind_overrides=overrides,out_dir='bind')
before=(Path(root)/'bind'/'bind_state.json').read_bytes();piece.data.vertices[0].co.x+=0.01
w=api.fit_bind('weights',piece='piece',armature='rig',out_dir='bind',body_object='piece')
print('RESULT '+json.dumps({'result':w,'unchanged':before==(Path(root)/'bind'/'bind_state.json').read_bytes(),'fit_exists':'piece_fit' in bpy.data.objects}))
''')
    assert not d['result'].get('ok'),d
    assert d['unchanged'] and not d['fit_exists'],d

@pytest.mark.parametrize('mutation',['world','membership','recipe'])
def test_changed_frame_membership_or_recipe_refuses_before_copy(tmp_path,mutation):
    edits={'world':"piece.location.x+=0.1; bpy.context.view_layer.update()",'membership':"piece.vertex_groups['lower'].remove([0])",'recipe':"state=json.loads(path.read_text());state['plan']['seam_bands'][0]['width_m']=0.1;path.write_text(json.dumps(state))"}
    d=execute(tmp_path,r'''
p=api.fit_bind('plan',piece='piece',armature='rig',roles={'lower':'cloth','upper':'cloth'},bind_overrides=overrides,out_dir='bind')
path=Path(root)/'bind'/'bind_state.json'
'''+edits[mutation]+r'''
before=path.read_bytes()
w=api.fit_bind('weights',piece='piece',armature='rig',out_dir='bind',body_object='piece')
print('RESULT '+json.dumps({'result':w,'unchanged':before==path.read_bytes(),'fit_exists':'piece_fit' in bpy.data.objects}))
''')
    assert not d['result'].get('ok'),d
    assert d['unchanged'] and not d['fit_exists'],d

def test_unpatched_native_region_transfer_composes_band_and_preserves_source(tmp_path):
    d=execute(tmp_path,r'''
FB._body_regions,FB._restrict_part=original_body_regions,original_restrict
source=mesh_hash(piece)
body=FB.C.duplicate(piece,'_body')
for g in list(body.vertex_groups): body.vertex_groups.remove(g)
for name,ids in [('spine_01',list(range(192))),('spine_03',list(range(192,len(body.data.vertices))))]:
    body.vertex_groups.new(name=name).add(ids,1.0,'REPLACE')
mod=body.modifiers.new('Armature','ARMATURE');mod.object=arm
p=api.fit_bind('plan',piece='piece',armature='rig',roles={'lower':'cloth','upper':'cloth'},bind_overrides=overrides,out_dir='bind')
w=api.fit_bind('weights',piece='piece',armature='rig',out_dir='bind',body_object=body.name)
if not w.get('ok'): print('RESULT '+json.dumps({'weights':w}))
else:
    fit=bpy.data.objects[w['object']];names,rows=FB.WT._read(fit,{'spine_01','spine_03'})
    print('RESULT '+json.dumps({'weights':w,'identical':all(np.array_equal(rows[a],rows[b]) for a,b in pairs),'all_weighted':bool(np.all(rows.sum(axis=1)>0)),'source_preserved':source==mesh_hash(piece)}))
''')
    assert d['weights'].get('ok'),d
    assert d['identical'] and d['all_weighted'] and d['source_preserved'],d


def test_existing_two_rigid_anchor_refusal_survives_band_integration(tmp_path):
    d=execute(tmp_path,r'''
V=[v.co[:] for v in piece.data.vertices];F=[list(p.vertices) for p in piece.data.polygons]
V.append(V[pairs[0][0]])
mesh=bpy.data.meshes.new('contact');mesh.from_pydata(V,[],F);mesh.update();piece.data=mesh
for g in list(piece.vertex_groups):piece.vertex_groups.remove(g)
for name,ids in [('lower',list(range(192))),('upper',list(range(192,len(V)-1))),('soft',[len(V)-1])]:
    piece.vertex_groups.new(name=name).add(ids,1.0,'REPLACE')
p=api.fit_bind('plan',piece='piece',armature='rig',roles={'lower':'metal','upper':'metal','soft':'cloth'},bind_overrides={'lower':{'bones':['spine_01']},'upper':{'bones':['spine_03']},'soft':{'bones':['spine_01']}},out_dir='bind')
before=(Path(root)/'bind'/'bind_state.json').read_bytes()
w=api.fit_bind('weights',piece='piece',armature='rig',out_dir='bind',body_object='piece')
print('RESULT '+json.dumps({'weights':w,'unchanged':before==(Path(root)/'bind'/'bind_state.json').read_bytes(),'fit_exists':'piece_fit' in bpy.data.objects}))
''')
    assert not d['weights'].get('ok') and 'conflicting rigid anchors' in d['weights'].get('error',''),d
    assert d['unchanged'] and not d['fit_exists'],d
