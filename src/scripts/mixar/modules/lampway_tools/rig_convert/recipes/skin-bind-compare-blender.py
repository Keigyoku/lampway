# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/recipes/skin-bind-compare-blender.py, sha256 f5d472ffd0ac), on 2026-10-06. A Blender recipe (headless Blender loads it by path).
"""Compare actual FBX rest, morphs, weights and evaluated poses in fresh Blender imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import canon
import skin_bind


def normal_errors(first,second,tolerance):
    if isinstance(tolerance,bool) or not isinstance(tolerance,(int,float)) or not math.isfinite(tolerance) or tolerance<=0:
        raise ValueError("normal tolerance must be positive and finite")
    if len(first)!=len(second) or not first:raise ValueError('normal corner count differs or empty')
    angles=[]
    for x,y in zip(first,second):
        if any(not math.isfinite(v) for v in x+y) or abs(math.hypot(*x)-1)>1e-6 or abs(math.hypot(*y)-1)>1e-6:
            raise ValueError('normal oracle is not a finite unit vector')
        cross=[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
        angles.append(math.degrees(math.atan2(math.hypot(*cross),math.fsum(a*b for a,b in zip(x,y)))))
    worst=max(range(len(angles)),key=angles.__getitem__)
    return {'max_degrees':angles[worst],'worst_corner':worst,'corners':len(angles),
            'over_tolerance':sum(x>tolerance for x in angles),'tolerance_degrees':tolerance}

def load_rules(path):
    rules=json.loads(Path(path).read_text())
    if rules.get('schema')!='titan.normal-comparison/1':raise ValueError('unsupported normal comparison rules')
    for key in ('rest_degrees','posed_degrees','control_max_posed_degrees','margin_degrees'):
        value=rules.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError('invalid normal calibration '+key)
    if abs(rules['posed_degrees']-math.fsum([rules['control_max_posed_degrees'],rules['margin_degrees']]))>1e-12:
        raise ValueError('posed tolerance must equal the authored control maximum plus margin')
    if len(rules.get('control_receipt_sha256',''))!=64:raise ValueError('control receipt hash required')
    return rules


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if '--' in args: args=args[args.index('--')+1:]
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('reference','candidate','mesh','space','poses','out-dir'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--rules',default=str(Path(__file__).with_name('skin-bind-compare-rules.json')))
    a=parser.parse_args(args)
    rules=load_rules(a.rules)
    import bpy
    from mathutils import Matrix,Vector
    if bpy.app.version_string!=rules['blender']:
        raise ValueError('normal calibration requires the declared Blender version; rerun the unchanged-source control')
    out=Path(a.out_dir).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('comparison requires a fresh output directory')
    space=json.loads(Path(a.space).read_text());canon._space(space)
    poses=json.loads(Path(a.poses).read_text())
    if not isinstance(poses,dict) or not poses: raise ValueError('authored pose map is empty')
    for name,bones in poses.items():
        if not isinstance(name,str) or not name or not name.replace('-','').replace('_','').isalnum() or not isinstance(bones,dict):
            raise ValueError('invalid authored pose name or bone map')
        for basis in bones.values(): skin_bind.validate_affine(basis)
    out.mkdir(parents=True,exist_ok=True)
    C=Matrix([[space['unit_cm']*x for x in row]+[0] for row in space['basis_to_canonical']]+[[0,0,0,1]])
    def points_error(first,second):
        if len(first)!=len(second): raise ValueError('vertex/corner count differs')
        return max((math.dist(x,y) for x,y in zip(first,second)),default=0.)
    framing=None
    def extract(label,path):
        nonlocal framing
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import lw_import                                  # canon_io, the one importer
        lw_import.import_raw(str(path),use_anim=False,automatic_bone_orientation=False)
        ob=bpy.data.objects.get(a.mesh)
        if ob is None or ob.type!='MESH': raise ValueError('selected mesh absent: '+a.mesh)
        if len(ob.modifiers)!=1 or ob.modifiers[0].type!='ARMATURE': raise ValueError('requires one Armature modifier')
        mod=ob.modifiers[0];arm=mod.object
        if not arm or mod.use_deform_preserve_volume or not mod.use_vertex_groups or mod.vertex_group or mod.use_bone_envelopes:
            raise ValueError('requires unmasked linear blend skinning')
        arm.animation_data_clear();arm.data.pose_position='POSE'
        for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
        for other in bpy.data.objects:
            if other.type=='MESH' and other!=ob:other.hide_render=True
        data=ob.data;world=C @ ob.matrix_world
        rest=[list(world @ v.co) for v in data.vertices]
        morphs={}
        if data.shape_keys:
            for key in list(data.shape_keys.key_blocks)[1:]:
                if key.value: raise ValueError('active morph is not a rest artifact')
                morphs[key.name]=[list(world.to_3x3() @ (point.co-data.vertices[i].co)) for i,point in enumerate(key.data)]
        weights=[]
        for v in data.vertices:
            row={}
            for group in v.groups:
                if group.weight<=0:continue
                name=ob.vertex_groups[group.group].name
                if name not in arm.data.bones:raise ValueError('unknown weighted bone '+name)
                row[name]=float(group.weight)
            if not row:raise ValueError('vertex has no weight mass')
            weights.append(row)
        result={'rest':rest,'morphs':morphs,'weights':weights,
                'face_smooth':[p.use_smooth for p in data.polygons],
                'normals':[list((world.to_3x3().inverted().transposed() @ n.vector).normalized()) for n in data.corner_normals],
                'faces':[list(p.vertices) for p in data.polygons],
                'uv':[list(x.uv) for x in data.uv_layers.active.data] if data.uv_layers.active else None,
                'materials':[m.name if m else None for m in data.materials],
                'face_mat':[p.material_index if data.materials else -1 for p in data.polygons],
                'hierarchy':{b.name:b.parent.name if b.parent else None for b in arm.data.bones},'poses':{},'pose_normals':{}}
        if framing is None:
            positions=[ob.matrix_world @ v.co for v in data.vertices]
            low=Vector([min(p[k] for p in positions) for k in range(3)])
            high=Vector([max(p[k] for p in positions) for k in range(3)])
            framing=((low+high)*.5,max(high-low)*1.35)
        for name,changes in sorted(poses.items()):
            for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
            for bone,basis in changes.items():
                if bone not in arm.pose.bones:raise ValueError('pose names absent bone '+bone)
                arm.pose.bones[bone].matrix_basis=Matrix(basis)
            bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
            evaluated=ob.evaluated_get(graph);mesh=evaluated.to_mesh()
            try:
                if [list(p.vertices) for p in mesh.polygons]!=result['faces']:raise ValueError('posed topology changed')
                result['poses'][name]=[list(C @ evaluated.matrix_world @ v.co) for v in mesh.vertices]
                nm=(C @ evaluated.matrix_world).to_3x3().inverted().transposed()
                result['pose_normals'][name]=[list((nm @ n.vector).normalized()) for n in mesh.corner_normals]
            finally:evaluated.to_mesh_clear()
            if a.render:
                scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
                scene.display.shading.light='STUDIO';scene.display.shading.color_type='SINGLE'
                scene.display.shading.single_color=(.6,.6,.6)
                scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
                center,size=framing
                camera=bpy.data.objects.new('CompareCamera',bpy.data.cameras.new('CompareCamera'))
                scene.collection.objects.link(camera);camera.location=center+Vector((0,-size*2,0))
                camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
                camera.data.type='ORTHO';camera.data.ortho_scale=size;scene.camera=camera
                scene.render.resolution_x=640;scene.render.resolution_y=640;scene.render.resolution_percentage=100
                scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/(label+'-'+name+'.png'))
                bpy.ops.render.render(write_still=True)
        return result
    reference=Path(a.reference).resolve();candidate=Path(a.candidate).resolve()
    ref=extract('reference',reference);got=extract('candidate',candidate)
    same_fields={key:ref[key]==got[key] for key in ('faces','materials','face_mat','hierarchy','face_smooth')}
    normals={'rest':normal_errors(ref['normals'],got['normals'],rules['rest_degrees']),
             'poses':{name:normal_errors(ref['pose_normals'][name],got['pose_normals'][name],rules['posed_degrees']) for name in sorted(poses)}}
    rest=points_error(ref['rest'],got['rest'])
    uv=points_error(ref['uv'],got['uv']) if ref['uv'] is not None and got['uv'] is not None else (0. if ref['uv']==got['uv'] else None)
    morph_names=set(ref['morphs'])==set(got['morphs'])
    morph_errors={name:points_error(ref['morphs'][name],got['morphs'][name]) for name in sorted(set(ref['morphs'])&set(got['morphs']))}
    if len(ref['weights'])!=len(got['weights']):raise ValueError('weight vertex count differs')
    weight_error=max(abs(a.get(name,0)-b.get(name,0)) for a,b in zip(ref['weights'],got['weights']) for name in set(a)|set(b))
    weight_names=all(set(a)==set(b) for a,b in zip(ref['weights'],got['weights']))
    pose_errors={name:points_error(ref['poses'][name],got['poses'][name]) for name in sorted(poses)}
    movement={name:points_error(ref['rest'],ref['poses'][name]) for name in sorted(poses)}
    passed=(all(same_fields.values()) and rest<=.001 and uv is not None and uv<=.00001
            and morph_names and max(morph_errors.values(),default=0)<=.001 and weight_names and weight_error<=.000001
            and max(pose_errors.values())<=.001 and normals['rest']['over_tolerance']==0
            and all(row['over_tolerance']==0 for row in normals['poses'].values()))
    receipt={'verdict':'PASS' if passed else 'FAIL','vertices':len(ref['rest']),
             'rest_max_error_cm':rest,'uv_max_error':uv,'same_fields':same_fields,
             'normal_errors':normals,'normal_rules':rules,'normal_rules_sha256':hashlib.sha256(Path(a.rules).read_bytes()).hexdigest(),
             'morph_names_equal':morph_names,'morph_count_reference':len(ref['morphs']),
             'morph_count_candidate':len(got['morphs']),'morph_max_error_cm':morph_errors,
             'weight_names_equal':weight_names,'weight_max_error':weight_error,
             'pose_max_error_cm':pose_errors,'reference_pose_max_movement_cm':movement,
             'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [reference,candidate,Path(a.space),Path(a.poses)]},
             'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'scope':'same vertex identities; rest/morph/weight/posed geometry and rest/posed corner normals; workbench renders, textures and morph-normal deltas unverified'}
    (out/'result.json').write_bytes(canon.serialize(receipt));print(json.dumps(receipt,indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
