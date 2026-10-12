# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Readonly owner fixture replay; input restoration is external to this suite."""
import json
import os
from pathlib import Path

import pytest

from blender_run import run_script


def test_actual_neck_auto_import_cleanup_and_named_skin_quality():
    root = Path(os.environ.get("LAMPWAY_ANIMATION_AUDIT_ASSETS", "/nonexistent"))
    scene = root / "assets/rig-animation-saved-result/rigged-suite.mixar"
    walking = root / "assets/walking-animation-input/inputs/walking.glb"
    preset = root / "fix-material/suite-evidence/anim/presets/SuiteMeshy.json"
    if not all(p.is_file() for p in (scene, walking, preset)):
        pytest.skip("set LAMPWAY_ANIMATION_AUDIT_ASSETS to the restored private audit root")
    script = '''
import bpy,json,tempfile,shutil,os
from mixar.modules.lampway_tools import api
root=tempfile.mkdtemp(prefix='animation-audit-')
api.settings_set(project_root=root)
shutil.copyfile(WALKING,os.path.join(root,'walking.glb'))
before=(set(bpy.data.objects),set(bpy.data.actions),set(bpy.data.collections))
auto=api.animation_retarget('walking.glb','root',mapping='auto',dry_run=True)
clean=before==(set(bpy.data.objects),set(bpy.data.actions),set(bpy.data.collections))
src=bpy.data.objects['target_character']
bpy.context.scene.frame_set(13)
def snapshot():
    return {'action':src.animation_data.action.name,'slot':src.animation_data.action_slot.identifier,'frame':bpy.context.scene.frame_current,
            'pose':[[float(x) for row in b.matrix_basis for x in row] for b in src.pose.bones]}
prior=snapshot()
out=api.animation_retarget(src.name,'Suite_Warrior_Game',action='Walking',mapping=json.load(open(PRESET)),root_motion='in_place',frame_range=[0,26],sample_frames=4,name='Audit_Walk',check_objects=['Warrior_Suite_Warrior_Conformed'])
print('RESULT '+json.dumps({'auto':auto,'clean':clean,'out':out,'source_unchanged':prior==snapshot()}))
'''.replace("WALKING", repr(str(walking))).replace("PRESET", repr(str(preset)))
    r = run_script(script, scene=scene, timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[-1]
    assert d["auto"]["ok"] and d["auto"]["dry_run"] and d["clean"], d
    assert d["out"]["ok"] and d["source_unchanged"], d
    assert d["out"]["metrics"]["max_world_angle_error_deg"] <= 0.01, d
    assert not d["out"]["quality"]["accepted"]
    assert d["out"]["quality"]["foot_slide"]["status"] == "unmeasured_world_contact"
    assert {"spine_04", "spine_05", "neck_02"} <= set(d["out"]["quality"]["unmapped_weighted_target"]["Warrior_Suite_Warrior_Conformed"])
    assert any("Inspect skin" in w for w in d["out"]["warnings"])
    evidence = os.environ.get("LAMPWAY_ANIMATION_AUDIT_RECEIPT")
    if evidence:
        Path(evidence).write_text(json.dumps(d, indent=2))
