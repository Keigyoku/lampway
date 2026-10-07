# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon08B5 uses target curl, including the thumb, on an already-curled authored hand."""
import numpy as np
import pytest
from mixar.modules.lampway_tools import canon_geom as G
from mixar.modules.lampway_tools.pipeline import finger_pose


def hand():
    ref={'hand_r':{'parent':None,'pos':(0,0,0),'rot':(0,0,0,1)}}
    axis=(-1,0,0)
    for f,x in zip(('index','middle','ring','pinky','thumb'),(-.03,0,.015,.03,-.05)):
        p=np.array([x,.1,0.]); parent='hand_r'
        for n,angle in ((1,20),(2,50),(3,50)):
            bone=f'{f}_{n:02d}_r'
            ref[bone]={'parent':parent,'pos':tuple(p),'rot':G.qaxis(axis,angle)}
            p+=np.array(G.qrot(G.qaxis(axis,angle),(0,.04,0)))
            parent=bone
    return ref


def test_target_adapter_subtracts_existing_curl_and_includes_thumb():
    ref=hand()
    entries=finger_pose.entries(ref,'r',1)
    assert len(entries)==15
    by={e['bone']:e for e in entries}
    for f in ('index','middle','ring','pinky','thumb'):
        assert by[f'{f}_01_r']['deg']==pytest.approx(60)
        assert by[f'{f}_02_r']['deg']==pytest.approx(65)
        assert by[f'{f}_03_r']['deg']==pytest.approx(60)
    assert {e['target_deg'] for e in entries}=={80,95,60}
    half=finger_pose.entries(ref,'r',.5)
    assert half[0]['deg']==pytest.approx(20) # TO40, not ADD40.


@pytest.mark.parametrize('fraction',[-.1,1.1,True,float('nan')])
def test_bad_fraction_refuses(fraction):
    with pytest.raises(ValueError,match='fraction'):
        finger_pose.entries(hand(),'r',fraction)


def test_coupled_targets_run_inside_the_actual_pose_search_and_receipt():
    from mixar.modules.lampway_tools.pipeline import pose_solve as PS
    ref=hand()
    # Real triangles far from the authored hand: no intersection; cost selects
    # the smallest necessary delta rather than merely the smallest fraction.
    V=np.array([[3,3,3],[4,3,3],[3,4,3]],float);T=np.array([[0,1,2]])
    samples=[(np.asarray(t['pos'])+[0,0,.01],b) for b,t in ref.items() if b!='hand_r']
    dofs=[{'bone':'hand_r','axis':[-1,0,0],'range':[0,0],'step':1,
           'expect':{'joint':'middle_01_r','along':'-up','min_cm':0}}]
    result=PS.solve(ref,{'up':(0,0,1),'forward':(0,-1,0)},samples,(V,T),dofs,
                    curl_side='r',curl_fractions=[1])
    assert len(result['entries'])==15
    assert any(e['bone']=='thumb_01_r' for e in result['entries'])
    assert len([r for r in result['sweeps'] if r['stage']=='finger_curl_to'])==1
    assert next(e['deg'] for e in result['entries'] if e['bone']=='index_01_r')==pytest.approx(60)
    assert result['pose_cost_deg']>0


@pytest.mark.parametrize('kind,expect',[('waist',{'joint':'spine_01','along':'forward','min_cm':0}),('boots',{'joint':'ball_r','along':'up','min_cm':0}),('gauntlets',{'joint':'middle_01_r','along':'up','min_cm':0})])
def test_complete_bounded_candidate_tables_drive_shared_geometry_sweeps(kind,expect):
    from mixar.modules.lampway_tools.pipeline import decision_tables as DT,pose_solve as PS
    ref=hand()
    for bone,pos,parent in [('pelvis',(0,0,1),None),('spine_01',(0,0,1.2),'pelvis'),('head',(0,0,1.6),'spine_01'),
                            ('thigh_l',(.1,0,1),'pelvis'),('calf_l',(.1,0,.5),'thigh_l'),('foot_l',(.1,0,.1),'calf_l'),('ball_l',(.1,-.15,.1),'foot_l'),
                            ('thigh_r',(-.1,0,1),'pelvis'),('calf_r',(-.1,0,.5),'thigh_r'),('foot_r',(-.1,0,.1),'calf_r'),('ball_r',(-.1,-.15,.1),'foot_r'),
                            ('lowerarm_r',(0,-.2,0),None)]:
        ref[bone]={'pos':pos,'parent':parent,'rot':(0,0,0,1)}
    ref['hand_r']['parent']='lowerarm_r'
    # Reorder parents first, as scene adapter always does.
    ordered={}
    while len(ordered)<len(ref):
        for bone,t in ref.items():
            if t['parent'] is None or t['parent'] in ordered: ordered[bone]=t
    table=DT.candidate(kind,expect,.002,side='r')
    samples=[(np.array(t['pos'])+[.005,0,0],b) for b,t in ordered.items()]
    V=np.array([[3,3,3],[4,3,3],[3,4,3]],float);T=np.array([[0,1,2]])
    result=PS.solve(ordered,{'up':(0,0,1),'forward':(0,-1,0)},samples,(V,T),table['dofs'],table['chain'],table['regions'],
                    curl_side=table.get('curl_side',''),curl_fractions=table.get('curl_fractions'))
    assert result['sign_check']['moved_cm']>0
    assert len(result['sweeps'])<=100
    assert 'not a canon table' in table['status']
    assert len(table['chain'])=={'waist':5,'boots':2,'gauntlets':1}[kind]


def test_curl_targets_reach_the_native_api_and_replay_without_scene_writes(tmp_path):
    import json
    from blender_run import run_script
    from test_wave3_weights import PRE
    ref=hand()
    script=PRE+'\nimport numpy as np\nref=json.loads('+repr(json.dumps(ref))+')\n'+r'''
bpy.ops.object.armature_add();arm=bpy.context.object;arm.name='curl_rig'
bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones[0])
for name,t in ref.items():
    b=arm.data.edit_bones.new(name);b.head=t['pos']
    children=[v['pos'] for n,v in ref.items() if v['parent']==name]
    b.tail=children[0] if children else np.array(t['pos'])+[0,.03,0]
    if t['parent']:b.parent=arm.data.edit_bones[t['parent']]
bpy.ops.object.mode_set(mode='OBJECT')
me=bpy.data.meshes.new('skin');points=[];faces=[];bones=[]
for name,t in ref.items():
    start=len(points);points.extend([np.array(t['pos'])+v for v in ((.001,0,.001),(.002,0,.001),(.001,.001,.001))]);faces.append((start,start+1,start+2));bones.extend([name]*3)
me.from_pydata(points,[],faces);me.update();skin=bpy.data.objects.new('skin',me);bpy.context.scene.collection.objects.link(skin)
for name in ref:
    g=skin.vertex_groups.new(name=name);g.add([i for i,n in enumerate(bones) if n==name],1,'REPLACE')
mod=skin.modifiers.new('rig','ARMATURE');mod.object=arm
me=bpy.data.meshes.new('piece');me.from_pydata([(3,3,3),(4,3,3),(3,4,3)],[],[(0,1,2)]);me.update()
piece=bpy.data.objects.new('piece',me);bpy.context.scene.collection.objects.link(piece)
before=[list(b.matrix_basis) for b in arm.pose.bones]
r=api.fit_pose('gauntlets',piece='piece',body='skin',armature='curl_rig',dofs=[{'bone':'hand_r','axis':[-1,0,0],'range':[0,0],'step':1,'expect':{'joint':'middle_01_r','along':'-up','min_cm':0}}],curl_side='r',curl_fractions=[1])
res({'result':r,'unchanged':before==[list(b.matrix_basis) for b in arm.pose.bones]})
'''
    result=run_script(script,env={'LW_KEEP_ROOT':str(tmp_path)},timeout=300)
    assert result.rc==0,result.out[-3000:]
    got=result.results[-1];r=got['result']
    assert r.get('ok'),r
    assert len(r['entries'])==15 and got['unchanged']
    assert any(e['bone']=='thumb_01_r' and e['target_deg']==80 for e in r['entries'])
    (tmp_path/'native-curl-proof.json').write_text(json.dumps(got,indent=2)+'\n')
