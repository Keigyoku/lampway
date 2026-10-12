# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual writer output is inspected without importing or evaluating the FBX."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one


def test_native_cm_recipe_exposes_container_scale_and_preserves_scene(tmp_path):
    diagnostic = Path(__file__).parents[2] / "scripts/lampway/diagnose_fbx_bind.py"
    result = one(go(tmp_path, '''
import runpy,hashlib
from mixar.modules.lampway_tools.features.rig_export import RECIPES
rig=armature(name="synthetic_container")
mesh=sphere("synthetic_mesh",subdiv=1)
group=mesh.vertex_groups.new(name="root")
group.add(list(range(len(mesh.data.vertices))),1.0,"REPLACE")
mod=mesh.modifiers.new("Armature","ARMATURE");mod.object=rig
recipe=json.loads((RECIPES/"cm_native_blender_convention.json").read_text())["exporter"]
recipe["object_types"]=set(recipe["object_types"])
bpy.context.scene.unit_settings.scale_length=1.0
for obj in bpy.context.view_layer.objects:obj.select_set(True)
bpy.context.view_layer.objects.active=rig
path=os.path.join(root,"synthetic.fbx")
bpy.ops.export_scene.fbx(filepath=path,use_selection=True,bake_anim=False,**recipe)
def scene_state():
 return {"objects":[(obj.name,obj.as_pointer(),[list(row) for row in obj.matrix_world],obj.select_get()) for obj in bpy.data.objects],
  "bones":[(bone.name,[list(row) for row in bone.matrix_local]) for bone in rig.data.bones],
  "counts":[len(bpy.data.meshes),len(bpy.data.armatures)],"active":bpy.context.view_layer.objects.active.name}
before=scene_state();original=hashlib.sha256(open(path,"rb").read()).hexdigest()
diagnostic=runpy.run_path(os.environ["FBX_DIAGNOSTIC_SCRIPT"])
report=diagnostic["diagnose"](path)
output=os.path.join(root,"private_diagnostic.json")
diagnostic["write_exclusive"](output,report)
print("RESULT",json.dumps({"counts":report["counts"],"usf":report["global_settings"]["UnitScaleFactor"]["values"],
 "scene_unchanged":before==scene_state(),"source_unchanged":original==hashlib.sha256(open(path,"rb").read()).hexdigest(),
 "private_mode":os.stat(output).st_mode&0o777}))
''', env={"FBX_DIAGNOSTIC_SCRIPT": str(diagnostic)}))
    assert result["counts"]["limb_nodes"] == 1
    assert result["counts"]["nonunit_scale_ancestors_of_limb_nodes"] == 1
    assert result["counts"]["poses"] >= 1 and result["counts"]["clusters"] == 1
    assert result["usf"] == [1.0]
    assert result["scene_unchanged"] and result["source_unchanged"]
    assert result["private_mode"] == 0o600
