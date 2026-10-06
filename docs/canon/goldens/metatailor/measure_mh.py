# Native MetaHuman rest joints (world, metres) for the analyser's frame check -> $MT_WORK/mh_joints.json
import bpy, json, os
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.environ['MT_BODY_GLB'])
arm=[o for o in bpy.data.objects if o.type=='ARMATURE'][0]
names=['pelvis','spine_05','neck_01','head','clavicle_r','upperarm_r','lowerarm_r','hand_r','clavicle_l','upperarm_l','lowerarm_l','hand_l',
 'thigh_l','calf_l','foot_l','ball_l','thigh_r','calf_r','foot_r','ball_r']
for s in 'r':
  for f in ('thumb','index','middle','ring','pinky'):
    for k in ('01','02','03'): names.append(f'{f}_{k}_{s}')
  for f in ('index','middle','ring','pinky'): names.append(f'{f}_metacarpal_{s}')
out={n:list(arm.matrix_world @ arm.data.bones[n].head_local) for n in names if n in arm.data.bones}
out['_tips']={}
for f in ('thumb','index','middle','ring','pinky'):
  b=arm.data.bones.get(f'{f}_03_r')
  if b: out['_tips'][f]=list(arm.matrix_world @ b.tail_local)
me=[o for o in bpy.data.objects if o.type=='MESH']
import mathutils
zs=[ (o.matrix_world @ v.co).z for o in me for v in o.data.vertices[:]] 
out['_height']=[min(zs),max(zs)]
out['_bones']=len(arm.data.bones)
json.dump(out,open(os.environ['MT_WORK']+'/mh_joints.json','w'),indent=1)
print('DONE',len(out))
