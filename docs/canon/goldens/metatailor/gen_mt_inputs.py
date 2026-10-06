# Synthetic MetaTailor golden inputs MT-1..MT-4, built around the native MetaHuman's rest joints (body frame: Z up, -Y front).
import bpy, bmesh, json, math, os
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import os
# Paths come from the environment: MT_BODY_GLB = the native MetaHuman FullBody GLB (rest pose, 342 bones),
# MT_OUT = where the GLBs MetaTailor imports are written, MT_SRC = where the per-piece JSON (V, F, label, uv_N) goes.
OUT=os.environ['MT_OUT']; SRC=os.environ['MT_SRC']; os.makedirs(OUT,exist_ok=True); os.makedirs(SRC,exist_ok=True)
os.makedirs(SRC,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.environ['MT_BODY_GLB'])
for o in list(bpy.data.objects):
    if o.name.startswith('Icosphere'): bpy.data.objects.remove(o)
arm=[o for o in bpy.data.objects if o.type=='ARMATURE'][0]
body=[o for o in bpy.data.objects if o.type=='MESH'][0]
dg=bpy.context.evaluated_depsgraph_get(); ev=body.evaluated_get(dg); me=ev.to_mesh()
bm=bmesh.new(); bm.from_mesh(me); bm.transform(body.matrix_world); bvh=BVHTree.FromBMesh(bm)
J=lambda n: arm.matrix_world @ arm.data.bones[n].head_local
T=lambda n: arm.matrix_world @ arm.data.bones[n].tail_local
def ray_in(o,d,maxd=0.12,default=0.02):
    h=bvh.ray_cast(o,d,maxd); return h[3] if h[0] is not None else default
def ray_out(c,d,far=0.32):
    h=bvh.ray_cast(c+d*far,-d,far); return far-h[3] if h[0] is not None else None
def frame(d,hint=Vector((0,0,1))):
    d=d.normalized(); u=d.cross(hint)
    if u.length<1e-6: u=d.cross(Vector((1,0,0)))
    u.normalize(); return d,u,d.cross(u)
class Piece:
    def __init__(s,name): s.name=name; s.V=[]; s.F=[]; s.lab=[]; s.fmat=[]; s.mats=[]
    def mat(s,name,rgb):
        if name not in s.mats: s.mats.append(name); s.__dict__.setdefault('rgb',{})[name]=rgb
        return s.mats.index(name)
    def add(s,verts,faces,label,mi):
        b=len(s.V); s.V+= [tuple(v) for v in verts]; s.lab+=[label]*len(verts)
        for f in faces: s.F.append([b+i for i in f]); s.fmat.append(mi)
def tube(a,b,rings,na,offset,t0=0.02,t1=0.98,ang=None,hint=Vector((0,0,1)),lid=False):
    d,u,w=frame(b-a,hint); verts=[]; angs=ang if ang is not None else [2*math.pi*k/na for k in range(na)]
    for i in range(rings):
        t=t0+(t1-t0)*i/(rings-1); c=a+(b-a)*t
        for th in angs:
            dr=(u*math.cos(th)+w*math.sin(th)); verts.append(c+dr*(ray_in(c,dr)+offset))
    n=len(angs); closed=ang is None; faces=[]
    for i in range(rings-1):
        for k in range(n if closed else n-1):
            k2=(k+1)%n; faces.append([i*n+k,i*n+k2,(i+1)*n+k2,(i+1)*n+k])
    if lid:
        top=sum((verts[k] for k in range(n)),Vector())/n; ci=len(verts); verts.append(top)
        for k in range(n): faces.append([ci,(k+1)%n,k])
    return verts,faces
def ctube(a,b,rings,na,r,t0=0.02,t1=0.98,ang=None,hint=Vector((0,0,1)),zero=None):
    d=(b-a).normalized(); z=zero if zero is not None else hint; u=(z-d*z.dot(d)).normalized(); w=d.cross(u)
    angs=ang if ang is not None else [2*math.pi*k/na for k in range(na)]; V=[]
    for i in range(rings):
        c=a+(b-a)*(t0+(t1-t0)*i/(rings-1))
        for th in angs: V.append(c+(u*math.cos(th)+w*math.sin(th))*r)
    n=len(angs); closed=ang is None; F=[]
    for i in range(rings-1):
        for k in range(n if closed else n-1):
            k2=(k+1)%n; F.append([i*n+k,i*n+k2,(i+1)*n+k2,(i+1)*n+k])
    return V,F
def disk(p,nrm,r=0.004,seg=8):
    _,u,w=frame(nrm); verts=[p]+[p+(u*math.cos(2*math.pi*k/seg)+w*math.sin(2*math.pi*k/seg))*r for k in range(seg)]
    return verts,[[0,1+k,1+(k+1)%seg] for k in range(seg)]
pieces=[]
def sphere(c,r,nu=8,nv=6):
    V=[c+Vector((0,0,r))]
    for j in range(1,nv):
        t=math.pi*j/nv
        for i in range(nu):
            a=2*math.pi*i/nu; V.append(c+Vector((r*math.sin(t)*math.cos(a),r*math.sin(t)*math.sin(a),r*math.cos(t))))
    V.append(c+Vector((0,0,-r))); F=[]
    for i in range(nu): F.append([0,1+i,1+(i+1)%nu])
    for j in range(nv-2):
        for i in range(nu): a=1+j*nu+i; b=1+j*nu+(i+1)%nu; F.append([a,a+nu,b+nu,b])
    last=len(V)-1; base=1+(nv-2)*nu
    for i in range(nu): F.append([base+i,last,base+(i+1)%nu])
    return V,F
# ---------------- MT-1 glove (right hand)
g=Piece('mt1_glove_r'); LEA=g.mat('leather',(0.22,0.20,0.18)); CAP=g.mat('caps',(0.75,0.75,0.78))
chains={'thumb':['thumb_01_r','thumb_02_r','thumb_03_r'],'index':['index_01_r','index_02_r','index_03_r'],'middle':['middle_01_r','middle_02_r','middle_03_r'],
        'ring':['ring_01_r','ring_02_r','ring_03_r'],'pinky':['pinky_01_r','pinky_02_r','pinky_03_r']}
curled={f:[J(n) for n in c]+[T(c[-1])] for f,c in chains.items()}
wrist=J('hand_r'); n=(J('pinky_01_r')-J('index_01_r')).cross(J('middle_01_r')-wrist).normalized()
if (J('thumb_02_r')-wrist).dot(n)>0: n=-n    # dorsal = away from the thumb's palmar side
dors=n
# STRAIGHT fingers (a flat-hand glove): each finger keeps its base joint and its three phalanx lengths, laid along the hand's
# forward axis (wrist->middle_01 projected off the dorsal normal) plus its own splay; the thumb keeps its base direction.
fwd=(J('middle_01_r')-wrist); fwd=(fwd-dors*fwd.dot(dors)).normalized()
rad={}
pts={}
for f_,P in curled.items():
    L=[(P[i+1]-P[i]).length for i in range(3)]
    if f_=='thumb': d=(P[1]-P[0]); d=(d-dors*d.dot(dors)).normalized()
    else:
        sp=P[0]-wrist; sp=(sp-dors*sp.dot(dors)); d=(fwd*0.85+sp.normalized()*0.15).normalized()
    Q=[P[0]]
    for l in L: Q.append(Q[-1]+d*l)
    pts[f_]=Q
    rad[f_]=[]
    for i in range(3):   # the finger's own thickness, measured on the curled body finger at the phalanx middle
        a,b=P[i],P[i+1]; c=(a+b)/2; _,u,w=frame(b-a); rs=[ray_in(c,(u*math.cos(t)+w*math.sin(t)),0.03,0.008) for t in [k*math.pi/4 for k in range(8)]]
        rad[f_].append(sum(rs)/len(rs))
pv,pf=tube(wrist,J('middle_01_r'),6,20,0.003); g.add(pv,pf,'palm',LEA)
keyp=[('wrist','wrist',wrist)]
for f,P in pts.items():
    for i in range(3):
        a,b=P[i],P[i+1]; v,fc=ctube(a,b,5,12,rad[f][i]+0.003,hint=dors); g.add(v,fc,f'{f}_{i+1}',LEA)
        if not (f=='thumb' and i==0):
            d=(b-a).normalized(); dd=(dors-d*dors.dot(d)).normalized(); _,u,w=frame(b-a,hint=dd)
            # angles centred on the dorsal direction dd
            cv,cf=ctube(a,b,4,7,rad[f][i]+0.007,t0=0.12,t1=0.88,ang=[math.radians(x) for x in (-60,-40,-20,0,20,40,60)],hint=dd,zero=dd)
            g.add(cv,cf,f'cap_{f}_{i+1}',CAP)
    for i,p in enumerate(P): keyp.append((f,f'{f}_{i}',p))
KC={'wrist':(1,0,1),'thumb':(1,0,0),'index':(0,1,0),'middle':(0,0,1),'ring':(1,1,0),'pinky':(0,1,1)}
markers=[]
for fam,name,p in keyp:
    if fam=='wrist': d=Vector((0,0,1)); dd=dors
    else:
        P=pts[fam]; i=int(name[-1]); a=P[max(0,i-1)]; b=P[min(3,max(1,i))]; d=(b-a).normalized(); dd=(dors-d*dors.dot(d)).normalized()
    tip=(fam!='wrist' and name.endswith('_3'))
    if fam=='wrist': h=ray_in(p,dd,0.05,0.008); q=p+dd*(h+0.006); mi=g.mat('mk_wrist',KC['wrist'])
    else:
        i=int(name[-1]); r=rad[fam][min(2,max(0,i-1 if i>0 else 0))]
        if tip: p=P[2]+(P[3]-P[2])*0.85      # on the last phalanx, above its cap
        q=p+dd*(r+0.010); mi=g.mat('mk_tip' if tip else 'mk_'+fam,(1,1,1) if tip else KC[fam])
    v,fc=sphere(q,0.0045)
    g.add(v,fc,'marker_'+name,mi); markers.append({'name':name,'joint':list(p),'surface':list(q)})
json_pts={f_:[list(x) for x in Q] for f_,Q in pts.items()}
pieces.append(g)
# ---------------- MT-2 shoulder plate (accessory)
s=Piece('mt2_plate_r'); PL=s.mat('plate',(0.70,0.70,0.74))
p0=J('upperarm_r'); lat=(J('upperarm_r')-J('clavicle_r')); lat.z=0; lat.normalize(); c=(lat+Vector((0,0,0.6))).normalized(); _,u,w=frame(c,hint=Vector((0,1,0)))
V=[];F=[]; NA,NB=13,11
for i in range(NA):
    for j in range(NB):
        a=math.radians(-50+100*i/(NA-1)); b=math.radians(-40+80*j/(NB-1))
        dr=(c*math.cos(a)*math.cos(b)+u*math.sin(a)*math.cos(b)+w*math.sin(b)).normalized(); V.append(p0+dr*(ray_in(p0,dr,0.2)+0.02))
for i in range(NA-1):
    for j in range(NB-1): F.append([i*NB+j,(i+1)*NB+j,(i+1)*NB+j+1,i*NB+j+1])
s.add(V,F,'plate',PL); pieces.append(s)
# ---------------- MT-3 skirt: belt + 16 strips
k=Piece('mt3_skirt'); BE=k.mat('belt',(0.35,0.22,0.12)); ST=k.mat('strips',(0.55,0.15,0.12))
pc=J('pelvis'); NAB=64; V=[]
for z in (0.985,0.945):
    for a in range(NAB):
        th=2*math.pi*a/NAB; dr=Vector((math.cos(th),math.sin(th),0)); c0=Vector((0,pc.y,z)); r=ray_out(c0,dr) or 0.17; V.append(c0+dr*(r+0.015))
F=[[a,(a+1)%NAB,NAB+(a+1)%NAB,NAB+a] for a in range(NAB)]; k.add(V,F,'belt',BE)
strip_r=[]
for q in range(16):
    ths=[math.radians(q*22.5+1+(20.5)*cc/3) for cc in range(4)]; zs=[0.94-(0.34)*rr/9 for rr in range(10)]
    rmax=max((ray_out(Vector((0,pc.y,z)),Vector((math.cos(t),math.sin(t),0))) or 0) for t in ths for z in zs)+0.02; strip_r.append(rmax)
    V=[Vector((rmax*math.cos(t),pc.y+rmax*math.sin(t),z)) for z in zs for t in ths]
    F=[[r*4+cc,r*4+cc+1,(r+1)*4+cc+1,(r+1)*4+cc] for r in range(9) for cc in range(3)]; k.add(V,F,f'strip_{q:02d}',ST)
pieces.append(k)
# ---------------- MT-4 greave with a closed top lid (right leg)
gr=Piece('mt4_greave_r'); GR=gr.mat('greave',(0.60,0.60,0.64))
v,f=tube(J('calf_r'),J('foot_r'),12,24,0.015,t0=0.12,t1=0.88,hint=Vector((0,-1,0)),lid=True)
nlid=len(v)-1; gr.add(v[:],f,'greave',GR); 
for i in range(nlid,len(gr.lab)): gr.lab[i]='lid'
for i in range(nlid-24,nlid): pass
pieces.append(gr)
meta={}
for P in pieces:
    m=bpy.data.meshes.new(P.name); m.from_pydata([tuple(v) for v in P.V],[],P.F); m.update()
    ob=bpy.data.objects.new(P.name,m); bpy.context.scene.collection.objects.link(ob)
    for nm in P.mats:
        mt=bpy.data.materials.new(nm); mt.use_nodes=True; bs=mt.node_tree.nodes['Principled BSDF']; r,gg,b=P.rgb[nm]
        bs.inputs['Base Color'].default_value=(r,gg,b,1); m.materials.append(mt)
    for poly,mi in zip(m.polygons,P.fmat): poly.material_index=mi; poly.use_smooth=True
    uv=m.uv_layers.new(name='UVMap'); N=int(math.ceil(math.sqrt(len(P.V))))
    for li,l in enumerate(m.loops):
        i=l.vertex_index; uv.data[li].uv=(((i%N)+0.5)/N,((i//N)+0.5)/N)
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active=ob
    path=os.path.join(OUT,P.name+'.glb')
    bpy.ops.export_scene.gltf(filepath=path,use_selection=True,export_format='GLB',export_yup=True,export_normals=True,export_materials='EXPORT',export_texcoords=True)
    meta[P.name]={'verts':len(P.V),'faces':len(P.F),'grid_N':N,'labels':sorted(set(P.lab))}
    json.dump({'name':P.name,'V':[list(v) for v in P.V],'F':P.F,'label':P.lab,'uv_N':N,'frame':'blender body frame Z up -Y front, metres; the GLB is the glTF Y-up export'},open(os.path.join(SRC,P.name+'.json'),'w'))
json.dump({'pieces':meta,'markers':markers,'glove_joints':json_pts,'finger_radius_m':rad,'dorsal':list(dors),'strip_radius_m':strip_r,
           'joints':{nm:list(J(nm)) for nm in ['pelvis','upperarm_r','clavicle_r','hand_r','calf_r','foot_r','thigh_r']}},open(os.path.join(SRC,'inputs_meta.json'),'w'),indent=1)
print('META',json.dumps(meta))
# ---- the glove re-posed for clicking: one rigid transform taking dorsal -> -Y (toward MetaTailor's front camera),
# hand_r->middle_01 -> -Z, the glove centroid -> (0,0,1.0). Recorded; the fit is landmark-driven, so the source pose is free.
import mathutils
d3m=(pts['middle'][3]-pts['middle'][2]).normalized(); nview=dors
f=(J('middle_01_r')-wrist); f=(f-nview*f.dot(nview)).normalized(); s3=f.cross(nview)
Rsrc=mathutils.Matrix((list(nview),list(f),list(s3))).transposed()
dst_d=Vector((0,-1,0)); dst_f=Vector((0,0,-1)); dst_s=dst_f.cross(dst_d)
Rdst=mathutils.Matrix((list(dst_d),list(dst_f),list(dst_s))).transposed()
R=Rdst @ Rsrc.transposed(); cen=sum((Vector(v) for v in g.V),Vector())/len(g.V); tvec=Vector((0,0,1.0))-R @ cen
gv=Piece('mt1_glove_r_view'); gv.__dict__.update({k:v for k,v in g.__dict__.items() if k not in ('name','V')}); gv.V=[tuple(R @ Vector(v)+tvec) for v in g.V]
m=bpy.data.meshes.new(gv.name); m.from_pydata(gv.V,[],gv.F); m.update(); ob=bpy.data.objects.new(gv.name,m); bpy.context.scene.collection.objects.link(ob)
for nm in gv.mats:
    mt=bpy.data.materials.get(nm+'_v') or bpy.data.materials.new(nm+'_v'); mt.use_nodes=True; r,gg,b=gv.rgb[nm]; mt.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(r,gg,b,1); m.materials.append(mt)
for poly,mi in zip(m.polygons,gv.fmat): poly.material_index=mi; poly.use_smooth=True
uv=m.uv_layers.new(name='UVMap'); N=int(math.ceil(math.sqrt(len(gv.V))))
for li,l in enumerate(m.loops): i=l.vertex_index; uv.data[li].uv=(((i%N)+0.5)/N,((i//N)+0.5)/N)
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active=ob
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT,gv.name+'.glb'),use_selection=True,export_format='GLB',export_yup=True,export_normals=True,export_materials='EXPORT',export_texcoords=True)
json.dump({'R':[list(r) for r in R],'t':list(tvec),'note':'view = R @ source + t (blender body frame)'},open(os.path.join(SRC,'mt1_glove_r_view_transform.json'),'w'),indent=1)
print('VIEW', [round(x,4) for x in tvec], 'curl_deg', round(math.degrees(math.acos(max(-1,min(1,d3m.dot((J('middle_01_r')-wrist).normalized()))))),1))
