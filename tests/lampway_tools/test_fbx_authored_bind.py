# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored writer binds cross-check all rows; malformed redundant evidence refuses."""
import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as N

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]
package=ModuleType('_fbx_bind_test_tools');package.__path__=[str(ROOT/'src/scripts/mixar/modules/lampway_tools')]
sys.modules[package.__name__]=package
B=importlib.import_module(package.__name__+'.rig_tools.fbx_bind')


def e(ident,props=(),elems=()):return N(id=ident,props=list(props),elems=list(elems))
def prop(key,values):return e(b'P',[key.encode(),b'',b'',b'',*values])
def properties(values):return e(b'Properties70',elems=[prop(k,v) for k,v in values.items()])


def fixture(count=3):
    models=[e(b'Model',[1,b'Armature\x00\x01Model',b'Null'],[properties({'Lcl Rotation':[-90.,0.,0.],'InheritType':[1]})])]
    world={1:B.BASIS.copy()};pose=[];clusters=[];edges=[e(b'C',[b'OO',1,0])]
    for i in range(count):
        ident=i+2;parent=1 if i==0 else ident-1
        p={'Lcl Translation':[.3,.6,.7],'Lcl Rotation':[10.,20.,30.],'InheritType':[1]}
        models.append(e(b'Model',[ident,('b'+str(i)).encode()+b'\x00\x01Model',b'LimbNode'],[properties(p)]))
        local=np.eye(4);local[:3,:3]=B.RC.rot('z',30)@B.RC.rot('y',20)@B.RC.rot('x',10);local[:3,3]=p['Lcl Translation']
        world[ident]=world[parent]@local
        values=world[ident].T.reshape(-1).tolist()
        pose.append(e(b'PoseNode',elems=[e(b'Node',[ident]),e(b'Matrix',[values])]))
        cid=1000+i;clusters.append(e(b'Deformer',[cid,b'cluster',b'Cluster'],[e(b'TransformLink',[values])]))
        edges.extend([e(b'C',[b'OO',ident,parent]),e(b'C',[b'OO',ident,cid])])
    raw=e(b'',elems=[e(b'Creator',[b'Blender (stable FBX IO) - fixture']),e(b'FBXHeaderExtension',elems=[e(b'FBXVersion',[7400])]),
        e(b'GlobalSettings',elems=[properties({**{k:[v] for k,v in B.AXES.items()},'UnitScaleFactor':[1.]})]),
        e(b'Objects',elems=[*models,e(b'Pose',[90,b'pose',b'BindPose'],[e(b'NbPoseNodes',[count]),*pose]),*clusters]),
        e(b'Connections',elems=edges)])
    return raw,{'axis_forward':'-Z','axis_up':'Y'}


def test_all_342_authored_rows_are_consistent_without_scene_or_bpy():
    raw,recipe=fixture(342);got=B.authored_bind(raw,recipe)
    assert got['diagnostics']['bones_compared']==342
    assert got['diagnostics']['pose_rows']==342 and got['diagnostics']['cluster_rows']==342
    assert got['diagnostics']['bars']==B.RC.BARS
    assert got['parents']['b0'] is None and got['parents']['b341']=='b340'
    assert got['diagnostics']['worst_consistency']['rotation_deg']<B.RC.BARS['rotation_deg']
    assert np.allclose(got['matrices']['b0'][:3,3],[.3,.6,.7])


@pytest.mark.parametrize('corruption',['node','pose','cluster','axes','zero_matrix','reflection','shear','pre','post','pivot','geometric','order','inherit','missing_pose','missing_cluster','cycle','parent','duplicate_name','creator','version','units','missing_parent','nonfinite'])
def test_unknown_or_contradictory_layout_refuses(corruption):
    raw,recipe=fixture();objects=B._one(raw,b'Objects');models=[x for x in objects.elems if x.id==b'Model']
    pose=next(x for x in objects.elems if x.id==b'Pose');cluster=next(x for x in objects.elems if x.id==b'Deformer')
    matrix=B._one(pose.elems[1],b'Matrix')
    if corruption=='node':models[1].elems[0].elems[1].props[-1]+=1.
    elif corruption in ('pose','zero_matrix','reflection','shear','nonfinite'):
        if corruption=='pose':matrix.props[0][12]+=1.
        elif corruption=='zero_matrix':matrix.props[0]=[0.]*16
        elif corruption=='reflection':matrix.props[0][0]*=-1
        elif corruption=='shear':matrix.props[0][4]+=.1
        else:matrix.props[0][0]=float('nan')
    elif corruption=='cluster':cluster.elems[0].props[0][12]+=1.
    elif corruption=='axes':B._one(raw,b'GlobalSettings').elems[0].elems[0].props[-1]=2
    elif corruption in ('pre','post','pivot','geometric','order','inherit'):
        key={'pre':'PreRotation','post':'PostRotation','pivot':'RotationPivot','geometric':'GeometricTranslation','order':'RotationOrder','inherit':'InheritType'}[corruption]
        vals=[1.,0.,0.] if corruption in ('pre','post','pivot','geometric') else [2]
        ps=models[1].elems[0];ps.elems=[p for p in ps.elems if p.props[0]!=key.encode()];ps.elems.append(prop(key,vals))
    elif corruption=='missing_pose':objects.elems.remove(pose)
    elif corruption=='missing_cluster':objects.elems.remove(cluster)
    elif corruption in ('cycle','parent','missing_parent'):
        edges=B._one(raw,b'Connections').elems
        if corruption=='cycle':edges[0].props[2]=4
        elif corruption=='parent':edges.append(e(b'C',[b'OO',2,0]))
        else:edges.remove(edges[0])
    elif corruption=='duplicate_name':models[2].props[1]=models[1].props[1]
    elif corruption=='creator':B._one(raw,b'Creator').props=[b'unsupported']
    elif corruption=='version':B._one(B._one(raw,b'FBXHeaderExtension'),b'FBXVersion').props=[7700]
    elif corruption=='units':B._one(raw,b'GlobalSettings').elems[0].elems[-1].props[-1]=100.
    with pytest.raises(B.BindRefused):B.authored_bind(raw,recipe)


def test_real_writer_long_coincident_bone_authored_bind_survives_tail_reconstruction():
    from blender_run import run_script
    from test_rig_export_space import PRE
    run=run_script(PRE+r'''
from mathutils import Vector
from mixar.modules.lampway_tools.features import rig_export as RE
from mixar.modules.lampway_tools.rig_tools import fbx_bind as B
from mixar.modules.lampway_tools.rig_tools import core as RC
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
bone=arm.data.edit_bones['leaf'];bone.head=(.23,.63,1.53);bone.tail=bone.head+Vector((.3,.6,.7)).normalized()*.1;bone.roll=1.872
helper=arm.data.edit_bones.new('coincident_helper');helper.head=bone.head;helper.tail=bone.head+Vector((.4,.3,.7)).normalized()*.1;helper.parent=bone;helper.roll=.4
bpy.ops.object.mode_set(mode='OBJECT');bpy.context.view_layer.update()
source=RE._table(arm);source_sha=digest(snapshot(arm,mesh,original))
path=Path(tempfile.gettempdir())/'long_bone.fbx'
with SPACE.centimetre_copies(arm,[mesh],None,recipe) as cp:
    for ob in bpy.context.view_layer.objects:ob.select_set(ob is cp['armature'] or ob in cp['meshes'])
    bpy.context.view_layer.objects.active=cp['armature']
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,bake_anim=False,**cp['exporter'])
raw,version=parse_fbx.parse(str(path));verified=B.authored_bind(raw,recipe)
independent,parents,ref_name,ref_sha,ref_import=RE._reference(str(path),arm,'ue_axes',str(path.parent),recipe)
assert ref_import is None and ref_sha==hashlib.sha256(path.read_bytes()).hexdigest()
assert parents==verified['parents']
def table(matrices):
    out={}
    for name,array in matrices.items():
        loc,q,scale=Matrix(array.tolist()).decompose()
        out[name]={'translation':list(loc),'rotation':[q.x,q.y,q.z,q.w],'scale':list(scale)}
    return out
authored=RC.readback_rows(source,table(verified['matrices']))
assert authored['over_tolerance']==[],authored
assert RC.readback_rows(source,independent)['over_tolerance']==[]
ids=canon_io.snapshot_ids()
try:
    bpy.ops.import_scene.fbx(filepath=str(path),automatic_bone_orientation=False,primary_bone_axis='Y',secondary_bone_axis='X',global_scale=1.)
    imported=[ob for ob in bpy.data.objects if ob not in ids['objects']]
    ra=next(ob for ob in imported if ob.type=='ARMATURE');rm=next(ob for ob in imported if ob.type=='MESH')
    units=SPACE.readback_representation(ra,imported,1.)
    rna=RC.readback_rows(source,RE._table(ra,representation=units))
    error=next(row for row in rna['rows'] if row['bone']=='leaf')
    assert .01<error['rotation_deg']<1 and ra.data.bones['leaf'].length<.02
    assert max(min((p-v).length for p in world_vertices(rm)) for v in world_vertices(mesh))<1e-6
    skin_before=evaluated_vertices(rm);weights_before=snapshot(ra,rm,original)['weights']
    B.authored_bind(raw,recipe)
    assert evaluated_vertices(rm)==skin_before and snapshot(ra,rm,original)['weights']==weights_before
    assert verified['diagnostics']['bones_compared']==len(source)
finally:canon_io.remove_new_ids(ids)
assert digest(snapshot(arm,mesh,original))==source_sha
print('RESULT '+json.dumps({'authored':authored['worst_rotation_deg'],'display_reconstruction_error':error['rotation_deg'],'source_unchanged':True}))
''')
    assert run.rc==0,run.out
    assert run.results[0]['authored']<.01


def test_diagonal_near_bar_rotation_uses_shortest_quaternion_angle():
    raw,recipe=fixture();pose=next(e for e in B._one(raw,b'Objects').elems if e.id==b'Pose')
    elem=B._one(pose.elems[1],b'Matrix');matrix=np.array(elem.props[0]).reshape(4,4).T
    axis=np.ones(3)/np.sqrt(3);cross=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
    angle=np.radians(.0105);rotation=np.eye(3)+np.sin(angle)*cross+(1-np.cos(angle))*(cross@cross)
    changed=matrix.copy();changed[:3,:3]=matrix[:3,:3]@rotation
    measured=B._delta(matrix,changed)
    assert .01<measured['rotation_deg']<.011
    elem.props[0]=changed.T.reshape(-1).tolist()
    with pytest.raises(B.BindRefused):B.authored_bind(raw,recipe)
