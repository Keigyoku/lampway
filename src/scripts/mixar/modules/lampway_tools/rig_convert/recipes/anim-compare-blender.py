# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/recipes/anim-compare-blender.py, sha256 1918ad859e51), on 2026-10-06. A Blender recipe (headless Blender loads it by path).
"""Independently decode UE control/round-trip FBXs and compare sampled motion."""
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from axi_common import Parser, emit, publish
import animation_canon as ac


def read_motion(path, times, expected_bones, include_bind=False):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.render.fps_base = 1
    import lw_import                                      # canon_io, the one importer (the record stamps every datablock lw_raw)
    lw_import.import_raw(str(path), use_anim=True, ignore_leaf_bones=False)
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    if len(arms) != 1 or not arms[0].animation_data or not arms[0].animation_data.action:
        raise ValueError("expected one animated armature")
    arm = arms[0]
    names = set(arm.pose.bones.keys())
    object_root = arm.name if set(expected_bones)-names == {arm.name} else None
    if object_root:
        names.add(object_root)
    if names != set(expected_bones):
        raise ValueError("bone roster differs: missing=" + str(sorted(set(expected_bones)-names))
                         + " extra=" + str(sorted(names-set(expected_bones))))
    rest = {}
    if include_bind:
        def value(matrix):
            p, q, s = matrix.decompose()
            return {'translation':[float(x)*100 for x in p],
                    'rotation':[q.x,q.y,q.z,q.w], 'scale':list(s)}
        rest['bind_pose'] = {b.name:value(arm.matrix_world @ b.matrix_local) for b in arm.data.bones}
        rest['parents'] = {b.name:b.parent.name if b.parent else object_root for b in arm.data.bones}
        if object_root:
            rest['bind_pose'][object_root] = value(arm.matrix_world)
            rest['parents'][object_root] = None
    action = arm.animation_data.action
    start, end = action.frame_range
    fps = scene.render.fps / scene.render.fps_base
    end_time = times[-1][0]/times[-1][1]
    tail = (end-start)/fps - end_time
    if tail < -0.000001 or tail > 1/30 + 0.000001:
        raise ValueError("FBX action does not cover source duration within one terminal export key")
    samples = []
    def evaluate(frame):
        scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        bpy.context.view_layer.update()
        evaluated = arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        pose = {}
        matrices = {bone.name: evaluated.matrix_world @ bone.matrix for bone in evaluated.pose.bones}
        if object_root:
            matrices[object_root] = evaluated.matrix_world
        for name, matrix in matrices.items():
            position, rotation, scale = matrix.decompose()
            pose[name] = {"translation": [float(x)*100 for x in position],
                               "rotation": [rotation.x, rotation.y, rotation.z, rotation.w],
                               "scale": list(scale)}
        return pose
    for time in times:
        samples.append({"time": time, "pose": evaluate(start + time[0]/time[1]*fps)})
    # Epic's exporter deliberately writes one key after EndFrameTime. Prove
    # that this is a held terminal key; never stretch the motion to its range.
    tail_check = ac.compare([samples[-1]], [{"time": times[-1], "pose": evaluate(end)}])
    if tail_check["translation_max"] > 0.001 or tail_check["rotation_max_degrees"] > 0.001:
        raise ValueError("extra FBX terminal key changes the source end pose")
    if include_bind and object_root:
        # Blender stores this FBX root on the armature OBJECT. Without a native
        # object-bind table, animated object bases cannot be inferred from frame0.
        held = ac.compare([{'time':s['time'],'pose':{object_root:rest['bind_pose'][object_root]}} for s in samples],
                          [{'time':s['time'],'pose':{object_root:s['pose'][object_root]}} for s in samples])
        if held['translation_max']>0.0001 or held['rotation_max_degrees']>0.0001:
            raise ValueError('animated object root requires an explicit native FBX object bind')
    return dict(rest, **{"samples": samples, "frame_range": [start, end], "fps": fps,
            "export_tail_seconds": tail, "object_root": object_root,
            "terminal_hold": tail_check,
            "scene_unit_scale": scene.unit_settings.scale_length,
            "position_units": "Blender metres converted to cm", "bones": len(names)})


def compare_native(expected, profile, decoded):
    """Compare through measured REST axes; never fit an animated-frame offset."""
    ac._profile(profile)
    if profile['adapter']['centimeters_per_unit'] != 1:
        raise ValueError('native UE profile must be in centimeters')
    bones = {b['name']:b for b in profile['bones']}
    if set(decoded['bind_pose']) != set(bones) or set(decoded['parents']) != set(bones):
        raise ValueError('imported bind bone roster differs')
    def reflect(q):
        return [-q[0],q[1],-q[2],q[3]]
    offsets = {}
    for name, bone in bones.items():
        if decoded['parents'][name] != bone['parent']:
            raise ValueError('imported bind hierarchy differs')
        offsets[name] = ac.qmul(ac.qinv(reflect(bone['bind']['rotation'])),decoded['bind_pose'][name]['rotation'])
    def to_native(pose):
        if set(pose) != set(bones):
            raise ValueError('imported motion bone roster differs')
        result = {}
        for name, t in pose.items():
            p=t['translation']
            # Positions were converted from metres in read_motion. The linear
            # part of the decomposed FBX world matrix carries the same .01
            # import factor and must also be expressed in native cm units.
            result[name]={'translation':[p[0],-p[1],p[2]], 'scale':[v*100 for v in t['scale']],
                          'rotation':reflect(ac.qmul(t['rotation'],ac.qinv(offsets[name])))}
        return result
    bind=ac.compare([{'time':[0,1],'pose':{n:b['bind'] for n,b in bones.items()}}],
                    [{'time':[0,1],'pose':to_native(decoded['bind_pose'])}])
    check=ac.compare(expected,[{'time':s['time'],'pose':to_native(s['pose'])} for s in decoded['samples']])
    ok=all(c['translation_max']<=0.1 and c['rotation_max_degrees']<=0.1 and c['scale_max']<=0.00001 for c in [bind,check])
    return {'verdict':'PASS' if ok else 'FAIL','motion':check,'bind':bind,
            'rest_axis_offsets':offsets,'basis_reflection':[1,-1,1],'linear_units_to_native':100,
            'limit':'Rest axes account for FBX joint conventions; motion and bind positions, not skin or gait.'}


def canonical_report(source):
    rows=[];errors=[]
    for row in source['cases']:
        try:
            if 'error' in row or 'error' in row.get('conversion',{}):
                raise ValueError('native conversion failed')
            path=Path(row['export']['path'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['export']['sha256']:
                raise ValueError('export hash mismatch')
            decoded=read_motion(path,[s['time'] for s in row['expected']],
                                [b['name'] for b in row['profile']['bones']],include_bind=True)
            check=compare_native(row['expected'],row['profile'],decoded)
            rows.append({'source':row['source'],'export':row['export'],'comparison':check,'decoded':decoded})
        except (KeyError,ValueError,RuntimeError,OSError) as exc:
            errors.append({'source':row.get('source'),'error':str(exc)})
    return {'cases':rows,'errors':errors,'verdict':'PASS' if rows and not errors and all(r['comparison']['verdict']=='PASS' for r in rows) else 'FAIL'}


def main(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if not argv or argv in (["help"], ["status"]):
        emit({"tool": "anim-compare-blender", "state": "requires actual exported control/candidate motion",
              "help": ["blender -b --python anim-compare-blender.py -- --receipt <UE result.json> --out <json>",
                       "blender -b --python anim-compare-blender.py -- --canonical-receipt <native transfer result.json> --out <json>"]})
        return 0
    parser = Parser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--receipt")
    inputs.add_argument("--canonical-receipt")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        import bpy
        if args.canonical_receipt:
            source_path=Path(args.canonical_receipt)
            report=canonical_report(json.loads(source_path.read_text()))
            report.update(blender=bpy.app.version_string,input_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                          recipe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            publish(args.out,ac.encode(report))
            emit({'verdict':report['verdict'],'compared':len(report['cases']),'errors':report['errors'],
                  'receipt':args.out,'help':['Inspect every imported bind/motion measurement; skin and foot contact remain separate.']})
            return 0 if report['verdict']=='PASS' else 1
        source_path = Path(args.receipt)
        source = json.loads(source_path.read_text())
        report = {"blender": bpy.app.version_string, "input_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                  "recipe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "limits": {"translation_cm": 0.1, "rotation_degrees": 0.1, "scale": 0.00001},
                  "sequences": {}, "errors": source.get("errors", [])[:]}
        for name, row in source["sequences"].items():
            try:
                native = row["emitted_pose_round_trip"]
                times = [s["time"] for s in row["packet"]["samples"]]
                bones = [b["name"] for b in row["packet"]["profile"]["bones"]]
                decoded = {}
                for label, export in native["exports"].items():
                    path = Path(export["path"])
                    if hashlib.sha256(path.read_bytes()).hexdigest() != export["sha256"]:
                        raise ValueError("export hash mismatch: " + label)
                    decoded[label] = read_motion(path, times, bones)
                check = ac.compare(decoded["control"]["samples"], decoded["round_trip"]["samples"])
                # Epic ConvertToFbxPos negates Y (FbxUtilsImport.cpp:244–252).
                # This absolute cross-world check catches a shared scale/basis
                # error that a within-Blender control comparison could conceal.
                cross_world = []
                for expected, measured in zip(row["samples"], decoded["round_trip"]["samples"]):
                    for bone in bones:
                        native_position = expected["pose"][bone]["translation"]
                        blender = measured["pose"][bone]["translation"]
                        delta = [blender[0]-native_position[0], -blender[1]-native_position[1], blender[2]-native_position[2]]
                        cross_world.append({"time": expected["time"], "bone": bone,
                                            "axis_delta_cm": delta, "distance_cm": math.sqrt(sum(x*x for x in delta))})
                cross_max = max(m["distance_cm"] for m in cross_world)
                passed = (check["translation_max"] <= 0.1 and check["rotation_max_degrees"] <= 0.1
                          and check["scale_max"] <= 0.00001 and cross_max <= 0.1)
                report["sequences"][name] = {"verdict": "PASS" if passed else "FAIL",
                                              "cross_world": {"max_cm": cross_max, "measurements": cross_world,
                                                              "blender_to_ue": {"cm_per_unit": 100, "axis_sign": [1,-1,1]}},
                                              "comparison": check, "decoded": decoded, "exports": native["exports"]}
            except (KeyError, ValueError, RuntimeError) as exc:
                report["errors"].append({"sequence": name, "error": str(exc)})
        ok = (not report["errors"] and bool(report["sequences"])
              and all(row["verdict"] == "PASS" for row in report["sequences"].values()))
        report["verdict"] = "PASS" if ok else "FAIL"
        publish(args.out, ac.encode(report))
        emit({"verdict": report["verdict"], "compared": len(report["sequences"]), "errors": report["errors"],
              "receipt": args.out, "help": ["Read every bone/time divergence; this is motion round-trip, not cross-rig gait acceptance."]})
        return 0 if ok else 1
    except (OSError, ValueError, KeyError, ImportError) as exc:
        emit({"error": str(exc), "help": ["Run inside Blender with the retained UE round-trip result."]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
