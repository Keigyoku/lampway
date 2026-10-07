# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured AC65 candidates on an owner's disposable scene; no default is selected.

Config supplies project-relative npz/plate paths and existing scene object names.
Pose candidate tables (including first-DOF sign expectations) are explicit inputs.
All receipts and views stay under the configured project root. Nothing is saved
back to the input blend, submitted to a provider, or promoted into canon settings.
"""
import json
from pathlib import Path
import numpy as np
from .. import canon_geom as G


def _path(root, value):
    path=(Path(root)/value).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('measurement paths must stay under the project root')
    return path


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
                modes=('common','per_side') if action=='pair' else (args.get('pair_scale_group','common'),)
                anchors=(args.get('scale_anchor'),) if action=='pair' else ('width','height','foot')
                body=_path(root,args['body']);piece=_path(root,args['piece'])
                b=np.load(body);row['candidates']=[]
                for mode in modes:
                    for anchor in anchors:
                        V,T,meta,report=fit_place.place(args['kind'],body,piece,args.get('turn',0),args.get('clear_mm',15),anchor,args.get('sides','both'),mode)
                        out=_path(root,f"measurements/{job['id']}/{mode}-{anchor or 'bracer'}.npz")
                        out.parent.mkdir(parents=True,exist_ok=True);np.savez(out,V=V,T=T)
                        candidate={'mode':mode,'anchor':anchor,'meta':meta,'report':report,'placed':str(out.relative_to(Path(root).resolve()))}
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
