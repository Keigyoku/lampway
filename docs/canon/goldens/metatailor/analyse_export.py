# Black-box measurement of MetaTailor's output for the synthetic goldens MT-1..MT-4 (no binary inspection: FBX in, numbers out).
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
# MT_WORK holds export_canon_mt1-4/canon_mt1-4.fbx, mh_joints.json and src/ (written by gen_mt_inputs.py); results -> mt_results.json
S=os.environ['MT_WORK']; SRC=S+'/src'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=S+'/export_canon_mt1-4/canon_mt1-4.fbx', ignore_leaf_bones=False, automatic_bone_orientation=False, global_scale=100.0)
arm=bpy.data.objects['Armature']; body=bpy.data.objects['Model']
dg=bpy.context.evaluated_depsgraph_get()
def world_verts(o):
    e=o.evaluated_get(bpy.context.evaluated_depsgraph_get()); m=e.to_mesh(); M=o.matrix_world
    V=np.array([tuple(M @ v.co) for v in m.vertices]); e.to_mesh_clear(); return V
mh=json.load(open(S+'/mh_joints.json')); meta=json.load(open(SRC+'/inputs_meta.json'))
# frame check: exported armature joints vs the native MetaHuman joints
jerr={}
for n in ['pelvis','hand_r','upperarm_r','calf_r','foot_r','middle_01_r','index_03_r']:
    if n in arm.data.bones and n in mh: jerr[n]=round(1000*(arm.matrix_world @ arm.data.bones[n].head_local-Vector(mh[n])).length,3)
out={'frame_check_mm':jerr}
def body_bvh():
    e=body.evaluated_get(bpy.context.evaluated_depsgraph_get()); m=e.to_mesh(); M=body.matrix_world
    V=[M @ v.co for v in m.vertices]; F=[list(p.vertices) for p in m.polygons]; e.to_mesh_clear(); return BVHTree.FromPolygons(V,F)
def inside(bvh,p):
    c=0
    for d in (Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1))):
        o=Vector(p); n=0; k=0
        while k<64:
            h=bvh.ray_cast(o,d,10.0)
            if h[0] is None: break
            n+=1; o=h[0]+d*1e-5; k+=1
        c+= n%2
    return c>=2
def uvmatch(o,N,nsrc):
    me=o.data; uv=me.uv_layers[0].data; best=None
    for flip in (False,True):
        idx=-np.ones(len(me.vertices),int); bad=0
        for l in me.loops:
            u,v=uv[l.index].uv; v=1-v if flip else v
            i=int(round(u*N-0.5)); j=int(round(v*N-0.5)); s=i+N*j
            if not (0<=s<nsrc): bad+=1; continue
            if idx[l.vertex_index]>=0 and idx[l.vertex_index]!=s: bad+=1
            idx[l.vertex_index]=s
        if best is None or bad<best[1]: best=(idx,bad,flip)
    return best
def simfit(P,Q):
    mp,mq=P.mean(0),Q.mean(0); A,B=P-mp,Q-mq; U,Sv,Vt=np.linalg.svd(B.T @ A); d=np.sign(np.linalg.det(U @ Vt)) or 1; D=np.diag([1,1,d]); R=U @ D @ Vt
    s=float((Sv*np.diag(D)).sum()/(A**2).sum()); t=mq-s*R @ mp; r=np.linalg.norm(s*P @ R.T+t-Q,axis=1)
    ang=math.degrees(math.acos(max(-1,min(1,(np.trace(R)-1)/2))))
    return s,ang,float(np.sqrt((r**2).mean())),float(r.max()),R,t
def edges_of(F):
    E=set()
    for f in F:
        for a,b in zip(f,f[1:]+f[:1]): E.add((min(a,b),max(a,b)))
    return np.array(sorted(E))
def weights(o):
    names={g.index:g.name for g in o.vertex_groups}; W=[]
    for v in o.data.vertices:
        W.append({names[g.group]:g.weight for g in v.groups if g.weight>1e-4})
    return W
def analyse(name,srcname,transform=None,pose=None):
    src=json.load(open(SRC+f'/{srcname}.json')); Vs=np.array(src['V']); F=src['F']; lab=src['label']; N=src['uv_N']
    if transform is not None:
        R=np.array(transform['R']); t=np.array(transform['t']); Vs=Vs @ R.T+t
    o=bpy.data.objects[name]; idx,bad,flip=uvmatch(o,N,len(Vs)); Ve=world_verts(o)
    ok=idx>=0
    # export may split vertices at UV seams/normals: average all export vertices that map to one source vertex
    acc=np.zeros((len(Vs),3)); cnt=np.zeros(len(Vs))
    np.add.at(acc,idx[ok],Ve[ok]); np.add.at(cnt,idx[ok],1); cov=cnt>0; Vx=np.where(cov[:,None],acc/np.maximum(cnt,1)[:,None],np.nan)
    res={'export_vertices':len(Ve),'source_vertices':len(Vs),'uv_conflicts':bad,'uv_v_flipped':flip,'source_covered':int(cov.sum())}
    s,ang,rms,mx,R0,t0=simfit(Vs[cov],Vx[cov]); res['whole']={'scale':round(s,4),'rot_deg':round(ang,2),'rms_mm':round(rms*1000,2),'max_mm':round(mx*1000,2)}
    E=edges_of(F); L0=np.linalg.norm(Vs[E[:,0]]-Vs[E[:,1]],axis=1); L1=np.linalg.norm(Vx[E[:,0]]-Vx[E[:,1]],axis=1); good=(L0>1e-6)&cov[E[:,0]]&cov[E[:,1]]
    st=np.abs(L1[good]/L0[good]-1)
    res['edge_strain']={'median_pct':round(100*float(np.median(st)),2),'p95_pct':round(100*float(np.percentile(st,95)),2),'max_pct':round(100*float(st.max()),2)}
    labs=sorted(set(lab)); per={}
    Wt=weights(o); Wsrc=[{} for _ in Vs]
    for i in np.nonzero(ok)[0]:
        Wsrc[idx[i]]=Wt[i]
    for L in labs:
        ii=np.array([k for k,x in enumerate(lab) if x==L and cov[k]])
        if len(ii)<3: continue
        s2,a2,r2,m2,_,_=simfit(Vs[ii],Vx[ii]); eg=good&np.isin(E[:,0],ii)&np.isin(E[:,1],ii); st2=np.abs(L1[eg]/L0[eg]-1) if eg.any() else np.array([0.0])
        mass={}
        for k in ii:
            for b,w in Wsrc[k].items(): mass[b]=mass.get(b,0)+w
        tot=sum(mass.values()) or 1; top=sorted(mass.items(),key=lambda kv:-kv[1])[:3]
        infl=[len(Wsrc[k]) for k in ii]
        per[L]={'n':len(ii),'scale':round(s2,4),'rot_deg':round(a2,2),'rigid_rms_mm':round(r2*1000,3),'rigid_max_mm':round(m2*1000,3),'strain_med_pct':round(100*float(np.median(st2)),2),'strain_max_pct':round(100*float(st2.max()),2),
                'top_bones':[(b,round(w/tot,3)) for b,w in top],'influences_max':int(max(infl)),'influences_mean':round(float(np.mean(infl)),2)}
    res['parts']=per
    infl=[len(w) for w in Wt]; res['influences']={'max':int(max(infl)),'mean':round(float(np.mean(infl)),2)}
    res['bones_used']=sorted({b for w in Wt for b in w})
    # clearance against the exported avatar at the bind pose
    bvh=body_bvh(); d=[]; ins=0; ipl={}
    for k in np.nonzero(cov)[0]:
        p=Vector(Vx[k]); h=bvh.find_nearest(p); dist=(h[0]-p).length
        if inside(bvh,p): ins+=1; dist=-dist; ipl[lab[k]]=ipl.get(lab[k],0)+1
        d.append(dist)
    d=np.array(d); res['inside_by_part']=ipl
    gm=np.array([not lab[k].startswith('marker') for k in np.nonzero(cov)[0]])
    if not gm.all(): res['clearance_bind_garment_only']={'min_mm':round(1000*float(d[gm].min()),2),'p01_mm':round(1000*float(np.percentile(d[gm],1)),2),'median_mm':round(1000*float(np.median(d[gm])),2),'inside_vertices':int((d[gm]<0).sum()),'of':int(gm.sum())}
    res['clearance_bind']={'min_mm':round(1000*float(d.min()),2),'median_mm':round(1000*float(np.median(d)),2),'inside_vertices':int(ins),'of':int(len(d))}
    # the same against the SOURCE placement (what we authored)
    if transform is None:
        ds=[]; ins_s=0
        for k in range(len(Vs)):
            p=Vector(Vs[k]); h=bvh.find_nearest(p); dist=(h[0]-p).length
            if inside(bvh,p): ins_s+=1; dist=-dist
            ds.append(dist)
        ds=np.array(ds); res['clearance_source']={'min_mm':round(1000*float(ds.min()),2),'median_mm':round(1000*float(np.median(ds)),2),'inside_vertices':int(ins_s)}
        dv=np.linalg.norm(Vx-Vs,axis=1); mv=np.nonzero(dv>1e-3)[0]
        res['moved_vertices']={'count_gt_1mm':int(len(mv)),'labels':sorted({lab[q] for q in mv}),'source_clearance_of_moved_mm':[round(1000*float(ds[q]),1) for q in mv][:20],'export_clearance_of_moved_mm':[round(1000*float(d[list(np.nonzero(cov)[0]).index(q)]),1) for q in mv][:20]}
        res['displacement_source_to_export_mm']={'median':round(1000*float(np.nanmedian(np.linalg.norm(Vx[cov]-Vs[cov],axis=1))),2),'max':round(1000*float(np.nanmax(np.linalg.norm(Vx[cov]-Vs[cov],axis=1))),2)}
    return res,idx,cov,Vs,Vx,E,L0,lab,Wsrc
R={}
VT=json.load(open(SRC+'/mt1_glove_r_view_transform.json'))
cases={'MT-1':('mt1_glove_r_view','mt1_glove_r',VT),'MT-2':('mt2_plate_r','mt2_plate_r',None),'MT-3':('mt3_skirt','mt3_skirt',None),'MT-4':('mt4_greave_r','mt4_greave_r',None)}
keep={}
for k,(o,sname,tr) in cases.items():
    r,*rest=analyse(o,sname,tr); R[k]=r; keep[k]=rest
# MT-1 landmarks: each marker sphere's centre vs the avatar joint it marks
jmap={'wrist':'hand_r'}
for f in ('thumb','index','middle','ring','pinky'):
    for i in range(3): jmap[f'{f}_{i}']=f'{f}_0{i+1}_r'
idx,cov,Vs,Vx,E,L0,lab,W=keep['MT-1']; mk={}
for name,bone in jmap.items():
    ii=[k for k,x in enumerate(lab) if x=='marker_'+name and cov[k]]
    if not ii or bone not in arm.data.bones: continue
    c=Vx[ii].mean(0); j=np.array(arm.matrix_world @ arm.data.bones[bone].head_local); mk[name]=round(1000*float(np.linalg.norm(c-j)),1)
src_off={m['name']:round(1000*float(np.linalg.norm(np.array(m['surface'])-np.array(m['joint']))),1) for m in meta['markers']}
R['MT-1']['marker_to_avatar_joint_mm']=mk; R['MT-1']['marker_authored_offset_mm']={k:src_off.get(k) for k in mk}
# MT-3 skirt: thigh share of the strips' weights by height band
idx,cov,Vs,Vx,E,L0,lab,W=keep['MT-3']; band={}
for k,x in enumerate(lab):
    if not x.startswith('strip') or not cov[k]: continue
    z=round(float(Vs[k][2]),2); w=W[k]; tot=sum(w.values()) or 1
    th=sum(v for b,v in w.items() if b.startswith('thigh') or b.startswith('calf'))/tot
    band.setdefault(z,[]).append(th)
R['MT-3']['thigh_share_by_height']={str(z):round(float(np.mean(v)),3) for z,v in sorted(band.items(),reverse=True)}
# ---- pose tests with THEIR weights (body and pieces share the exported armature)
def rot_world(bone,axis,deg):
    pb=arm.pose.bones[bone]; Mw=arm.matrix_world @ pb.matrix; h=Mw.translation.copy()
    Rm=Matrix.Rotation(math.radians(deg),4,Vector(axis))
    pb.matrix=arm.matrix_world.inverted() @ (Matrix.Translation(h) @ Rm @ Matrix.Translation(-h) @ Mw)
    bpy.context.view_layer.update()
def reset():
    for pb in arm.pose.bones: pb.matrix_basis=Matrix()
    bpy.context.view_layer.update()
def measure(k,objname):
    idx,cov,Vs,Vx,E,L0,lab,W=keep[k]; o=bpy.data.objects[objname]; Ve=world_verts(o)
    acc=np.zeros((len(Vs),3)); cnt=np.zeros(len(Vs)); ok=idx>=0; np.add.at(acc,idx[ok],Ve[ok]); np.add.at(cnt,idx[ok],1); P=acc/np.maximum(cnt,1)[:,None]
    Lb=np.linalg.norm(Vx[E[:,0]]-Vx[E[:,1]],axis=1); Lp=np.linalg.norm(P[E[:,0]]-P[E[:,1]],axis=1); g=(Lb>1e-6)&cov[E[:,0]]&cov[E[:,1]]
    st=np.abs(Lp[g]/Lb[g]-1); bvh=body_bvh(); ins=sum(1 for q in np.nonzero(cov)[0] if inside(bvh,Vector(P[q])))
    per={}
    for L in sorted(set(lab)):
        ii=np.array([q for q,x in enumerate(lab) if x==L and cov[q]])
        if len(ii)<3 or L.startswith('marker'): continue
        s2,a2,r2,m2,_,_=simfit(Vx[ii],P[ii]); per[L]=round(r2*1000,2)
    grp={}
    for L in sorted(set(lab)):
        key=L.split('_')[0]
        m=g&np.array([lab[a]==L and lab[b]==L for a,b in E])
        if m.any(): grp.setdefault(key,[]).extend(list(np.abs(Lp[m]/Lb[m]-1)))
    cross=g&np.array([lab[a]!=lab[b] for a,b in E])
    return {'strain_by_group_p95_pct':{k:round(100*float(np.percentile(v,95)),2) for k,v in grp.items()},'strain_cross_label_edges_p95_pct':round(100*float(np.percentile(np.abs(Lp[cross]/Lb[cross]-1),95)),2) if cross.any() else None,
            'inside_by_part':{L:int(sum(1 for q in np.nonzero(cov)[0] if lab[q]==L and inside(bvh,Vector(P[q])))) for L in sorted(set(lab)) if not L.startswith('marker')} if k=='MT-1' else None,
            'strain_med_pct':round(100*float(np.median(st)),2),'strain_p95_pct':round(100*float(np.percentile(st,95)),2),'strain_max_pct':round(100*float(st.max()),2),
            'inside_body_vertices_garment':int(sum(1 for q in np.nonzero(cov)[0] if not lab[q].startswith('marker') and inside(bvh,Vector(P[q])))),'inside_body_vertices':int(ins),'of':int(cov.sum()),'part_rigid_rms_mm_vs_bind':per}
poses={}
reset(); rot_world('thigh_l',(1,0,0),-60); rot_world('thigh_r',(1,0,0),-60); poses['MT-3 hips_flexed_60']=measure('MT-3','mt3_skirt')
reset(); rot_world('calf_r',(1,0,0),90); poses['MT-4 knee_bent_90']=measure('MT-4','mt4_greave_r')
reset(); rot_world('upperarm_r',(0,1,0),-60); poses['MT-2 arm_raised_60']=measure('MT-2','mt2_plate_r')
reset()
hand=arm.matrix_world @ arm.data.bones['hand_r'].head_local; kn=(arm.matrix_world @ arm.data.bones['pinky_01_r'].head_local)-(arm.matrix_world @ arm.data.bones['index_01_r'].head_local); kn.normalize()
for f in ('index','middle','ring','pinky'):
    for i in ('01','02','03'): rot_world(f'{f}_{i}_r',tuple(kn),-40)
poses['MT-1 fist_40_per_joint']=measure('MT-1','mt1_glove_r_view')
tip=arm.matrix_world @ arm.pose.bones['middle_03_r'].head; 
idx1,cov1,Vs1,Vx1,E1,L01,lab1,W1=keep['MT-1']
dors=np.mean([Vx1[q] for q,x in enumerate(lab1) if x=='marker_middle_1'],0)-np.array(arm.matrix_world @ arm.data.bones['middle_02_r'].head_local)
reset(); tip0=arm.matrix_world @ arm.pose.bones['middle_03_r'].head
poses['MT-1 fist_40_per_joint']['middle_03_head_move_along_dorsal_mm']=round(1000*float(np.dot(np.array(tip-tip0),dors/np.linalg.norm(dors))),1)
reset()

# ---- seam behaviour: distances between separate parts, in the source, the export bind, and each pose
def posed(k,objname):
    idx,cov,Vs,Vx,E,L0,lab,W=keep[k]; Ve=world_verts(bpy.data.objects[objname])
    acc=np.zeros((len(Vs),3)); cnt=np.zeros(len(Vs)); ok=idx>=0; np.add.at(acc,idx[ok],Ve[ok]); np.add.at(cnt,idx[ok],1); return acc/np.maximum(cnt,1)[:,None]
def part_gap(P,lab,F,a,b):
    fb=[f for f in F if all(lab[v]==b for v in f)]; bv=BVHTree.FromPolygons([Vector(x) for x in P],fb)
    d=[(bv.find_nearest(Vector(P[q]))[0]-Vector(P[q])).length for q,x in enumerate(lab) if x==a]
    return round(1000*float(min(d)),2),round(1000*float(np.median(d)),2)
def seams(k,objname,P):
    src=json.load(open(SRC+'/'+cases[k][1]+'.json')); F=src['F']; lab=src['label']; out={}
    if k=='MT-1':
        for L in sorted(set(lab)):
            if L.startswith('cap_'): out[L+'->'+L[4:]]=part_gap(P,lab,F,L,L[4:])
    if k=='MT-3':
        for i in range(16):
            a=f'strip_{i:02d}'; b=f'strip_{(i+1)%16:02d}'
            out[a+'->'+b]=part_gap(P,lab,F,a,b)
        tops=[]
        for i in range(16):
            a=f'strip_{i:02d}'; fb=[f for f in F if all(lab[v]=='belt' for v in f)]; bv=BVHTree.FromPolygons([Vector(x) for x in P],fb)
            ii=[q for q,x in enumerate(lab) if x==a]; zt=max(P[q][2] for q in ii)
            top=sorted(ii,key=lambda q:-src['V'][q][2])[:4]
            tops.append(min((bv.find_nearest(Vector(P[q]))[0]-Vector(P[q])).length for q in top))
        out['strip_top_to_belt_mm']={'min':round(1000*min(tops),2),'max':round(1000*max(tops),2)}
    if k=='MT-4': out['lid->greave']=part_gap(P,lab,F,'lid','greave')
    return out
SE={}
for k,o in (('MT-1','mt1_glove_r_view'),('MT-3','mt3_skirt'),('MT-4','mt4_greave_r')):
    idx,cov,Vs,Vx,E,L0,lab,W=keep[k]; SE[k]={'source':seams(k,o,Vs),'export_bind':seams(k,o,Vx)}
reset(); rot_world('thigh_l',(1,0,0),-60); rot_world('thigh_r',(1,0,0),-60); SE['MT-3']['hips_flexed_60']=seams('MT-3','mt3_skirt',posed('MT-3','mt3_skirt'))
reset(); rot_world('calf_r',(1,0,0),90); SE['MT-4']['knee_bent_90']=seams('MT-4','mt4_greave_r',posed('MT-4','mt4_greave_r'))
reset()
for f in ('index','middle','ring','pinky'):
    for i in ('01','02','03'): rot_world(f'{f}_{i}_r',tuple(kn),-40)
SE['MT-1']['fist_40_per_joint']=seams('MT-1','mt1_glove_r_view',posed('MT-1','mt1_glove_r_view'))
reset()
out['seams_min_median_mm']=SE
out.update({'cases':R,'poses':poses})
json.dump(out,open(S+'/mt_results.json','w'),indent=1)
print('DONE')
