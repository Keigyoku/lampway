# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured AC65 candidates on an owner's disposable scene; no default is selected.

Config supplies project-relative npz/plate paths and existing scene object names.
Pose candidate tables (including first-DOF sign expectations) are explicit inputs.
All receipts and views stay under the configured project root. Nothing is saved
back to the input blend, submitted to a provider, or promoted into canon settings.
"""
import json
import hashlib
from pathlib import Path
import numpy as np
from .. import canon_geom as G


def _path(root, value):
    path=(Path(root)/value).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('measurement paths must stay under the project root')
    return path


def _file_identity(root, path):
    return {'path':str(Path(path).resolve().relative_to(Path(root).resolve())),
            'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def _body_context(root, context):
    """Explicit world-metre geometry and fixed camera bounds; never infer anatomy."""
    import bpy
    if not isinstance(context, dict) or bool(context.get('npz')) == bool(context.get('object')):
        raise ValueError('body_context requires exactly one project npz or current-copy object')
    bounds=np.asarray(context.get('bounds_m'),float)
    if bounds.shape!=(2,3) or not np.isfinite(bounds).all() or not (bounds[1]>bounds[0]).all():
        raise ValueError('body_context bounds_m requires finite increasing world-metre bounds')
    if not context.get('views') or any(v not in ('Front','Left','Back','Right') for v in context['views']):
        raise ValueError('body_context views must explicitly name cardinal views')
    if context.get('npz'):
        path=_path(root,context['npz'])
        with np.load(path,allow_pickle=False) as data: V,T=np.array(data['V'],float),np.array(data['T'],int)
        identity={'npz':str(path.relative_to(Path(root).resolve())),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    else:
        ob=bpy.data.objects.get(context['object'])
        if ob is None or ob.type!='MESH': raise ValueError('requested body_context object is not a current-copy mesh')
        ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
        try:
            me.calc_loop_triangles()
            V=np.array([(ev.matrix_world@v.co)[:] for v in me.vertices]);T=np.array([t.vertices[:] for t in me.loop_triangles],int)
        finally: ev.to_mesh_clear()
        scale=context.get('metres_per_unit')
        if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not np.isfinite(scale) or scale<=0:
            raise ValueError('object body_context requires explicit positive metres_per_unit')
        V*=scale
        identity={'object':ob.name,'evaluated':True,'metres_per_unit':scale}
    if V.ndim!=2 or V.shape[1]!=3 or not len(V) or not np.isfinite(V).all() or T.ndim!=2 or T.shape[1]!=3 or not len(T) or T.min()<0 or T.max()>=len(V):
        raise ValueError('body_context requires finite nonempty world-metre triangle geometry')
    identity['geometry_sha256']=hashlib.sha256(V.astype('<f8').tobytes()+T.astype('<i8').tobytes()).hexdigest()
    return V,T,identity


def _vertex_clearance(P,V,T,limits):
    """All vertices, canonical closed pseudonormal/open winding sign; explicit scope."""
    import math
    if not isinstance(limits,dict) or set(('min_signed_m','max_below_min_vertices'))-limits.keys():
        raise ValueError('clearance_acceptance requires explicit min_signed_m and max_below_min_vertices')
    threshold=limits['min_signed_m'];allowed=limits['max_below_min_vertices']
    if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not math.isfinite(threshold):
        raise ValueError('min_signed_m must be an explicit finite signed distance')
    if isinstance(allowed,bool) or not isinstance(allowed,int) or allowed<0: raise ValueError('max_below_min_vertices must be an explicit nonnegative integer')
    P=np.asarray(P,float)
    if not len(P) or not np.isfinite(P).all():raise ValueError('clearance points must be finite and nonempty')
    raw_boundary=G.boundary_edges(T)
    # Analytical topology only: retain authored V/T for context images and identities.
    T=G.weld_keys(V)[T]
    T=T[(T[:,0]!=T[:,1])&(T[:,1]!=T[:,2])&(T[:,2]!=T[:,0])]
    if not len(T):raise ValueError('body_context has no nondegenerate analytical triangles')
    edges=np.sort(np.concatenate([T[:,[0,1]],T[:,[1,2]],T[:,[2,0]]]),axis=1)
    edges,counts=np.unique(edges,axis=0,return_counts=True)
    if (counts>2).any():raise ValueError('body_context has nonmanifold edges; clearance signs refused')
    boundary=edges[counts==1];band_count=0
    if len(boundary):
        band=limits.get('body_open_band_m')
        if isinstance(band,bool) or not isinstance(band,(int,float)) or not math.isfinite(band) or band<=0:
            raise ValueError('open body_context requires explicit positive body_open_band_m')
        A=V[boundary[:,0]];D=V[boundary[:,1]]-A;den=np.maximum((D*D).sum(1),1e-300)
        for block in np.array_split(P,max(1,int(np.ceil(len(P)/256)))):
            t=np.clip(((block[:,None]-A)*D).sum(2)/den,0,1)
            distance=np.linalg.norm(block[:,None]-(A+t[:,:,None]*D),axis=2).min(1)
            band_count+=int((distance<=band).sum())
        if band_count:
            return {'scope':'all-vertex signed clearance only','pass':None,'status':'REFUSED_OPENING_BAND','opening_band_vertices':band_count,'vertices':len(P),'limits':limits,
                    'raw_boundary_edges':raw_boundary,'boundary_edges':len(boundary),'analytical_weld_m':G.WELD_M,
                    'not_measured':['surface crossings','innermost layer gap','hideable skin']}
    else:
        volume=float(np.einsum('ij,ij->i',V[T[:,0]],np.cross(V[T[:,1]],V[T[:,2]])).sum()/6)
        if volume<=0:raise ValueError('body_context must have outward orientation for signed clearance')
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    tree=BVHTree.FromPolygons(V.tolist(),T.tolist(),all_triangles=True)
    nearest=[tree.find_nearest(Vector(p)) for p in P]
    distances=np.array([r[3] for r in nearest]);locations=np.array([r[0][:] for r in nearest]);triangles=np.array([r[2] for r in nearest])
    if len(boundary):sign=np.where(G.winding_numbers(V,T,P)>.5,-1.,1.)
    else:sign=G.PseudoNormals(V,T).signs(P,locations,triangles)
    signed=distances*sign
    below=int((signed<threshold).sum())
    return {'scope':'all-vertex signed clearance only','pass':below<=allowed,'status':'MEASURED','vertices':len(P),'min_signed_m':float(signed.min()),
            'median_signed_m':float(np.median(signed)),'p90_signed_m':float(np.quantile(signed,.9)),'inside_vertices':int((signed<0).sum()),
            'below_min_vertices':below,'boundary_edges':len(boundary),'raw_boundary_edges':raw_boundary,'analytical_weld_m':G.WELD_M,
            'limits':limits,'not_measured':['surface crossings','innermost layer gap','hideable skin']}


def _capture_context(P,PT,B,BT,context,size,out):
    """Body and candidate in one fixed world frame, no per-subject cropping."""
    import bpy
    from mathutils import Vector
    from .. import canon_io
    from ..features.render import TO_CAMERA
    if not 32<=int(size)<=4096:raise ValueError('image_size is 32..4096')
    bounds=np.asarray(context['bounds_m'],float);center=Vector(bounds.mean(0));extent=float((bounds[1]-bounds[0]).max())
    before=canon_io.snapshot_ids();sc=None
    try:
        sc=bpy.data.scenes.new('lw_decision_context')
        for name,V,T,color in [('body',B,BT,(.1,.3,.9,1)),('candidate',P,PT,(.95,.25,.05,1))]:
            me=bpy.data.meshes.new('lw_decision_'+name);me.from_pydata(V.tolist(),[],T.tolist());me.update()
            ob=bpy.data.objects.new('lw_decision_'+name,me);ob.color=color;sc.collection.objects.link(ob)
        camera=bpy.data.cameras.new('lw_decision_camera');camera.type='ORTHO';camera.ortho_scale=extent
        cam=bpy.data.objects.new('lw_decision_camera',camera);sc.collection.objects.link(cam);sc.camera=cam
        r=sc.render;r.engine='BLENDER_WORKBENCH';r.resolution_x=r.resolution_y=int(size);r.resolution_percentage=100;r.film_transparent=True
        r.image_settings.file_format='PNG';r.image_settings.color_mode='RGBA';sc.display.shading.light='FLAT';sc.display.shading.color_type='OBJECT'
        sc.view_settings.view_transform='Standard';sc.view_settings.look='None'
        images=[];visibility=[]
        for view in context['views']:
            cam.location=center+Vector(TO_CAMERA[view])*(extent*2);cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
            path=Path(out) if len(context['views'])==1 else Path(out).with_name(Path(out).stem+'-'+view+'.png')
            r.filepath=str(path);bpy.ops.render.render(write_still=True,scene=sc.name);images.append(str(path))
            from PIL import Image
            pixels=np.asarray(Image.open(path).convert('RGBA')).astype(int)
            body_pixels=int(((pixels[:,:,2]>pixels[:,:,0]+30)&(pixels[:,:,3]>0)).sum())
            candidate_pixels=int(((pixels[:,:,0]>pixels[:,:,2]+30)&(pixels[:,:,3]>0)).sum())
            visibility.append({'view':view,'body_pixels':body_pixels,'candidate_pixels':candidate_pixels})
        return {'images':images,'camera_bounds_m':context['bounds_m'],'body_and_candidate_visible':all(v['body_pixels']>0 and v['candidate_pixels']>0 for v in visibility),
                'visibility':visibility,'frame':'world metres; fixed across candidates','crop':False,
                'geometry_bounds_m':{'body':[B.min(0).tolist(),B.max(0).tolist()],'candidate':[P.min(0).tolist(),P.max(0).tolist()]}}
    finally:
        if sc is not None:bpy.data.scenes.remove(sc)
        canon_io.remove_new_ids(before)


def measure(config, root):
    import bpy
    from .. import api, canon_io
    from ..features import normalize, opening, render
    from . import fit_place
    api.settings_set(project_root=str(Path(root).resolve()))
    output=[]
    for job in config['jobs']:
        row={'id':job['id'],'action':job['action'],'selection':'none; measurements for owner decision'}
        try:
            action=job['action']; args=job.get('args',{})
            if action=='facing':
                row['result']=normalize.measure_frame(bpy.data.objects[args['object']],args['plate'],root)
            elif action in ('pair','boots'):
                context=job.get('body_context',config.get('body_context'))
                requested=bool(context is not None or job.get('body_relative_views',config.get('body_relative_views',False)))
                limits=job.get('clearance_acceptance',config.get('clearance_acceptance'))
                if requested:
                    CV,CT,context_identity=_body_context(root,context)
                    if limits is None:raise ValueError('body-relative measurement requires explicit clearance_acceptance; no physical defaults selected')
                    if any(k not in args or args[k] is None for k in ('turn','clear_mm','pair_scale_group')):
                        raise ValueError('body-relative measurement requires explicit turn, clear_mm and pair_scale_group')
                modes=('common','per_side') if action=='pair' else (args.get('pair_scale_group','common'),)
                anchors=(args.get('scale_anchor'),) if action=='pair' else ('width','height','foot')
                body=_path(root,args['body']);piece=_path(root,args['piece'])
                row['placement_inputs']={'body':_file_identity(root,body),'piece':_file_identity(root,piece),
                    'args':{k:args.get(k,default) for k,default in (
                        ('kind',None),('turn',0),('clear_mm',15),('sides','both'),
                        ('pair_scale_group',None),('scale_anchor',None))}}
                with np.load(body,allow_pickle=False) as data:
                    b={'V':np.array(data['V']),'T':np.array(data['T'])}
                row['candidates']=[]
                for mode in modes:
                    for anchor in anchors:
                        V,T,meta,report=fit_place.place(args['kind'],body,piece,args.get('turn',0),args.get('clear_mm',15),anchor,args.get('sides','both'),mode)
                        if any(_file_identity(root,path)!=row['placement_inputs'][key]
                               for key,path in (('body',body),('piece',piece))):
                            raise ValueError('placement source changed during measurement; rerun with stable inputs')
                        out=_path(root,f"measurements/{job['id']}/{mode}-{anchor or 'bracer'}.npz")
                        out.parent.mkdir(parents=True,exist_ok=True);np.savez(out,V=V,T=T)
                        candidate={'mode':mode,'anchor':anchor,'meta':meta,'report':report,'placed':str(out.relative_to(Path(root).resolve())),
                                   'placed_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
                        if requested:
                            candidate['vertex_clearance']=_vertex_clearance(V,CV,CT,limits)
                            capture=_capture_context(V,T,CV,CT,context,int(config.get('image_size',384)),out.with_name(out.stem+'-body.png'))
                            capture['images']=[str(Path(p).relative_to(Path(root).resolve())) for p in capture['images']]
                            capture['body_identity']=context_identity
                            candidate['body_relative_capture']=capture
                        # A bounded deterministic sample; signed points near native openings
                        # are not acceptance evidence without the canon15 declared band.
                        count=int(config.get('max_samples',256))
                        if not 1<=count<=4096: raise ValueError('max_samples is 1..4096')
                        ids=np.linspace(0,len(V)-1,min(count,len(V)),dtype=int)
                        distance=G.signed_distance(b['V'],b['T'],V[ids])[0]
                        candidate['sampled_body_distance_m']={'samples':len(ids),'min':float(distance.min()),'median':float(np.median(distance)),
                                                             'p90':float(np.quantile(distance,.9)),'negative':int((distance<0).sum()),
                                                             'limits':'sampled; native-opening band and anatomical region review still required'}
                        before=canon_io.snapshot_ids()
                        try:
                            me=bpy.data.meshes.new('lw_decision_candidate');me.from_pydata(V.tolist(),[],T.tolist());me.update()
                            ob=bpy.data.objects.new('lw_decision_candidate',me);bpy.context.scene.collection.objects.link(ob)
                            candidate['views']=[]
                            for view in ('Front','Left','Back'):
                                image=out.with_name(out.stem+'-'+view+'.png');render.render_view(ob,view,int(config.get('image_size',384)),str(image))
                                candidate['views'].append(str(image.relative_to(Path(root).resolve())))
                        finally: canon_io.remove_new_ids(before)
                        row['candidates'].append(candidate)
                if requested:
                    passes=[c['vertex_clearance']['pass'] for c in row['candidates']]
                    row['acceptance']={'scope':'all-vertex signed clearance only','pass':None if any(p is None for p in passes) else all(passes),
                                       'full_fit_acceptance':None,'not_measured':['surface crossings','innermost layer gap','hideable skin']}
            elif action=='pose':
                args=dict(args)
                proposal=args.pop('candidate',None)
                if proposal:
                    from .decision_tables import candidate
                    table=candidate(args['kind'],proposal['expect'],proposal['threshold_m'],proposal.get('side','l'))
                    row['candidate_table']=table
                    args.update({k:table[k] for k in ('dofs','chain','regions','curl_side','curl_fractions') if k in table})
                row['result']=api.fit_pose(**args,apply=False,out=f"measurements/{job['id']}/pose.json")
                if not row['result'].get('ok',False): raise ValueError(row['result'].get('error',row['result']))
            elif action=='collar':
                row['result']=opening.run('variants',args['object'],root,**{k:v for k,v in args.items() if k!='object'},depths_mm=[10,20,35])
            else: raise ValueError('action is facing | pair | boots | pose | collar')
        except Exception as error:
            row['error']=str(error);row['ok']=False
        else: row['ok']=True
        output.append(row)
    result={'schema':'lampway.fit-decision-measurements/1','default_choices_applied':False,'jobs':output}
    out=_path(root,config.get('out','measurements/decisions.json'));out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result
