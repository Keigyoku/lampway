# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Public fit-bind consumes verified native corrective fan-outs at the fit pose."""
from blender_run import run_script
from test_native_complete_topology import PRE, BUILD
import pytest


def test_unstamped_native_fit_bind_plan_weights_return_preserve_source():
    r = run_script(PRE + BUILD + r'''
piece=skinned(arm,'native_plate')
piece.vertex_groups.clear()
g=piece.vertex_groups.new(name='plate');g.add(list(range(len(piece.data.vertices))),1,'REPLACE')
original=[list(v.co) for v in piece.data.vertices]
arm.pose.bones['upperarm_l'].rotation_mode='XYZ'
arm.pose.bones['upperarm_l'].rotation_euler.z=.7
bpy.context.view_layer.update()
out={}
out['plan']=api.fit_bind('plan',piece=piece.name,armature=arm.name,roles={'plate':'metal'},
    bind_overrides={'plate':{'bones':['upperarm_l'],'reason':'explicit fixture binding'}},out_dir='bind')
out['weights']=api.fit_bind('weights',piece=piece.name,armature=arm.name,body_object=skinned(arm,'body').name,out_dir='bind')
out['return']=api.fit_bind('return',piece=piece.name,armature=arm.name,out_dir='bind')
out['apply']=api.fit_bind('apply',piece=piece.name,armature=arm.name,out_dir='bind')
out['source_unchanged']=original==[list(v.co) for v in piece.data.vertices]
out['rest_unchanged']=before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
out['unstamped']='lw_canon' not in arm
res(out)
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    got = r.results[-1]
    for stage in ('plan', 'weights', 'return', 'apply'):
        assert got[stage]['ok'], got[stage]
    assert got['source_unchanged'] and got['rest_unchanged'] and got['unstamped']
    assert got['return']['per_metal_part']['plate']['max_mm'] < .5


def test_native_bind_segments_follow_current_pose_and_authored_driver():
    r = run_script(PRE + BUILD + r'''
from mixar.modules.lampway_tools.features import weights as WT
arm.pose.bones['upperarm_l'].rotation_mode='XYZ';arm.pose.bones['upperarm_l'].rotation_euler.z=.7
bpy.context.view_layer.update()
segments=WT.bone_segments(arm,native_raw=True,posed=True)
name='thumb_03_half_l'
from mixar.modules.lampway_tools.features.normalize_rigged import canonical_helper_ends
rest=canonical_helper_ends(arm,native_raw=True)[name]
expected=arm.matrix_world @ arm.pose.bones[name].matrix @ arm.data.bones[name].matrix_local.inverted() @ arm.matrix_world.inverted() @ Vector(rest)
res({'end_error':float(np.linalg.norm(segments[name][1]-expected)),
     'joint_error':float(np.linalg.norm(segments['upperarm_l'][1]-(arm.matrix_world @ arm.pose.bones['lowerarm_l'].head))),
     'pose_displacement':float(np.linalg.norm(segments[name][1]-rest))})
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    got = r.results[-1]
    assert got['end_error'] < 1e-8 and got['joint_error'] < 1e-8
    assert got['pose_displacement'] > .01


@pytest.mark.parametrize('bad', ['unknown', 'reparented', 'missing'])
def test_raw_native_bind_refuses_unverified_topology_without_plan(bad):
    r = run_script(PRE + BUILD + 'BAD=' + repr(bad) + r'''
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
if BAD=='unknown':
    b=arm.data.edit_bones.new('unknown_driver');b.head=(0,0,0);b.tail=(0,0,.1);b.parent=arm.data.edit_bones['root']
elif BAD=='reparented':arm.data.edit_bones['upperarm_out_l'].parent=arm.data.edit_bones['upperarm_l']
else:arm.data.edit_bones.remove(arm.data.edit_bones['pinky_03_in_l'])
bpy.ops.object.mode_set(mode='OBJECT')
piece=skinned(arm,'plate');piece.vertex_groups.clear();g=piece.vertex_groups.new(name='plate');g.add(list(range(len(piece.data.vertices))),1,'REPLACE')
result=api.fit_bind('plan',piece=piece.name,armature=arm.name,roles={'plate':'metal'},out_dir='bind')
res({'result':result,'plan_exists':(__import__('pathlib').Path(root)/'bind/bind_plan.json').exists()})
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    got = r.results[-1]
    assert not got['result']['ok'] and not got['plan_exists']
    assert 'native topology' in got['result']['error']


def test_root_named_continuation_requires_actual_descendant():
    r = run_script(PRE + r'''
from mixar.modules.lampway_tools.canon_geom.bones import chain_ends, CONTINUATION
heads={'root':(0,0,0),'pelvis':(0,0,1),'unknown_l':(1,0,0),'unknown_r':(-1,0,0)}
parents={'root':None,'pelvis':None,'unknown_l':'root','unknown_r':'root'}
try:chain_ends(heads,parents,main_child=CONTINUATION);result={'refused':False}
except ValueError as error:result={'refused':True,'error':str(error)}
res(result)
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    got = r.results[-1]
    assert got['refused'] and "'root'" in got['error'] and 'no named continuation' in got['error']


def test_native_plan_never_auto_selects_authored_corrective_drivers():
    r = run_script(PRE + BUILD + r'''
from mixar.modules.lampway_tools.canon_geom import native_topology as NT
from mixar.modules.lampway_tools.features import normalize_rigged as NR
piece=skinned(arm,'cloth');piece.vertex_groups.clear()
piece.scale=(.0001,.0001,.0001)
piece.location=Vector(NR.canonical_helper_ends(arm,native_raw=True)['upperarm_correctiveRoot_l'])
g=piece.vertex_groups.new(name='cloth');g.add(list(range(len(piece.data.vertices))),1,'REPLACE')
bpy.context.view_layer.update()
result=api.fit_bind('plan',piece=piece.name,armature=arm.name,roles={'cloth':'cloth'},out_dir='bind')
res({'result':result,'drivers':sorted(set(result.get('parts',{}).get('cloth',{}).get('bones',[]))&NT.AUXILIARY)})
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    got = r.results[-1]
    assert got['result']['ok'], got['result']
    assert not got['drivers'], got['drivers']
