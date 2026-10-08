# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon08G: validated canon09 inverse maps and bounded residual hit summaries."""
import hashlib
import json
import math
import numpy as np


def geometry_hash(vertices,triangles):
    digest=hashlib.sha256()
    for data,dtype in ((vertices,'<f8'),(triangles,'<i8')):
        array=np.asarray(data,dtype=dtype)
        digest.update(json.dumps(array.shape).encode('ascii'))
        digest.update(array.tobytes())
    return digest.hexdigest()


def source_hash(ref,samples):
    return hashlib.sha256(json.dumps({'ref':ref,'samples':samples},sort_keys=True,
                                    separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _number(value,name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('placement '+name+' must be finite')
    return float(value)


def _vector(value,name):
    if not isinstance(value,(list,tuple,np.ndarray)) or any(isinstance(v,(bool,np.bool_)) or not isinstance(v,(int,float,np.integer,np.floating)) for v in value):
        raise ValueError('placement '+name+' must be a finite numeric vector')
    try: result=np.asarray(value,float)
    except (TypeError,ValueError): raise ValueError('placement '+name+' must be a finite vector') from None
    if result.shape!=(3,) or not np.isfinite(result).all():
        raise ValueError('placement '+name+' must be a finite three-vector')
    return result


def prepare(meta,V,T):
    """Admit actual producer formats, retaining a map for each original triangle."""
    if not isinstance(meta,dict) or not meta:
        raise ValueError('placement metadata is required to map blockers back to the source piece; run lampway_fit_place')
    if 'placed_sha256' in meta and meta['placed_sha256']!=geometry_hash(V,T):
        raise ValueError('placement metadata is stale for this placed mesh; run lampway_fit_place again')
    turn=_number(meta.get('turn_deg'),'turn_deg');angle=math.radians(turn)
    R=np.array([[math.cos(angle),-math.sin(angle),0],[math.sin(angle),math.cos(angle),0],[0,0,1]])
    groups={};owners=np.full(len(T),'',dtype=object)
    if 'side_transforms' in meta:
        side_transforms=meta['side_transforms']
        if not isinstance(side_transforms,dict) or not side_transforms or set(side_transforms)-{'l','r'}:
            raise ValueError('placement side_transforms must name l and/or r')
        assigned=np.zeros(len(V),bool)
        for side,tr in side_transforms.items():
            if not isinstance(tr,dict):raise ValueError('placement side transform must be an object')
            raw_ids=tr.get('vertex_ids')
            if not isinstance(raw_ids,list) or not raw_ids or any(isinstance(i,bool) or not isinstance(i,int) for i in raw_ids):
                raise ValueError('placement vertex_ids must be nonempty integer identities')
            ids=np.asarray(raw_ids,int)
            if (ids<0).any() or (ids>=len(V)).any() or len(np.unique(ids))!=len(ids) or assigned[ids].any():
                raise ValueError('placement vertex_ids are invalid or overlap')
            assigned[ids]=True
            mask=np.zeros(len(V),bool);mask[ids]=True
            faces=mask[T].all(1);owners[faces]=side
            raw_rot=tr.get('rotation')
            if not isinstance(raw_rot,(list,tuple,np.ndarray)) or any(not isinstance(row,(list,tuple,np.ndarray)) for row in raw_rot):
                raise ValueError('placement rotation must be a numeric matrix')
            for row in raw_rot:_vector(row,'rotation row')
            rot=np.asarray(raw_rot,float)
            if rot.shape!=(3,3) or not np.isfinite(rot).all() or not np.allclose(rot.T@rot,np.eye(3),atol=1e-6,rtol=0) or np.linalg.det(rot)<=0:
                raise ValueError('placement rotation must be a proper rotation')
            scale=_number(tr.get('scale'),'scale')
            if scale<=0:raise ValueError('placement scale must be positive')
            groups[side]={'scale':scale,'translation':_vector(tr.get('translation'),'translation'),'rotation':rot@R,'offset':np.zeros(3)}
        if not assigned.all() or (owners=='').any():
            raise ValueError('placement maps leave vertices unassigned or triangles crossing side groups')
    else:
        scale=_number(meta.get('scale'),'scale')
        if scale<=0:raise ValueError('placement scale must be positive')
        if 'translation' in meta:
            translation=_vector(meta['translation'],'translation');offset=np.zeros(3)
        else: # Original chest producer: normalised height plus y_shift and tz.
            lo=_vector(meta.get('norm_lo'),'norm_lo');hi=_vector(meta.get('norm_hi'),'norm_hi')
            if not (hi>lo).all():raise ValueError('placement normalisation bounds must increase')
            translation=np.array([_number(meta.get('x_shift',0),'x_shift'),_number(meta.get('y_shift'),'y_shift'),_number(meta.get('tz'),'tz')])
            scale/=hi[2]-lo[2]
            offset=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])@R
        groups['center']={'scale':scale,'translation':translation,'rotation':R,'offset':offset}
        owners[:]='center'
    return groups,owners


def labels(classes,T):
    if classes is None:return None
    if not isinstance(classes,(list,tuple,np.ndarray)) or np.ndim(classes)!=1 or len(classes)!=len(T) or any(not isinstance(s,str) or not s for s in classes):
        raise ValueError('classes must contain one nonempty string label per placed triangle')
    return np.asarray(classes,dtype=str)


def blocking(origins,directions,distances,face_ids,mask,bones,maps,classes):
    groups,owners=maps;records={}
    for index in np.flatnonzero(mask):
        face=int(face_ids[index])
        if face<0 or face>=len(owners):raise ValueError('blocking hit has no valid placed triangle identity')
        group=owners[face]
        side=group if group!='center' else (bones[index][-1] if bones[index].endswith(('_l','_r')) else 'center')
        transform=groups[group]
        H=origins[index]+distances[index]*directions[index]
        Q=((H-transform['translation'])/transform['scale'])@transform['rotation']+transform['offset']
        row=records.setdefault(side,{'points':0,'by_class':{},'bbox_piece_frame':[Q.copy(),Q.copy()]})
        row['points']+=1
        row['bbox_piece_frame'][0]=np.minimum(row['bbox_piece_frame'][0],Q)
        row['bbox_piece_frame'][1]=np.maximum(row['bbox_piece_frame'][1],Q)
        if classes is not None:
            label=str(classes[face]);row['by_class'][label]=row['by_class'].get(label,0)+1
    for row in records.values():row['bbox_piece_frame']=[p.tolist() for p in row['bbox_piece_frame']]
    return records
