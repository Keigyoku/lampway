# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the pinned Blender writer's authored binds, without EditBone inference.

export_fbx_bin writes XYZ Model TRS (1970ff), global BindPose matrices (726ff),
then the same bone globals in Cluster.TransformLink (1857ff). fbx_utils writes
matrices column-major (253ff). Only the default recipes' declared -Z/Y basis
is supported: pinned axis_conversion maps Blender Y to -Z and Z to Y;
RIGHT_HAND_AXES[('Y','-Z')] writes Up(1,+1), Front(2,+1), Coord(0,+1).
This is a restricted writer-layout reader, not a general FBX evaluator.
No matrices are projected, no bones reconstructed, and no scene is touched.
"""
import math
import numpy as np

from . import core as RC
from ..canon_geom.rest_frames import FLOAT32_FRAME_BUDGET

WRITER_SHA256 = '72852e99d9720398d82d6c8c1169ca1a67ed4a5ef6c20f9ca62739570886b4d4'
BASIS = np.array([[1.,0.,0.,0.],[0.,0.,1.,0.],[0.,-1.,0.,0.],[0.,0.,0.,1.]])
AXES = {'UpAxis':1,'UpAxisSign':1,'FrontAxis':2,'FrontAxisSign':1,'CoordAxis':0,'CoordAxisSign':1}


class BindRefused(ValueError):
    """An unsupported or contradictory authored bind refuses publication."""


def _one(node, ident):
    found=[e for e in node.elems if e.id==ident]
    if len(found)!=1:raise BindRefused('Missing or ambiguous FBX bind element')
    return found[0]


def _props(node):
    groups=[e for e in node.elems if e.id==b'Properties70']
    if len(groups)>1:raise BindRefused('Ambiguous FBX properties')
    out={}
    for p in groups[0].elems if groups else ():
        if p.id!=b'P' or len(p.props)<5:raise BindRefused('Malformed FBX property')
        key=p.props[0].decode('utf8')
        if key in out:raise BindRefused('Duplicate FBX property')
        out[key]=p.props[4:]
    return out


def _vector(props,key,default):
    value=np.asarray(props.get(key,default),float)
    if value.shape!=(3,) or not np.isfinite(value).all():raise BindRefused('Invalid FBX transform vector')
    return value


def _rigid(matrix):
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.array_equal(matrix[3],[0.,0.,0.,1.]):
        raise BindRefused('Invalid or nonaffine FBX bind matrix')
    scales=np.linalg.norm(matrix[:3,:3],axis=0)
    if np.any(scales<=0) or np.max(np.abs(scales-1))>RC.BARS['scale']:
        raise BindRefused('Nonunit authored FBX bind scale')
    frame=matrix[:3,:3]/scales
    # Admission only; no SVD/polar replacement enters a returned matrix.
    if np.linalg.det(frame)<=0 or np.max(np.abs(np.linalg.svd(frame,compute_uv=False)-1))>FLOAT32_FRAME_BUDGET:
        raise BindRefused('Nonrigid or reflected authored FBX bind')
    return scales,frame


def _array_matrix(node,ident):
    elem=_one(node,ident)
    if len(elem.props)!=1:raise BindRefused('Malformed FBX matrix array')
    values=np.asarray(elem.props[0],float)
    if values.shape!=(16,):raise BindRefused('Malformed FBX matrix array')
    matrix=values.reshape(4,4).T.copy()
    _rigid(matrix)
    return matrix


def _quaternion(frame):
    """Standard matrix-to-quaternion conversion; never replaces the input frame."""
    trace=float(np.trace(frame));q=np.zeros(4)
    if trace>0:
        s=2*math.sqrt(trace+1);q[3]=s/4
        q[:3]=[(frame[2,1]-frame[1,2])/s,(frame[0,2]-frame[2,0])/s,(frame[1,0]-frame[0,1])/s]
    else:
        i=int(np.argmax(np.diag(frame)));j=(i+1)%3;k=(i+2)%3
        s=2*math.sqrt(1+frame[i,i]-frame[j,j]-frame[k,k]);q[i]=s/4
        q[j]=(frame[i,j]+frame[j,i])/s;q[k]=(frame[i,k]+frame[k,i])/s
        q[3]=(frame[k,j]-frame[j,k])/s
    return q


def _delta(a,b):
    sa,ra=_rigid(a);sb,rb=_rigid(b)
    return {'position_cm':float(np.linalg.norm(a[:3,3]-b[:3,3])),
            'rotation_deg':RC._qangle_deg(_quaternion(ra),_quaternion(rb)),
            'scale':float(np.max(np.abs(sa-sb)))}


def _equal(a,b):
    row=_delta(a,b)
    if any(row[k]>RC.BARS[k] for k in RC.BARS):raise BindRefused('Contradictory authored FBX node, pose or cluster bind')
    return row


def authored_bind(raw,exporter):
    """Return bone globals in Blender world axes and cm, plus consistency metrics.

    The caller verifies the actual writer source hash before calling. Every bone
    must have independently consistent node TRS, BindPose and connected cluster
    matrices. Unsupported layouts refuse rather than fall back to inferred tails.
    """
    if (exporter.get('axis_forward'),exporter.get('axis_up'))!=('-Z','Y'):
        raise BindRefused('Unsupported declared writer axis basis')
    if exporter.get('bake_space_transform',False):raise BindRefused('Baked-space writer layouts are unsupported')
    creator=_one(raw,b'Creator').props
    if len(creator)!=1 or not isinstance(creator[0],bytes) or not creator[0].startswith(b'Blender (stable FBX IO)'):
        raise BindRefused('Unsupported FBX creator')
    if _one(_one(raw,b'FBXHeaderExtension'),b'FBXVersion').props!=[7400]:
        raise BindRefused('Unsupported pinned-writer FBX version')
    glob=_props(_one(raw,b'GlobalSettings'))
    if any(glob.get(k)!=[v] for k,v in AXES.items()) or glob.get('UnitScaleFactor')!=[1.]:
        raise BindRefused('FBX axes or units contradict the declared centimetre recipe')
    models, poses, clusters = {}, [], {}
    objects=_one(raw,b'Objects')
    for e in objects.elems:
        if e.id==b'Model':
            if len(e.props)!=3 or e.props[0] in models:raise BindRefused('Duplicate or malformed FBX Model')
            models[e.props[0]]=e
        elif e.id==b'Pose':
            if len(e.props)<3 or e.props[2]!=b'BindPose':raise BindRefused('Unsupported FBX pose layout')
            nodes=[n for n in e.elems if n.id==b'PoseNode']
            if _one(e,b'NbPoseNodes').props!=[len(nodes)]:raise BindRefused('FBX pose count differs')
            poses.extend(nodes)
        elif e.id==b'Deformer' and len(e.props)>=3 and e.props[2]==b'Cluster':
            if e.props[0] in clusters:raise BindRefused('Duplicate FBX cluster')
            clusters[e.props[0]]=e
    names={ident:e.props[1].split(b'\x00')[0].decode('utf8') for ident,e in models.items()}
    bones={ident for ident,e in models.items() if e.props[2]==b'LimbNode'}
    if not bones or len({names[i] for i in bones})!=len(bones):raise BindRefused('Empty or ambiguous FBX bone roster')
    parents, links = {}, {}
    for e in _one(raw,b'Connections').elems:
        if e.id!=b'C' or len(e.props)<3 or e.props[0]!=b'OO':continue
        child,parent=e.props[1:3]
        if child in models and (parent in models or parent==0):
            if child in parents:raise BindRefused('Ambiguous FBX Model ancestry')
            parents[child]=parent
        elif child in bones and parent in clusters:
            if parent in links:raise BindRefused('Ambiguous FBX cluster bone connection')
            links[parent]=child
    world={}
    def evaluate(ident,visiting):
        if ident in world:return world[ident]
        if ident in visiting:raise BindRefused('Cyclic FBX Model ancestry')
        if ident not in parents:raise BindRefused('Missing FBX Model ancestry')
        e=models[ident]
        if e.props[2] not in (b'Null',b'LimbNode'):raise BindRefused('Unsupported bone ancestor type')
        p=_props(e)
        for key in ('PreRotation','PostRotation','RotationOffset','RotationPivot','ScalingOffset','ScalingPivot','GeometricTranslation','GeometricRotation'):
            if np.any(_vector(p,key,[0.,0.,0.])):raise BindRefused('Unsupported FBX pre/post/pivot/geometric transform')
        if not np.array_equal(_vector(p,'GeometricScaling',[1.,1.,1.]),[1.,1.,1.]):raise BindRefused('Unsupported FBX geometric scaling')
        if p.get('RotationOrder',[0])!=[0] or p.get('InheritType',[1])!=[1]:raise BindRefused('Unsupported FBX rotation or inheritance mode')
        rot=_vector(p,'Lcl Rotation',[0.,0.,0.])
        local=np.eye(4);local[:3,:3]=RC.rot('z',rot[2])@RC.rot('y',rot[1])@RC.rot('x',rot[0])@np.diag(_vector(p,'Lcl Scaling',[1.,1.,1.]))
        local[:3,3]=_vector(p,'Lcl Translation',[0.,0.,0.]);_rigid(local)
        parent=parents[ident]
        world[ident]=(evaluate(parent,visiting|{ident}) if parent else np.eye(4))@local
        _rigid(world[ident]);return world[ident]
    for ident in bones:evaluate(ident,set())
    pose_count={i:0 for i in bones};cluster_count={i:0 for i in bones};metrics=[]
    for e in poses:
        ident=_one(e,b'Node').props
        if len(ident)!=1 or ident[0] not in models:raise BindRefused('Invalid FBX pose node identity')
        if ident[0] in bones:
            metrics.append(_equal(world[ident[0]],_array_matrix(e,b'Matrix')));pose_count[ident[0]]+=1
    for ident,e in clusters.items():
        if ident not in links:raise BindRefused('Unconnected FBX skin cluster')
        bone=links[ident]
        metrics.append(_equal(world[bone],_array_matrix(e,b'TransformLink')));cluster_count[bone]+=1
    if any(not pose_count[i] or not cluster_count[i] for i in bones):raise BindRefused('Missing independent FBX bone pose or skin cluster bind')
    return {'matrices':{names[i]:BASIS.T@world[i] for i in bones},
            'parents':{names[i]:names.get(parents[i]) if parents[i] in bones else None for i in bones},
            'diagnostics':{'verification':'authored_bind_verification','bones_compared':len(bones),
                           'pose_rows':sum(pose_count.values()),'cluster_rows':sum(cluster_count.values()),
                           'bars':dict(RC.BARS),'worst_consistency':{k:max(r[k] for r in metrics) for k in RC.BARS},
                           'writer_sha256':WRITER_SHA256,'basis':'pinned_writer_-Z_Y_inverse'}}
