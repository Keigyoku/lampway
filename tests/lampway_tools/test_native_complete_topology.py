# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Complete measured342-edge topology, synthetic coordinates, native consumers."""
import json
import hashlib
import pytest
from pathlib import Path
from blender_run import run_script
from test_canon_normalize_rigged import PRE, RIG

PARENTS = json.loads((Path(__file__).parent / "fixtures/metahuman342-topology.json").read_text())["parents"]
assert hashlib.sha256(json.dumps(PARENTS,sort_keys=True,separators=(',',':')).encode()).hexdigest() == '78d86865754f78d6d66a917a8274e5c59e3c7511015fccfae39f1b4f1e313ae1'
BUILD = RIG + "NATIVE_PARENTS=" + repr(PARENTS) + r'''
import numpy as np
from mixar.modules.lampway_tools.features import weights as W, opening as OP
P=dict(NATIVE_PARENTS)
J['root']=(0,0,0);J['neck_02']=(0,0,.93)
for side,sign in (('l',1),('r',-1)):
    for i,finger in enumerate(('thumb','index','middle','ring','pinky')):
        for n in (1,2,3):J[f'{finger}_{n:02d}_{side}']=(sign*(.42+.025*n),.015*(i-2),.60)
        if finger!='thumb':J[f'{finger}_metacarpal_{side}']=(sign*.42,.015*(i-2),.60)
    for i,toe in enumerate(('bigtoe','indextoe','middletoe','ringtoe','littletoe')):
        for n in (1,2):J[f'{toe}_{n:02d}_{side}']=(sign*(.05+i*.01),-.07-n*.025,0)
pending=set(P)-set(J)
while pending:
    for n in sorted(pending):
        if P[n] in J:
            h=np.array(J[P[n]]);i=sorted(P).index(n)
            J[n]=tuple(h+np.array([.001*(1+i%3),.002*(1+i%5),.001]));pending.remove(n)
NEXT.update({'root':'pelvis','clavicle_l':'upperarm_l','clavicle_r':'upperarm_r','upperarm_l':'lowerarm_l','upperarm_r':'lowerarm_r','lowerarm_l':'hand_l','lowerarm_r':'hand_r','thigh_l':'calf_l','thigh_r':'calf_r','calf_l':'foot_l','calf_r':'foot_r','foot_l':'ball_l','foot_r':'ball_r','hand_l':'middle_metacarpal_l','hand_r':'middle_metacarpal_r'})
arm=build('complete_native_graph')
# These are authored driver frames, deliberately unrelated to their children.
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
for b in arm.data.edit_bones:
    if '_half_' in b.name or '_correctiveRoot_' in b.name:
        b.tail=b.head+Vector((0,0,.012));b.roll=math.radians(120)
bpy.ops.object.mode_set(mode='OBJECT')
before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
'''


def test_complete342_normalize_weights_and_posed_opening_axis():
    r=run_script(PRE+BUILD+r'''
result=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False)
checks={}
if result.get('ok'):
    doc=json.loads(arm['lw_canon']);rows={b['name']:b for b in doc['body']['bones']}
    segments=W.bone_segments(arm)
    driver_errors=[]
    for name,row in rows.items():
        if row['along_source']=='authored_helper_frame':
            expected=np.array(row['head_m'])+np.array(row['along'])*row['length_m']
            driver_errors.append(float(np.linalg.norm(segments[name][1]-expected)))
    piece=skinned(arm,'weight_probe');plan=api.weight_audit(action='plan',object=piece.name,armature=arm.name)
    arm.pose.bones['upperarm_l'].rotation_mode='XYZ';arm.pose.bones['upperarm_l'].rotation_euler.z=.35
    bpy.context.view_layer.update();head,axis=OP.site_axis(arm.name,'upperarm_l')
    expected=(arm.matrix_world@arm.pose.bones['lowerarm_l'].head)-(arm.matrix_world@arm.pose.bones['upperarm_l'].head)
    checks={'bones':len(rows),'roster':doc['body']['roster'],'driver_count':len(driver_errors),'driver_error':max(driver_errors),'plan':plan,'site_error':(axis-expected.normalized()).length,'frames_unchanged':before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones},'errors':CA.validate(doc)}
res({'result':result,'checks':checks})
''',timeout=300)
    assert r.rc==0,r.out[-3000:]
    got=r.results[-1];assert got['result']['ok'],got['result']
    c=got['checks'];assert c['bones']==342 and c['roster']=={'complete':True,'missing':[]}
    assert c['driver_count']>200 and c['driver_error']<1e-8
    assert c['plan']['ok'] and c['site_error']<1e-6
    assert c['frames_unchanged'] and not c['errors']


@pytest.mark.parametrize('bad', ['unknown', 'reparented'])
def test_whole_topology_unknown_or_moved_driver_refuses_before_normalization(bad):
    r=run_script(PRE+BUILD+'BAD='+repr(bad)+r'''
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
if BAD=='unknown':
    b=arm.data.edit_bones.new('pinky_03_unknown_l');b.head=(.5,0,.6);b.tail=(.5,0,.62);b.parent=arm.data.edit_bones['pinky_03_half_l']
else:arm.data.edit_bones['pinky_03_in_l'].parent=arm.data.edit_bones['ring_03_half_l']
bpy.ops.object.mode_set(mode='OBJECT')
before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
result=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False)
res({'result':result,'stamped':'lw_canon' in arm.keys(),'unchanged':before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}})
''',timeout=300)
    assert r.rc==0,r.out[-2000:]
    got=r.results[-1];assert not got['result']['ok'] and 'native topology refused' in got['result']['error']
    assert not got['stamped'] and got['unchanged']


def test_partial_native_stamp_cannot_publish_full_body_or_export():
    r=run_script(PRE+BUILD+r'''
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones.remove(arm.data.edit_bones['pinky_03_in_l']);bpy.ops.object.mode_set(mode='OBJECT')
result=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False)
doc=json.loads(arm['lw_canon']) if 'lw_canon' in arm.keys() else {}
piece=skinned(arm,'body_probe')
plan=api.weight_audit(action='plan',object=piece.name,armature=arm.name)
body=api.fit_body('build',armature=arm.name,mesh=piece.name,out='body/partial')
export=api.rig_export_ue(armature=arm.name,out='export/partial.fbx')
res({'result':result,'roster':doc.get('body',{}).get('roster'),'reference':doc.get('body',{}).get('reference_skeleton'),'plan':plan,'body':body,'export':export,'files':[str(p) for p in __import__('pathlib').Path(root).rglob('*.fbx')]})
''',timeout=300)
    assert r.rc==0,r.out[-2500:]
    got=r.results[-1];assert got['result']['ok'],got['result']
    assert got['roster']=={'complete':False,'missing':['pinky_03_in_l']} and got['reference']['bones']==342
    assert got['plan']['ok'] and got['plan']['canonical_roster']==got['roster']
    for operation in ('body','export'):
        assert not got[operation]['ok'] and 'full-body reference is incomplete' in got[operation]['error']
    assert not got['files']


def test_changed_helper_rest_frame_and_unstamped_complete_graph_refuse_consumers():
    r=run_script(PRE+BUILD+r'''
result=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False);assert result.get('ok'),result
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones['pinky_03_half_l'].roll+=.2;bpy.ops.object.mode_set(mode='OBJECT')
errors={}
for name,fn in [('weights',lambda:W.bone_segments(arm)),('opening',lambda:OP.site_axis(arm.name,'upperarm_l'))]:
    try:fn();errors[name]='accepted'
    except Exception as e:errors[name]=str(e)
del arm['lw_canon']
try:W.bone_segments(arm);errors['unstamped']='accepted'
except Exception as e:errors['unstamped']=str(e)
res(errors)
''',timeout=300)
    assert r.rc==0,r.out[-2500:]
    got=r.results[-1]
    assert all('rest frames changed' in got[n] for n in ('weights','opening'))
    assert 'no named continuation' in got['unstamped']


def test_complete342_oblique_authored_frames_preserve_rotation_precision():
    """All auxiliary families retain float32 axes without decimal quantization drift."""
    r=run_script(PRE+BUILD+r'''
from mixar.modules.lampway_tools.canon_geom import native_topology as NT
from mixar.modules.lampway_tools.features import rig_tools as RT
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
for i,name in enumerate(sorted(NT.AUXILIARY)):
    b=arm.data.edit_bones[name]
    b.tail=b.head+Vector((math.sin(i+.31),math.cos(i*.71+.17),math.sin(i*.37+.83)))*.013
    b.roll=math.sin(i*.57)*math.pi
bpy.ops.object.mode_set(mode='OBJECT')
before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
raw=RT.read(arm)['frames']
result=api.normalize_rigged(armature=arm.name,profile='metahuman',dry_run=False)
checks={}
if result.get('ok'):
    doc=json.loads(arm['lw_canon']);rows={b['name']:b for b in doc['body']['bones']}
    drift=max(float(np.max(np.abs(np.array(row['frame'])-raw[name]))) for name,row in rows.items())
    rounded=json.loads(json.dumps(doc))
    for row in rounded['body']['bones']:row['frame']=np.round(row['frame'],6).tolist()
    coarse_errors=CA.validate(rounded)
    falsifiers={}
    for kind,matrix in [('shear',[[1,.01,0],[0,1,0],[0,0,1]]),('reflection',[[-1,0,0],[0,1,0],[0,0,1]])]:
        bad=json.loads(json.dumps(doc));bad['body']['bones'][0]['frame']=matrix
        falsifiers[kind]=CA.validate(bad)
    segments=W.bone_segments(arm)
    receipt=json.loads(arm['lw_canon_normalize_receipt'])
    receipt_hash=__import__('hashlib').sha256(json.dumps(receipt,sort_keys=True,indent=1).encode()).hexdigest()
    checks={'drift':drift,'drivers':sum(row['along_source']=='authored_helper_frame' for row in rows.values()),
            'coarse_errors':coarse_errors,'errors':CA.validate(doc),'falsifiers':falsifiers,
            'correction_count':len(receipt['canonical_frame_corrections']),
            'receipt_matches':receipt_hash==doc['receipt_sha256'],
            'segment_count':len(segments),'unchanged':before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}}
res({'result':result,'checks':checks})
''',timeout=300)
    assert r.rc==0,r.out[-3000:]
    got=r.results[-1];assert got['result']['ok'],got['result']
    c=got['checks'];assert c['drivers']==258 and c['segment_count']==342
    # Only serialized rotations change, within the float32 producer budget;
    # every authored Blender matrix and the strict document validator remain.
    from mixar.modules.lampway_tools.canon_geom.rest_frames import FLOAT32_FRAME_BUDGET
    assert c['drift']<FLOAT32_FRAME_BUDGET and c['unchanged'] and not c['errors']
    assert c['correction_count']>0 and c['receipt_matches']
    assert got['result']['canonical_frame_corrections']['count']==c['correction_count']
    assert any('proper rotation' in e for e in c['coarse_errors'])
    assert all(any('proper rotation' in e for e in errors) for errors in c['falsifiers'].values())
