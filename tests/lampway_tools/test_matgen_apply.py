# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""MatGen auto-apply: the agent tool's add_to_layer_stack / apply_to_object_names. A generated material lands in the library AND
is applied to the named objects when asked: onto the active Mixar Paint layer stack when one exists, otherwise as the object's
surface material (a Group node of the generated node group into the Material Output). REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

SCRIPT = ("import bpy\\n"
          "g = bpy.data.node_groups.new('LW_TestMat', 'ShaderNodeTree')\\n"
          "g.interface.new_socket('Shader', in_out='OUTPUT', socket_type='NodeSocketShader')\\n"
          "o = g.nodes.new('NodeGroupOutput'); b = g.nodes.new('ShaderNodeBsdfPrincipled')\\n"
          "g.links.new(b.outputs['BSDF'], o.inputs[0])\\n")

BODY = '''
import bpy, json
from mixar.modules.paint.procedural_materials import matgen_queue as Q, material_registry as R, matgen_persistence as P
P.save_material = lambda m: m
Q._post = lambda path, body: {"material_id": "matgen_t1", "name": "Test Mat", "node_group_name": "LW_TestMat", "script": "%s", "description": "t", "category": "ai_generated"}
Q._run_in_thread = lambda fn: fn()
Q._on_main_thread = lambda fn: fn()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
import bmesh
def cube(name):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob
a, b = cube("a"), cube("b")
%s
''' % (SCRIPT, "%s")


def test_the_generated_material_is_applied_to_the_named_objects_as_a_group_node_surface():
    r = run_script(BODY % '''
job = Q.enqueue_matgen_job(prompt="test", apply_to_object_names=["a", "b"], layer_name="Test layer")
def info(ob):
    m = ob.data.materials[0] if ob.data.materials else None
    nodes = [n.bl_idname for n in m.node_tree.nodes] if m else []
    grp = [n.node_tree.name for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeGroup"] if m else []
    out = next((n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None) if m else None
    linked = bool(out and out.inputs["Surface"].links and out.inputs["Surface"].links[0].from_node.bl_idname == "ShaderNodeGroup")
    return {"n": len(ob.data.materials), "groups": grp, "linked": linked}
print("RESULT", json.dumps({"state": job.state.value, "applied": getattr(job, "applied", None), "a": info(a), "b": info(b),
                            "status": getattr(bpy.context.window_manager, "mixar_matgen_status", "headless: the paint panel's properties are not registered")}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["state"] == "done" and sorted(out["applied"]) == ["a", "b"]
    for k in ("a", "b"):
        assert out[k] == {"n": 1, "groups": ["LW_TestMat"], "linked": True}, out[k]
    assert out["status"].startswith(("done:", "headless"))


def test_without_targets_nothing_is_applied_and_a_missing_object_is_reported_not_raised():
    r = run_script(BODY % '''
j1 = Q.enqueue_matgen_job(prompt="one")
Q._in_flight.clear()
j2 = Q.enqueue_matgen_job(prompt="two", apply_to_object_names=["a", "ghost"])
print("RESULT", json.dumps({"a_mats": len(a.data.materials), "j1": getattr(j1, "applied", None), "j2": getattr(j2, "applied", None),
                            "missing": getattr(j2, "apply_missing", None), "state": j2.state.value}))
''')
    out = r.results[0]
    assert out["j1"] in (None, []) and out["j2"] == ["a"] and out["missing"] == ["ghost"] and out["state"] == "done"
