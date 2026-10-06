#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/recipes/anim-normalize-ue.py, sha256 f391b0a89729), on 2026-10-06. A UE editor recipe: the UE leg is on hold, its tests are needs_box.
"""Extract complete native animation profiles and verify reversible canonical samples."""
import hashlib
import json
import re
from pathlib import Path
import sys

RIG_CONVERT = Path(__file__).resolve().parents[1] / "rig_convert"     # the ported canonical modules
sys.path.insert(0, str(RIG_CONVERT))
from axi_common import Parser, emit, publish
from editor_runner import run_editor
import animation_canon as ac


def validate(config):
    if set(config) != {"schema", "profiles", "sequences"} or config["schema"] != 1:
        raise ValueError("expected normalization recipe schema1")
    names = set()
    for p in config["profiles"]:
        if set(p) != {"name", "skeleton", "bones", "basis", "centimeters_per_unit", "alignment"}:
            raise ValueError("profile requires complete adapter, skeleton and alignment fields")
        if not p["name"].replace("-", "").isalnum() or p["name"] in names:
            raise ValueError("profile name must be unique and filename-safe")
        if not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", p["skeleton"]) or type(p["bones"]) is not int or p["bones"] < 1:
            raise ValueError("profile skeleton/count invalid")
        ac.qnorm(p["basis"])
        if p["centimeters_per_unit"] <= 0 or not p["alignment"]:
            raise ValueError("explicit positive units and alignment rules required")
        names.add(p["name"])
    if not names:
        raise ValueError("at least one full skeleton profile required")
    ids = set()
    for seq in config["sequences"]:
        if set(seq) != {"name", "profile", "asset", "source", "sha256"}:
            raise ValueError("sequence requires asset/profile and immutable source pin")
        if seq["profile"] not in names or not seq["name"].replace("_", "").isalnum() or seq["name"] in ids:
            raise ValueError("sequence name/profile invalid")
        if not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", seq["asset"]):
            raise ValueError("sequence asset must be a Game package")
        sha = seq["sha256"]
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("sequence requires a full lowercase sha256 pin")
        ids.add(seq["name"])
    assets = [row["asset"] for row in config["sequences"]]
    if len(assets) != len(set(assets)):
        raise ValueError("sequence destination packages must be unique")
    return config


EDITOR = r'''
import unreal, json, re, sys, traceback
from pathlib import Path
CFG=json.loads(Path(CFG).read_text())
sys.path.insert(0, CFG['tools'])
import animation_canon as ac

def import_sources(recipe):
    # Native-file intake is an explicit world edge, before canonical extraction.
    # Preflight the entire cohort before importing any file. Never save skeletons.
    import hashlib
    profiles={row['name']:row for row in recipe['profiles']}
    snapshots={};tasks=[]
    for row in recipe['sequences']:
        source=Path(row['source'])
        if source.suffix.lower()!='.fbx' or not source.is_absolute():
            raise ValueError('FBX intake requires absolute source FBX paths')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('FBX source changed before import: '+row['name'])
        if unreal.EditorAssetLibrary.does_asset_exist(row['asset']):
            raise ValueError('existing import destination refused: '+row['asset'])
        skeleton_path=profiles[row['profile']]['skeleton']
        skeleton=unreal.load_asset(skeleton_path)
        if not isinstance(skeleton,unreal.Skeleton):raise ValueError('import skeleton unavailable')
        if skeleton_path not in snapshots:
            file=Path(unreal.Paths.project_content_dir())/(skeleton_path[len('/Game/'):]+'.uasset')
            snapshots[skeleton_path]=(skeleton,file,hashlib.sha256(file.read_bytes()).hexdigest(),
                unreal.AnimPoseExtensions.get_reference_pose(skeleton).export_text())
        options=unreal.FbxImportUI();options.automated_import_should_detect_type=False
        options.mesh_type_to_import=unreal.FBXImportType.FBXIT_ANIMATION
        options.import_mesh=False;options.import_animations=True
        options.import_materials=False;options.import_textures=False;options.skeleton=skeleton
        data=options.anim_sequence_import_data
        data.set_editor_property('import_custom_attribute',True)
        data.set_editor_property('import_bone_tracks',True)
        data.set_editor_property('use_default_sample_rate',True)
        task=unreal.AssetImportTask();task.filename=str(source)
        task.destination_path,task.destination_name=row['asset'].rsplit('/',1)
        task.automated=True;task.replace_existing=False;task.save=False;task.options=options
        tasks.append((row,task,skeleton))
    result=[]
    for row,task,skeleton in tasks:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        assets=[unreal.load_asset(path) for path in task.imported_object_paths]
        if len(assets)!=1 or not isinstance(assets[0],unreal.AnimSequence):
            raise ValueError('FBX intake must create exactly one AnimSequence: '+row['name'])
        sequence=assets[0]
        if sequence.get_path_name().split('.')[0]!=row['asset'] or sequence.get_editor_property('skeleton')!=skeleton:
            raise ValueError('FBX intake changed destination or skeleton')
        if sequence.get_editor_property('additive_anim_type')!=unreal.AdditiveAnimationType.AAT_NONE:
            raise ValueError('additive FBX intake needs a separate delta contract')
        if not unreal.EditorAssetLibrary.save_loaded_asset(sequence,only_if_is_dirty=False):
            raise ValueError('could not save imported sequence')
        file=Path(unreal.Paths.project_content_dir())/(row['asset'][len('/Game/'):]+'.uasset')
        result.append({'source':row['source'],'source_sha256':row['sha256'],
                       'asset':sequence.get_path_name(),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                       'skeleton':skeleton.get_path_name(),'settings':{'sample_rate':30,
                       'import_custom_attribute':True,'import_bone_tracks':True,'import_mesh':False}})
    for path,(skeleton,file,sha,pose) in snapshots.items():
        if hashlib.sha256(file.read_bytes()).hexdigest()!=sha or unreal.AnimPoseExtensions.get_reference_pose(skeleton).export_text()!=pose:
            raise ValueError('source skeleton changed during animation-only import: '+path)
    return result

def transform(t):
    return {'translation':[t.translation.x,t.translation.y,t.translation.z],
            'rotation':[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],
            'scale':[t.scale3d.x,t.scale3d.y,t.scale3d.z]}

def sample(sequence, times, method):
    opts=unreal.AnimPoseEvaluationOptions()
    opts.set_editor_property('extract_root_motion',False)
    opts.set_editor_property('evaluation_type',method)
    result=[]
    for time in times:
        p=unreal.AnimPoseExtensions.get_anim_pose_at_time(sequence,time[0]/time[1],opts)
        names=[str(n) for n in unreal.AnimPoseExtensions.get_bone_names(p)]
        result.append({'time':time,'pose':{n:transform(unreal.AnimPoseExtensions.get_bone_pose(
            p,n,unreal.AnimPoseSpaces.WORLD)) for n in names}})
    return result

def emit_pose_round_trip(sequence, packet, restored, name):
    # Pose-only verification fixture: channel carry is checked independently.
    # Native UE durations are frame-grid values; refuse a material time stretch.
    length=float(ac._duration(packet['duration']));frames=round(length*30)
    if frames<1 or abs(length-frames/30)>0.000001:
        raise ValueError('native 30fps emission cannot represent duration within1e-6s')
    source_skel=sequence.get_editor_property('skeleton')
    job=Path(OUT).parent.name.replace('-','_')
    package='/Game/AnimationNormalizeVerify/'+job
    factory=unreal.AnimSequenceFactory();factory.set_editor_property('target_skeleton',source_skel)
    created=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,package,unreal.AnimSequence,factory)
    if created is None:raise ValueError('round-trip sequence creation failed')
    settings_path=package+'/CanonicalCompression'
    settings=unreal.load_asset(settings_path) if unreal.EditorAssetLibrary.does_asset_exist(settings_path) else None
    if settings is None:
        settings=unreal.AssetToolsHelpers.get_asset_tools().create_asset('CanonicalCompression',package,
            unreal.AnimBoneCompressionSettings,unreal.AnimBoneCompressionSettingsFactory())
    codecs=settings.get_editor_property('codecs')
    if len(codecs)!=1 or codecs[0].get_class().get_name()!='AnimBoneCompressionCodec_ACLSafe':
        codec_class=unreal.load_class(None,'/Script/ACLPlugin.AnimBoneCompressionCodec_ACLSafe')
        if codec_class is None:raise ValueError('ACL safe class unavailable')
        codec=unreal.new_object(codec_class,outer=settings)
        codec.set_editor_property('ErrorThreshold',0.0001)
        settings.set_editor_property('codecs',[codec])
    if abs(settings.get_editor_property('codecs')[0].get_editor_property('ErrorThreshold')-0.0001)>1e-10:
        raise ValueError('canonical codec configuration differs')
    unreal.EditorAssetLibrary.save_asset(settings.get_path_name(),only_if_is_dirty=False)
    created.set_editor_property('bone_compression_settings',settings)
    ctl=created.get_editor_property('controller');ctl.open_bracket('canonical pose round trip')
    ctl.set_frame_rate(unreal.FrameRate(30,1));ctl.set_number_of_frames(unreal.FrameNumber(frames))
    for b in packet['profile']['bones']:
        positions=[];rotations=[];scales=[]
        for frame in range(frames+1):
            pose=restored[frame]['pose'];world=pose[b['name']]
            if b['parent'] is None:
                position=world['translation'];rotation=world['rotation']
            else:
                parent=pose[b['parent']];inv=ac.qinv(parent['rotation'])
                position=ac.rotate(inv,[x-y for x,y in zip(world['translation'],parent['translation'])])
                rotation=ac.qnorm(ac.qmul(inv,world['rotation']))
            positions.append(unreal.Vector(*position));rotations.append(unreal.Quat(*rotation));scales.append(unreal.Vector(1,1,1))
        if not ctl.add_bone_curve(b['name']) or not ctl.set_bone_track_keys(b['name'],positions,rotations,scales):
            raise ValueError('controller refused bone '+b['name'])
    ctl.close_bracket()
    for prop in ('enable_root_motion','root_motion_root_lock','interpolation','rate_scale'):
        created.set_editor_property(prop,sequence.get_editor_property(prop))
    unreal.EditorAssetLibrary.save_asset(created.get_path_name(),only_if_is_dirty=False)
    times=packet['samples']
    times=[row['time'] for row in times]
    source=sample(sequence,times,unreal.AnimDataEvalType.COMPRESSED)
    candidate=sample(created,times,unreal.AnimDataEvalType.COMPRESSED)
    source_raw=sample(sequence,times,unreal.AnimDataEvalType.RAW)
    candidate_raw=sample(created,times,unreal.AnimDataEvalType.RAW)
    # Raw source is the uncompressed motion being normalized; the measured
    # OUTPUT is always the real runtime Compressed pose. Existing source ACL
    # loss is a separate control, not an error to bake into canonical motion.
    check=ac.compare(source_raw,candidate)
    diagnostic={'source_compression':ac.compare(source_raw,source),
                'candidate_compression':ac.compare(candidate_raw,candidate),
                'raw_round_trip':ac.compare(source_raw,candidate_raw),
                'old_compressed_comparison':ac.compare(source,candidate),
                'source_codec':sequence.get_editor_property('bone_compression_settings').get_path_name(),
                'candidate_codec':created.get_editor_property('bone_compression_settings').get_path_name()}
    exports={}
    for label,asset in [('control',sequence),('round_trip',created)]:
        path=Path(OUT).parent/(name+'-'+label+'.fbx')
        task=unreal.AssetExportTask();task.object=asset;task.filename=str(path)
        task.automated=True;task.prompt=False;task.replace_identical=False
        task.exporter=unreal.AnimSequenceExporterFBX()
        options=unreal.FbxExportOption();options.set_editor_property('export_preview_mesh',False)
        options.set_editor_property('ascii',False);task.options=options
        if not unreal.Exporter.run_asset_export_task(task) or not path.is_file():
            raise ValueError('FBX export failed '+label)
        exports[label]={'path':str(path),'sha256':__import__('hashlib').sha256(path.read_bytes()).hexdigest()}
    return {'asset':created.get_path_name(),'comparison':check,'exports':exports,'diagnostic':diagnostic,
            'expected':'uncompressed input motion','measured':'emitted runtime Compressed pose',
            'compression':{'codec':'ACLSafe','error_threshold_cm':0.0001},
            'duration_error':abs(length-frames/30),
            'verdict':'PASS' if check['translation_max']<=0.1 and check['rotation_max_degrees']<=0.1 else 'FAIL'}

report={'profiles':{},'sequences':{},'errors':[]}
if CFG.get('import_fbx'):
    try:report['imports']=import_sources(CFG['recipe'])
    except Exception:report['errors'].append({'import':traceback.format_exc()})
for cfg in CFG['recipe']['profiles']:
    try:
        skel=unreal.load_asset(cfg['skeleton'])
        if not isinstance(skel,unreal.Skeleton):raise ValueError('skeleton failed to load')
        pose=unreal.AnimPoseExtensions.get_reference_pose(skel)
        names=[str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
        if len(names)!=cfg['bones']:raise ValueError('actual bone count differs from authored pin')
        parents=[int(x) for x in re.search(r'ParentBoneIndices=\(([^()]*)\)',pose.export_text()).group(1).split(',')]
        bones=[{'name':n,'parent':names[parents[i]] if parents[i]>=0 else None,
                'local':transform(unreal.AnimPoseExtensions.get_ref_bone_pose(pose,n,unreal.AnimPoseSpaces.LOCAL))}
               for i,n in enumerate(names)]
        aligned=ac.align_reference(bones,cfg['alignment'])
        profile=ac.make_profile(cfg['name'],aligned,basis=cfg['basis'],centimeters_per_unit=cfg['centimeters_per_unit'])
        # Real tables must survive validation/idempotent use, not just serialize.
        ac.normalize([{'time':[0,1],'pose':{b['name']:b['reference'] for b in aligned}}],profile,duration='0',channels={})
        by_name={b['name']:b for b in aligned}
        rules=[]
        for rule in cfg['alignment']:
            a=by_name[rule['bone']]['reference']['translation'];b=by_name[rule['toward']]['reference']['translation']
            actual=[y-x for x,y in zip(a,b)];wanted=rule['direction']
            dot=sum(x*y for x,y in zip(actual,wanted))/(sum(x*x for x in actual)*sum(x*x for x in wanted))**.5
            rules.append({'bone':rule['bone'],'degrees':__import__('math').degrees(__import__('math').acos(max(-1,min(1,dot))))})
        if max(r['degrees'] for r in rules)>0.0001:raise ValueError('T reference rule readback failed')
        report['profiles'][cfg['name']]={'profile':profile,'alignment':rules,'source':cfg['skeleton']}
    except Exception:report['errors'].append({'profile':cfg['name'],'error':traceback.format_exc()})
for cfg in ([] if report['errors'] else CFG['recipe']['sequences']):
    try:
        p=report['profiles'][cfg['profile']]['profile']
        a=unreal.load_asset(cfg['asset'])
        if not isinstance(a,unreal.AnimSequence):raise ValueError('sequence failed to load')
        source_cfg=next(row for row in CFG['recipe']['profiles'] if row['name']==cfg['profile'])
        if a.get_editor_property('skeleton')!=unreal.load_asset(source_cfg['skeleton']):raise ValueError('sequence/profile skeleton mismatch')
        if a.get_editor_property('additive_anim_type')!=unreal.AdditiveAnimationType.AAT_NONE:raise ValueError('additive normalization needs a separate delta contract')
        duration=str(float(unreal.AnimationLibrary.get_sequence_length(a)))
        times=ac.sample_times(duration)
        model=a.get_editor_property('data_model_interface')
        curve_property='LegacyCurveData' if model.get_class().get_name()=='AnimationSequencerDataModel' else 'CurveData'
        curve_texts=[c.export_text() for c in model.get_editor_property(curve_property).float_curves]
        curves=[]
        for curve_name in unreal.AnimationLibrary.get_animation_curve_names(a,unreal.RawCurveTrackTypes.RCT_FLOAT):
            name=str(curve_name)
            text=next(t for t in curve_texts if json.loads(re.search(r'\bCurveName=("(?:\\.|[^"])*")',t).group(1))==name)
            key_times,key_values=unreal.AnimationLibrary.get_float_keys(a,curve_name)
            curves.append({'name':name,'rich_text':text,'times':list(key_times),'values':list(key_values)})
        channels={'root_motion':bool(a.get_editor_property('enable_root_motion')),
                  'notifies':[n.export_text() for n in unreal.AnimationLibrary.get_animation_notify_events(a)],
                  'sync_markers':[n.export_text() for n in unreal.AnimationLibrary.get_animation_sync_markers(a)],
                  'curves':curves}
        samples=sample(a,times,unreal.AnimDataEvalType.RAW)
        packet=ac.normalize(samples,p,duration=duration,channels=channels)
        repeated=ac.normalize(samples,p,duration=duration,channels=channels)
        if ac.encode(packet)!=ac.encode(repeated):raise ValueError('normalization is not deterministic')
        restored=ac.adapt(packet,p)
        check=ac.compare(samples,restored)
        if check['translation_max']>0.00001 or check['rotation_max_degrees']>0.00001:raise ValueError('canonical inverse changes native motion')
        report['sequences'][cfg['name']]={'packet':packet,'round_trip':check,'source':cfg,'samples':samples}
        if CFG['emit_round_trip']:
            emitted=emit_pose_round_trip(a,packet,restored,cfg['name'])
            report['sequences'][cfg['name']]['emitted_pose_round_trip']=emitted
            if emitted['verdict']!='PASS':raise ValueError('actual Compressed pose round-trip exceeds0.1cm/0.1degree')
    except Exception:report['errors'].append({'sequence':cfg['name'],'error':traceback.format_exc()})
Path(OUT).write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv in (["status"], ["help"]):
        emit({"tool": "anim-normalize-ue", "state": "explicit profile/clip recipe required; optional pinned FBX intake into new scratch packages",
              "help": ["--config <json> --engine <root> --project <scratch.uproject> --out-dir <directory> [--emit-round-trip] [--import-fbx]",
                       "Pins complete T-reference tables and 30fps canonical motion; source round-trip is separate from retarget quality."]})
        return 0
    parser = Parser(description=__doc__)
    for key in ("config", "engine", "project", "out-dir"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--emit-round-trip", action="store_true")
    parser.add_argument("--import-fbx", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = validate(json.loads(Path(args.config).read_text()))
        for row in config["sequences"]:
            if hashlib.sha256(Path(row["source"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("source hash mismatch: " + row["name"])
        fingerprints = {Path(ac.__file__): hashlib.sha256(Path(ac.__file__).read_bytes()).hexdigest(),
                        Path(__file__): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        out = Path(args.out_dir)
        run = run_editor(EDITOR, {"tools": str(RIG_CONVERT), "recipe": config,
                                 "emit_round_trip": args.emit_round_trip, "import_fbx": args.import_fbx},
                         engine=args.engine, project=args.project, work_root=str(out / "runs"),
                         logname="anim-normalize-ue.log", timeout=1800)
        result = json.loads(Path(run.result_path).read_text())
        for row in config["sequences"]:
            if hashlib.sha256(Path(row["source"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("source changed during normalization; publication refused: " + row["name"])
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != sha for path, sha in fingerprints.items()):
            raise ValueError("normalization code changed during the editor run; publication refused")
        if result["errors"]:
            emit({"error": result["errors"], "receipt": run.receipt_path, "help": ["Inspect result.json; no profiles/packets published."]})
            return 1
        outputs = {}
        for name, row in result["profiles"].items():
            outputs[name + ".profile.json"] = ac.encode(row["profile"])
        for name, row in result["sequences"].items():
            outputs[name + ".animation.json"] = ac.encode(row["packet"])
        manifest = {"recipe_sha256": ac.digest(config), "module_sha256": fingerprints[Path(ac.__file__)],
                    "recipe_code_sha256": fingerprints[Path(__file__)],
                    "outputs": {n: hashlib.sha256(b).hexdigest() for n, b in outputs.items()}}
        outputs["manifest.json"] = ac.encode(manifest)
        # All collisions, including the manifest, precede artifact publication.
        for name, raw in outputs.items():
            path = out / name
            if path.is_symlink() or (path.exists() and path.read_bytes() != raw):
                raise ValueError("different-existing/symlink output refused: " + name)
        for name, raw in outputs.items():
            publish(out / name, raw)
        emit({"verdict": "PASS", "scope": ("native extraction, canonical samples and emitted runtime Compressed poses; Blender/retarget require separate checks"
                                            if args.emit_round_trip else "native extraction and reversible canonical samples; emitted world artifacts/retarget not yet checked"),
              "outputs": len(outputs), "receipt": run.receipt_path, "help": ["Verify both actual world adapters before publishing runtime animations."]})
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        emit({"error": str(exc), "help": ["Check authored profile/source pins and the retained editor result."]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
