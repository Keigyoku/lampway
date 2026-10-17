# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon08G residual blockers keep source frames, identities and material classes."""
import json
import numpy as np
import pytest

from canon_support import LOAD_OBJ, goldens
from test_canon_item7_pose import TOOL, _c07, FRAME
from mixar.modules.lampway_tools.pipeline import pose_solve as PS
from issue2_isolated import run

IDENTITY={'scale':1.,'translation':[0.,0.,0.],'turn_deg':0.}


def setup(goldens):
    return ('import math,os,numpy as np\nroot=os.environ["LAMPWAY_PROJECT_ROOT"]\nos.makedirs(root,exist_ok=True)\napi.settings_set(project_root=root)\n'
            +LOAD_OBJ+f'GOLD={str(goldens)!r}\n'+TOOL.split('from mixar.modules.lampway_tools import posing as PO')[0])


def test_typed_scene_pose_requires_placement_before_any_output_or_mutation(tmp_path,goldens):
    rows=run(tmp_path,setup(goldens)+r'''
coords=[tuple(v.co) for v in sleeve.data.vertices]
pose=[list(b.matrix_basis) for b in ob.pose.bones]
result=api.fit_pose(kind='chest',piece='sleeve',body='body',armature='rig',dofs=[dof],regions={'arm_l':{'bones':['upperarm_l'],'threshold_m':.01}},out='missing.json',apply=True)
assert not result['ok'] and 'placement' in result['error'],result
assert not os.path.exists(root+'/missing.json')
assert coords==[tuple(v.co) for v in sleeve.data.vertices]
assert pose==[list(b.matrix_basis) for b in ob.pose.bones]
print('RESULT',json.dumps(result))
''')
    assert not rows[-1]['ok']


def test_residual_blockers_backmap_hits_rather_than_body_samples(goldens):
    ref,samples,piece,dof,regions=_c07(goldens)
    # Lock the actual golden A-pose; residuals are present and classed by hit face.
    dof=dict(dof,range=[0,0])
    result=PS.solve(ref,FRAME,samples,piece,[dof],regions=regions,
                    placement_meta={'scale':2.,'translation':[1.,2.,3.],'turn_deg':90.},
                    classes=['metal']*len(piece[1]))
    row=result['blocking']['l']
    assert row['points']==result['posed']['arm_l']['over']>0
    assert row['by_class']=={'metal':row['points']}
    # Reconstruct independently from actual golden rays/triangles.
    head=np.array(ref['upperarm_l']['pos']);end=np.array(ref['lowerarm_l']['pos']);segment=end-head
    P=np.array([p for p,b in samples]);O=head+np.clip((P-head)@segment/(segment@segment),0,1)[:,None]*segment
    D=P-O;L=np.linalg.norm(D,axis=1);D/=L[:,None]
    t=PS.numpy_hits(O,D,L,*piece);mask=np.isfinite(t)&(L-t>regions['arm_l']['threshold_m'])
    H=O[mask]+t[mask,None]*D[mask]
    R=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    Q=((H-[1,2,3])/2)@R
    assert np.allclose(row['bbox_piece_frame'],[Q.min(0),Q.max(0)],atol=1e-12)
    assert not np.allclose(row['bbox_piece_frame'],[((P[mask]-[1,2,3])/2@R).min(0),((P[mask]-[1,2,3])/2@R).max(0)])
    assert len(result['body_sha256'])==len(result['placed_sha256'])==64


@pytest.mark.parametrize('bad_meta', [{}, {'scale':0,'translation':[0,0,0],'turn_deg':0},
    {'scale':1,'translation':[0,0,float('nan')],'turn_deg':0}])
def test_invalid_backmap_refuses_before_rays(goldens,bad_meta):
    ref,samples,piece,dof,regions=_c07(goldens)
    rays=[]
    with pytest.raises(PS.PoseError,match='placement'):
        PS.solve(ref,FRAME,samples,piece,[dof],regions=regions,placement_meta=bad_meta,
                 hits=lambda *args,**kwargs:rays.append(args) or PS.numpy_hits(*args,**kwargs))
    assert not rays


def test_class_labels_are_triangle_aligned_and_reversed_sign_still_refuses(goldens):
    ref,samples,piece,dof,regions=_c07(goldens)
    with pytest.raises(PS.PoseError,match='classes'):
        PS.solve(ref,FRAME,samples,piece,[dof],regions=regions,placement_meta=IDENTITY,classes=['metal'])
    with pytest.raises(PS.PoseError,match='sign check'):
        PS.solve(ref,FRAME,samples,piece,[dict(dof,axis=[0,-1,0])],regions=regions,placement_meta=IDENTITY)


def test_native_hashes_class_files_all_kinds_and_stale_maps(tmp_path,goldens):
    rows=run(tmp_path,setup(goldens)+r'''
from mixar.modules.lampway_tools import posing as PO
from mixar.modules.lampway_tools.features import rig as RIG
from mixar.modules.lampway_tools.pipeline import pose_receipt as PR
bound=PO.stamp_placement(sleeve,{'scale':2.,'translation':[1.,2.,3.],'turn_deg':90.})
V,T=RIG._body_mesh(sleeve)
assert bound['placed_sha256']==PR.geometry_hash(V,T)
json.dump(bound,open(root+'/placement.json','w'))
json.dump(['metal']*len(T),open(root+'/classes.json','w'))
kwargs=dict(piece='sleeve',body='body',armature='rig',dofs=[dict(dof,range=[0,0])],regions={'arm_l':{'bones':['upperarm_l'],'threshold_m':.01}},placement_meta='placement.json',classes='classes.json')
results=[]
for kind in ('chest','helmet','waist','boots','gauntlets'):
    result=api.fit_pose(kind=kind,out=kind+'.json',**kwargs)
    assert result['ok'],result
    assert result['placed_sha256']==bound['placed_sha256'] and len(result['body_sha256'])==64,result
    assert result['blocking']['l']['points']==result['posed']['arm_l']['over']==37,result
    assert result['blocking']['l']['by_class']=={'metal':37},result
    disk=json.load(open(root+'/'+kind+'.json'))
    assert disk['blocking']==result['blocking'] and disk['body_sha256']==result['body_sha256']
    results.append(result)
# Full-source hash includes native weights, not merely sampled skin positions.
body.vertex_groups[0].add([0],.5,'REPLACE')
weighted=api.fit_pose(kind='chest',**kwargs)
assert weighted['ok'] and weighted['body_sha256']!=results[0]['body_sha256'],weighted
coords=[tuple(v.co) for v in sleeve.data.vertices];pose=[list(b.matrix_basis) for b in ob.pose.bones]
for bad in ({'scale':1,'translation':[0,0,0],'turn_deg':0},dict(bound,scale=-1),dict(bound,translation=[0,0,float('nan')])):
    failure=api.fit_pose(kind='chest',**dict(kwargs,placement_meta=bad,out='bad.json',apply=True))
    assert not failure['ok'] and 'placement' in failure['error'],failure
    assert not os.path.exists(root+'/bad.json')
    assert coords==[tuple(v.co) for v in sleeve.data.vertices] and pose==[list(b.matrix_basis) for b in ob.pose.bones]
sleeve.data.vertices[0].co.x+=.01;sleeve.data.update();bpy.context.view_layer.update()
stale=api.fit_pose(kind='chest',**dict(kwargs,out='stale.json',apply=True))
assert not stale['ok'] and 'stale' in stale['error'] and not os.path.exists(root+'/stale.json'),stale
print('RESULT',json.dumps({'kinds':[r['kind'] for r in results],'first':results[0],'stale':stale}))
''')
    assert len(rows[-1]['kinds'])==5


def test_legacy_chest_normalization_backmap_matches_existing_recipe():
    from mixar.modules.lampway_tools.pipeline import pose_receipt as PR
    V=np.array([[0,0,0],[1,0,0],[0,1,0]],float);T=np.array([[0,1,2]])
    meta={'scale':3.,'y_shift':4.,'tz':5.,'turn_deg':-90.,'norm_lo':[-2.,-3.,-4.],'norm_hi':[2.,3.,6.]}
    maps=PR.prepare(meta,V,T)
    H=np.array([[.5,4.3,5.6]])
    result=PR.blocking(H,np.array([[0,0,1.]]),np.array([0.]),np.array([0]),np.array([True]),['head'],maps,None)
    turned=H.copy();turned[:,1]-=4;turned[:,2]-=5
    turned=turned/3*10+[0,0,-4]
    R=np.array([[0,1,0],[-1,0,0],[0,0,1.]])
    assert np.allclose(result['center']['bbox_piece_frame'],np.repeat(turned@R,2,axis=0))


def test_pair_hit_uses_its_triangle_group_map_even_across_body_sides():
    from mixar.modules.lampway_tools.pipeline import pose_receipt as PR
    V=np.array([[1.,0,0],[2,0,0],[1,1,0],[-1,0,0],[-2,0,0],[-1,1,0]])
    T=np.array([[0,1,2],[3,4,5]])
    meta={'turn_deg':0.,'side_transforms':{
        'l':{'vertex_ids':[0,1,2],'scale':2.,'rotation':np.eye(3).tolist(),'translation':[1.,2.,3.]},
        'r':{'vertex_ids':[3,4,5],'scale':3.,'rotation':np.eye(3).tolist(),'translation':[-1.,-2.,-3.]}}}
    maps=PR.prepare(meta,V,T)
    result=PR.blocking(np.array([[1.5,2.3,3.6],[-1.3,-2.6,-3.9]]),np.zeros((2,3)),np.zeros(2),np.array([0,1]),np.array([True,True]),['hand_r','hand_l'],maps,np.array(['metal','cloth']))
    assert result['l']['by_class']=={'metal':1} and result['r']['by_class']=={'cloth':1}
    assert np.allclose(result['l']['bbox_piece_frame'],[[.25,.15,.3]]*2)
    assert np.allclose(result['r']['bbox_piece_frame'],[[-.1,-.2,-.3]]*2)
    with pytest.raises(ValueError,match='crossing'):
        PR.prepare(meta,V,np.array([[0,1,3]]))
    meta['side_transforms']['l']['rotation'][0][0]=-1
    with pytest.raises(ValueError,match='proper rotation'):PR.prepare(meta,V,T)


@pytest.mark.parametrize('mode',['common','per_side'])
def test_public_placement_producer_stamp_reaches_native_pose(tmp_path,goldens,mode):
    from test_canon_pair_scale import pair
    body_path,piece_path=pair(tmp_path)
    with np.load(body_path) as b: body_data={k:b[k].tolist() for k in ('V','T','J','names')}
    with np.load(piece_path) as p: piece_data={k:p[k].tolist() for k in ('V','T')}
    script=setup(goldens)+f'pair_data={piece_data!r}\nbody_data={body_data!r}\nmode={mode!r}\n'+r'''
from mixar.modules.lampway_tools.features import rig as RIG
from mixar.modules.lampway_tools.pipeline import pose_receipt as PR
np.savez(root+'/source.npz',V=pair_data['V'],T=pair_data['T'])
np.savez(root+'/placement_body.npz',**body_data)
mesh=bpy.data.meshes.new('pair');mesh.from_pydata(pair_data['V'],[],pair_data['T']);mesh.update()
placed=bpy.data.objects.new('pair',mesh);bpy.context.scene.collection.objects.link(placed)
placement=api.fit_place('gauntlets',piece='source.npz',body='placement_body.npz',object='pair',pair_scale_group=mode)
assert placement['ok'],placement
bound=json.loads(placed['lw_fit_placement_meta'])
V,T=RIG._body_mesh(placed)
assert bound['placed_sha256']==PR.geometry_hash(V,T)
# The stamp binds rounded native scene coordinates, rather than the float64 NPZ.
with np.load(placement['placed']) as output:
    assert np.max(np.abs(V-output['V']))<1e-6
    assert np.max(np.abs(V-output['V']))>0
result=api.fit_pose('gauntlets',piece='pair',body='body',armature='rig',dofs=[dict(dof,range=[0,0])],regions={'arm_l':{'bones':['upperarm_l'],'threshold_m':.01}},out='producer-pose.json')
assert result['ok'] and result['placed_sha256']==bound['placed_sha256'],result
assert result['sign_check']['moved_cm']>2
before=[tuple(v.co) for v in placed.data.vertices]
pose=[list(b.matrix_basis) for b in ob.pose.bones]
# Invalid class input and escaped JSON/NPY paths fail before pose or output writes.
for overrides in ({'classes':['metal']},{'classes':[[1]]*len(T)}, {'classes':'../outside.npy'}, {'placement_meta':'../outside.json'}, {'out':'../outside.json'}):
    failure=api.fit_pose('gauntlets',piece='pair',body='body',armature='rig',dofs=[dof],regions={'arm_l':{'bones':['upperarm_l'],'threshold_m':.01}},apply=True,**overrides)
    assert not failure['ok'],failure
    assert before==[tuple(v.co) for v in placed.data.vertices] and pose==[list(b.matrix_basis) for b in ob.pose.bones]
np.save(root+'/classes.npy',np.array(['cloth']*len(T)))
classified=api.fit_pose('gauntlets',piece='pair',body='body',armature='rig',dofs=[dict(dof,range=[0,0])],regions={'arm_l':{'bones':['upperarm_l'],'threshold_m':.01}},classes='classes.npy')
assert classified['ok'],classified
# Even an inside-root symlink cannot expose an outside metadata or labels file.
outside=os.path.join(os.path.dirname(root),'outside.json');json.dump(bound,open(outside,'w'))
os.symlink(outside,root+'/escaped.json')
refused=api.fit_pose('gauntlets',piece='pair',body='body',armature='rig',dofs=[dof],placement_meta='escaped.json')
assert not refused['ok'] and 'project' in refused['error'],refused
print('RESULT',json.dumps({'mode':mode,'stamp_hash':bound['placed_sha256'],'pose_hash':result['placed_sha256'],'blocking':result['blocking']}))
'''
    rows=run(tmp_path,script)
    assert rows[-1]['stamp_hash']==rows[-1]['pose_hash']


@pytest.mark.parametrize('kind',['waist','boots','gauntlets'])
def test_omitted_scene_dofs_execute_the_default_admission_path(tmp_path,goldens,kind):
    rows=run(tmp_path,setup(goldens)+f'kind={kind!r}\n'+r'''
result=api.fit_pose(kind,piece='sleeve',body='body',armature='rig',out='default.json')
assert not result['ok'] and 'placement' in result['error'],result
assert not os.path.exists(root+'/default.json')
print('RESULT',json.dumps(result))
''')
    assert not rows[-1]['ok']
