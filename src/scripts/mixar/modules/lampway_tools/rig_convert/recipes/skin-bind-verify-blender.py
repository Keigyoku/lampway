# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/recipes/skin-bind-verify-blender.py, sha256 2e0845e5973b), on 2026-10-06. A Blender recipe (headless Blender loads it by path).
"""Blender adapter: explicit native binds versus independently evaluated skin."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import canon
import skin_bind


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if '--' in args: args=args[args.index('--')+1:]
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('fbx','mesh','space','poses','out-dir'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args(args)
    import bpy
    from mathutils import Matrix
    import math

    source=Path(a.fbx).resolve();out=Path(a.out_dir).resolve()
    space_raw=Path(a.space).read_bytes();pose_raw=Path(a.poses).read_bytes()
    space=json.loads(space_raw);poses=json.loads(pose_raw)
    if not isinstance(poses,dict) or not poses or any(
            not isinstance(k,str) or not k or not k.replace('-','').replace('_','').isalnum()
            or not isinstance(v,dict) for k,v in poses.items()):
        raise ValueError('poses must name a nonempty set of explicit bone-basis maps')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import lw_import                                      # canon_io, the one importer
    lw_import.import_raw(str(source),use_anim=False,automatic_bone_orientation=False)
    mesh=bpy.data.objects.get(a.mesh)
    if mesh is None or mesh.type!='MESH': raise ValueError('selected mesh not found: '+a.mesh)
    mods=list(mesh.modifiers)
    if len(mods)!=1 or mods[0].type!='ARMATURE':
        raise ValueError('requires exactly one Armature modifier; other deformation is unsupported')
    mod=mods[0];arm=mod.object
    if not arm or mod.use_deform_preserve_volume or not mod.use_vertex_groups or mod.vertex_group or mod.use_bone_envelopes:
        raise ValueError('requires unmasked linear blend skinning with vertex groups only')
    data=mesh.data
    if data.shape_keys and any(k.value for k in list(data.shape_keys.key_blocks)[1:]):
        raise ValueError('active shape keys require a separate morph pose oracle')
    normal_matrix=mesh.matrix_world.to_3x3().inverted().transposed()
    native={'meshes':[{'name':mesh.name,'verts':[list(mesh.matrix_world @ v.co) for v in data.vertices],
        'faces':[list(p.vertices) for p in data.polygons],
        'loop_uv':[list(x.uv) for x in data.uv_layers.active.data] if data.uv_layers.active else None,
        'materials':[m.name if m else None for m in data.materials],
        'face_mat':[p.material_index if data.materials else -1 for p in data.polygons],
        'shading':{'schema':canon.SHADING_FORM['schema'], 'face_smooth':[p.use_smooth for p in data.polygons],
                   'corner_normals':[list((normal_matrix @ n.vector).normalized()) for n in data.corner_normals]},
        'morphs':{k.name:[list(mesh.matrix_world.to_3x3() @ (p.co-data.vertices[i].co))
                          for i,p in enumerate(k.data)] for k in list(data.shape_keys.key_blocks)[1:]}
                  if data.shape_keys else {}}]}
    canonical=canon.normalize_mesh(native,space)
    C=Matrix([[space['unit_cm']*x for x in row]+[0] for row in space['basis_to_canonical']]+[[0,0,0,1]])
    Ci=C.inverted()
    def mat(m): return [[float(x) for x in row] for row in m]
    objroot='object::'+arm.name
    if objroot in arm.data.bones: raise ValueError('armature object root name collides with a bone')
    joints=[{'name':objroot,'parent':None,'bind':mat(C @ arm.matrix_world @ Ci)}]
    joints += [{'name':b.name,'parent':b.parent.name if b.parent else objroot,
                'bind':mat(C @ arm.matrix_world @ b.matrix_local @ Ci)} for b in arm.data.bones]
    weights=[];positive_names=set()
    for vertex in data.vertices:
        row=[]
        for group in vertex.groups:
            name=mesh.vertex_groups[group.group].name
            if group.weight>0:
                bone=arm.data.bones.get(name)
                if bone is None or not bone.use_deform:
                    raise ValueError('positive weight is not a deform bone: '+name)
                positive_names.add(name);row.append([name,float(group.weight)])
        weights.append(row)
    packet=skin_bind.capture(canonical,joints,{mesh.name:weights})
    outputs={'packet.json':canon.serialize(packet)};results=[]
    for name,changes in sorted(poses.items()):
        for p in arm.pose.bones: p.matrix_basis=Matrix.Identity(4)
        for bone,basis in changes.items():
            if bone not in arm.pose.bones: raise ValueError('pose names absent bone: '+bone)
            # The pure packet validator checks the affine numeric contract too.
            arm.pose.bones[bone].matrix_basis=Matrix(skin_bind.validate_affine(basis))
        bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get()
        evaluated_arm=arm.evaluated_get(graph)
        pose={objroot:mat(C @ evaluated_arm.matrix_world @ Ci)}
        pose.update({p.name:mat(C @ evaluated_arm.matrix_world @ p.matrix @ Ci) for p in evaluated_arm.pose.bones})
        predicted=skin_bind.evaluate(packet,pose,geometry_only=True)
        evaluated=mesh.evaluated_get(graph);em=evaluated.to_mesh()
        try:
            if len(em.vertices)!=len(weights): raise ValueError('evaluated vertex count differs')
            if [list(p.vertices) for p in em.polygons]!=native['meshes'][0]['faces']:
                raise ValueError('evaluated topology differs')
            oracle=[list(C @ evaluated.matrix_world @ v.co) for v in em.vertices]
        finally: evaluated.to_mesh_clear()
        errors=[math.dist(x,y) for x,y in zip(predicted['meshes'][0]['verts'],oracle)]
        movement=[math.dist(x,y) for x,y in zip(predicted['meshes'][0]['verts'],canonical['meshes'][0]['verts'])]
        outputs[name+'-pose.json']=canon.serialize(pose)
        outputs[name+'-oracle.json']=canon.serialize(oracle)
        outputs[name+'-evaluated.json']=canon.serialize(predicted)
        results.append({'pose':name,'max_error_cm':max(errors),'mean_error_cm':math.fsum(errors)/len(errors),
                        'max_movement_cm':max(movement),'vertices':len(errors),'pass':max(errors)<=.001})
    receipt={'source':str(source),'source_sha256':digest(source.read_bytes()),
             'space_sha256':digest(space_raw),'poses_sha256':digest(pose_raw),
             'generator_sha256':digest(Path(__file__).read_bytes()),
             'modules':{m.__name__:digest(Path(m.__file__).read_bytes()) for m in (canon,skin_bind)},
             'blender':bpy.app.version_string,'native_bones':len(arm.data.bones),
             'explicit_armature_object_root':objroot,'weighted_bones':len(positive_names),'space':space,
             'results':results,'outputs':{name:digest(raw) for name,raw in outputs.items()},
             'verdict':'PASS' if all(x['pass'] for x in results) else 'FAIL',
             'scope':'native bind/shading extraction and explicit geometry-only vertex evaluation; semantic rig profile, textures and posed normals unverified'}
    outputs['result.json']=canon.serialize(receipt)
    for name,raw in outputs.items():
        path=out/name
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes()!=raw)):
            raise ValueError('different-existing output refused: '+str(path))
    out.mkdir(parents=True,exist_ok=True)
    for name,raw in outputs.items():
        path=out/name
        if not path.exists():path.write_bytes(raw)
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['verdict']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
