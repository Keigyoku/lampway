# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only owner-scene diagnosis: call capture(armature_name) on source-hash-pinned tools.
No imports, exports, saves, source geometry changes, or unbounded frame output.
Disposable copies use the existing canonical context, restoring IDs/selection.
"""
import hashlib
import json
from pathlib import Path
import bpy
from mixar.modules.lampway_tools.features import rig_export as RE
from mixar.modules.lampway_tools.features import rig_export_space as SPACE
from mixar.modules.lampway_tools.features import rig_tools as RT
from mixar.modules.lampway_tools.rig_tools import core as RC

EXPECTED = {'rig_export.py': 'd713b22259557cf41897fa425fa42e5ef45c8fbcc991a142c4db7fae817d2324', 'rig_export_space.py': '9bb3c077bde9591eb30b8c003289a63e738c7f19869ad299f5ef72534d47c847'}
SELECTED = ('upperarm_twistCor_01_r','thigh_twistCor_01_l','thigh_twist_01_l',
            'upperarm_twist_01_r','calf_twistCor_02_r','calf_twist_02_r',
            'calf_twist_02_l','calf_twistCor_02_l')


def _sha(value):
    return hashlib.sha256(json.dumps(value,allow_nan=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _state(arm, meshes):
    scene=bpy.context.scene
    return {'units':[scene.unit_settings.system,scene.unit_settings.scale_length],
            'ids':[(kind,[(item.name,item.as_pointer()) for item in getattr(bpy.data,kind)])
                   for kind in ('objects','armatures','meshes','actions','shape_keys')],
            'selection':[ob.name for ob in bpy.context.selected_objects],
            'active':getattr(bpy.context.view_layer.objects.active,'name',None),
            'arm_world':[list(row) for row in arm.matrix_world],
            'rest':[(b.name,list(b.head_local),list(b.tail_local),[list(row) for row in b.matrix_local],b.parent.name if b.parent else None)
                    for b in arm.data.bones],
            'pose':[(b.name,[list(row) for row in b.matrix_basis]) for b in arm.pose.bones],
            'mesh':[(ob.name,[list(row) for row in ob.matrix_world],[list(v.co) for v in ob.data.vertices],
                     [[(g.group,g.weight) for g in v.groups] for v in ob.data.vertices],
                     [(key.name,[list(v.co) for v in key.data]) for key in ob.data.shape_keys.key_blocks] if ob.data.shape_keys else []) for ob in meshes],
            'actions':[(action.name,[(fc.data_path,fc.array_index,[(list(k.co),list(k.handle_left),list(k.handle_right)) for k in fc.keyframe_points])
                                    for fc in RT._fcurves(action)]) for action in bpy.data.actions]}


def capture(armature_name):
    """Return eight derived rows only; refuse with a sanitized reason on failure."""
    try:
        return _capture(armature_name)
    except CaptureRefused as exc:
        raise exc from None
    except Exception:
        raise CaptureRefused("Copy diagnostic refused; check the exact overlay and supported source dependencies") from None


class CaptureRefused(ValueError):
    """A bounded refusal that never repeats owner names, paths or raw values."""


def _capture(armature_name):
    for module in (RE,SPACE):
        filename=Path(module.__file__).name
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()!=EXPECTED[filename]:
            raise CaptureRefused('Capture requires the source-hash-pinned exporter Python overlay')
    arm=bpy.data.objects.get(armature_name)
    if arm is None or arm.type!='ARMATURE':raise CaptureRefused('Pass the actual caller-selected armature name')
    missing=[name for name in SELECTED if name not in arm.data.bones]
    if missing:raise CaptureRefused('Selected twist rows are missing from the caller-selected armature')
    meshes=[ob for ob in bpy.data.objects if ob.type=='MESH' and any(m.type=='ARMATURE' and m.object==arm for m in ob.modifiers)]
    bpy.context.view_layer.update()
    before=_sha(_state(arm,meshes))
    reference=RE._table(arm,set(SELECTED))
    doc,recipe_path=RE._recipe('cm_native_ue_axes','')
    exporter=dict(doc['exporter']);exporter['object_types']=set(exporter['object_types'])
    try:
        with SPACE.centimetre_copies(arm,meshes,None,exporter) as copied:
            table=RE._table(copied['armature'],set(SELECTED),representation={'translation_to_metres':.01,'scale_divisor':1.})
            rows=RC.readback_rows(reference,table)
            measurements=[{**row,'source_length_m':arm.data.bones[row['bone']].length,
                           'source_head_magnitude_m':arm.data.bones[row['bone']].head_local.length,
                           'copy_length_cm':copied['armature'].data.bones[row['bone']].length}
                          for row in rows['rows']]
            receipt=copied['receipt']
    finally:
        after=_sha(_state(arm,meshes))
        if before!=after:
            raise CaptureRefused('Source or scene state changed during disposable-copy capture')
    return {'schema_version':1,'diagnostic_only':True,'candidate':'source-hash-pinned',
            'scope':'Copy-time diagnosis only; no writer/import or engine acceptance',
            'tool_source_sha256':dict(EXPECTED),'source_scene_sha256_before':before,
            'source_scene_sha256_after':after,'source_scene_unchanged':True,
            'recipe_sha256':hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
            'bars':rows['bars'],'copy_representation':receipt,'rows':measurements}
