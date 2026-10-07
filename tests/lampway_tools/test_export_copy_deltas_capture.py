# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Published diagnostic returns bounded copy deltas, never export acceptance."""
import json
from pathlib import Path

from blender_run import run_script

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/lampway/capture_export_copy_deltas.py'
PRE = r'''
import bpy, json, runpy
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
import addon_utils
addon_utils.enable('io_scene_fbx',default_set=False)
ns=runpy.run_path(SCRIPT_PATH)
capture=ns['capture'];Refused=ns['CaptureRefused']
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
data=bpy.data.armatures.new('synthetic_data');arm=bpy.data.objects.new('synthetic_arm',data)
scene.collection.objects.link(arm);arm.select_set(True);bpy.context.view_layer.objects.active=arm
bpy.ops.object.mode_set(mode='EDIT')
root=data.edit_bones.new('root');root.head=(0,0,0);root.tail=(0,.3,0)
for i,name in enumerate(ns['SELECTED']):
    bone=data.edit_bones.new(name);bone.head=(.23,.63,1.53)
    length=.00001 if i%2 else .0001
    bone.tail=bone.head+Vector((.3,.6,.7)).normalized()*length;bone.roll=1.872;bone.parent=root
bpy.ops.object.mode_set(mode='OBJECT')
arm.location.x=.01;arm.keyframe_insert('location',frame=1)
bpy.context.view_layer.update()
'''.replace('SCRIPT_PATH', json.dumps(str(SCRIPT)))


def test_capture_numeric_rows_and_bounded_schema():
    run=run_script(PRE+r'''
result=capture(arm.name)
assert result['source_scene_sha256_before']==result['source_scene_sha256_after']
assert result['source_scene_unchanged'] and result['diagnostic_only']
assert result['schema_version']==1
assert len(result['rows'])==8
assert result['bars']=={'position_cm':.01,'rotation_deg':.01,'scale':.0001}
assert set(result)=={'schema_version','diagnostic_only','candidate','scope','tool_source_sha256','source_scene_sha256_before','source_scene_sha256_after','source_scene_unchanged','recipe_sha256','bars','copy_representation','rows'}
for row in result['rows']:
    assert set(row)=={'bone','position_cm','rotation_deg','scale','source_length_m','source_head_magnitude_m','copy_length_cm'}
    assert row['bone'] in ns['SELECTED']
    assert row['position_cm']<.01 and row['scale']<.0001
    assert row['source_length_m']>0 and row['source_head_magnitude_m']>1
rotations=[r['rotation_deg'] for r in result['rows']]
assert .02<min(rotations)<.1 and .2<max(rotations)<2.
assert len(json.dumps(result))<6500
assert 'synthetic_arm' not in json.dumps(result)
assert 'matrix' not in json.dumps(result).lower()
print('RESULT '+json.dumps(result))
''')
    assert run.rc==0,run.out
    assert len(run.results[0]['rows'])==8


def test_capture_refusals_are_sanitized_and_restore_source():
    run=run_script(PRE+r'''
from contextlib import contextmanager
from unittest.mock import patch
SPACE=ns['SPACE'];state=ns['_state'];sha=ns['_sha']
before=sha(state(arm,[]));failures=[]
with patch.dict(ns['EXPECTED'],{'rig_export.py':'0'*64}):
    try:capture(arm.name)
    except Refused as exc:failures.append(str(exc))
    else:assert False
assert sha(state(arm,[]))==before
original=SPACE.centimetre_copies
@contextmanager
def failed(*args,**kwargs):
    with original(*args,**kwargs) as prepared:
        yield prepared
        raise RuntimeError('private-owner-marker /private-owner-path/source.blend')
with patch.object(SPACE,'centimetre_copies',failed):
    try:capture(arm.name)
    except Refused as exc:failures.append(str(exc))
    else:assert False
assert sha(state(arm,[]))==before
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
arm.data.edit_bones.remove(arm.data.edit_bones[ns['SELECTED'][0]])
bpy.ops.object.mode_set(mode='OBJECT');bpy.context.view_layer.update()
missing_before=sha(state(arm,[]))
try:capture(arm.name)
except Refused as exc:failures.append(str(exc))
else:assert False
assert sha(state(arm,[]))==missing_before
for reason in failures:
    assert len(reason)<160 and 'private-owner' not in reason and 'synthetic_arm' not in reason and '/' not in reason
assert len(failures)==3
print('RESULT '+json.dumps({'refusals':failures,'source_restored':True}))
''')
    assert run.rc==0,run.out
    assert run.results[0]['source_restored']


def test_changed_state_refusal_suppresses_nested_private_traceback():
    run=run_script(PRE+r'''
import traceback
from contextlib import contextmanager
from unittest.mock import patch
SPACE=ns['SPACE'];state=ns['_state'];sha=ns['_sha']
before=sha(state(arm,[]));active=bpy.context.view_layer.objects.active
original=SPACE.centimetre_copies
@contextmanager
def changed_state(*args,**kwargs):
    with original(*args,**kwargs) as prepared:
        yield prepared
    # Deliberate corruption after copy cleanup; this control cannot claim preservation.
    bpy.context.view_layer.objects.active=None
    raise RuntimeError('nested-private-marker /fake-private-path/source.blend')
try:
    with patch.object(SPACE,'centimetre_copies',changed_state):
        try:capture(arm.name)
        except Refused as exc:
            reason=str(exc)
            rendered=''.join(traceback.format_exception(exc))
        else:assert False
    assert 'Source or scene state changed' in reason
    assert sha(state(arm,[]))!=before
    assert 'nested-private-marker' not in rendered
    assert '/fake-private-path' not in rendered
finally:
    bpy.context.view_layer.objects.active=active
    bpy.context.view_layer.update()
assert sha(state(arm,[]))==before
print('RESULT '+json.dumps({'changed_state_detected':True,'test_cleanup_restored':True}))
''')
    assert run.rc==0,run.out
    assert run.results[0]['changed_state_detected']
