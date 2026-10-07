# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Default export follows measured normalized frames, keeping every readback bar."""
from test_rig_export_ue import run,CHAIN


def test_default_recipe_follows_measured_frames_and_preserves_corrective_roll(tmp_path):
    r=run(tmp_path,CHAIN+r'''
results={}
for mode in ('y','x'):
    arm=chain('same_unknown_name_'+mode,mode)
    bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
    helper=arm.data.edit_bones.new('upperarm_correctiveRoot_l');helper.head=J[1];helper.tail=Vector(J[1])+Vector((0,0,.04));helper.roll=math.radians(120);helper.parent=arm.data.edit_bones['b1']
    bpy.ops.object.mode_set(mode='OBJECT')
    call('rig_inspect',armature=arm.name)
    results[mode]=call('rig_export_ue',armature=arm.name,out='export/default_'+mode+'.fbx')
print('RESULT',json.dumps(results))
''',timeout=600)
    assert r.rc==0,r.out[-3000:]
    for mode,recipe in [('y','cm_native_blender_convention'),('x','cm_native_ue_axes')]:
        row=r.results[0][mode]
        assert row['ok'],row
        assert row['recipe']['name']==recipe
        assert row['recipe_selection']['requested']=='auto'
        assert row['recipe_selection']['measured_convention']==row['convention']
        assert row['readback']['over_tolerance']==[]
        assert row['readback']['bars']=={'position_cm':.01,'rotation_deg':.01,'scale':.0001}
        assert row['readback']['bones_compared']==6
