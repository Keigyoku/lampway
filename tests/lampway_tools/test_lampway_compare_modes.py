# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 11 (mrmak/05 section 6.5) in the real binary: Textured and the data modes show each model's own materials on a
normalised copy in the scratch scene (the user's scene untouched); Base colour shows the base map through an emission, Normal
map the map itself or, when none was baked, the flat (0.5, 0.5, 1.0) that makes the absence the finding; ORM the green and
blue channels; Textured restores the originals without importing again."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_wave2b_model_compare import go  # noqa: E402

BODY = '''
from mixar.modules.lampway_tools.ui import compare as CMP
img = bpy.data.images.new("base_px", 4, 4)
img.pixels = [0.8, 0.2, 0.1, 1.0] * 16
img.filepath_raw = os.path.join(root, "base_px.png"); img.file_format = "PNG"; img.save()
def textured_sphere(path, normal=False):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.5)
    me = bpy.data.meshes.new("tex_exp"); bm.to_mesh(me); bm.free()
    me.uv_layers.new(name="UVMap")
    mat = bpy.data.materials.new("m"); mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if normal:
        n = mat.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img
        nm = mat.node_tree.nodes.new("ShaderNodeNormalMap")
        mat.node_tree.links.new(n.outputs["Color"], nm.inputs["Color"]); mat.node_tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    me.materials.append(mat)
    ob = bpy.data.objects.new("tex_exp", me); link(ob)
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB")
    bpy.data.objects.remove(ob)
textured_sphere(os.path.join(root, "flat.glb"))
textured_sphere(os.path.join(root, "bumpy.glb"), normal=True)
user_objects = sorted(o.name for o in bpy.context.scene.objects)
call("model_compare", action="build", set={"id": "dm", "piece": "P", "models": [{"file": "flat.glb"}, {"file": "bumpy.glb"}]})
CMP.load_set("dm", "P", root)
def emission_source(ob):
    mat = ob.material_slots[0].material
    out = next(n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    shader = out.inputs["Surface"].links[0].from_node
    if shader.type != "EMISSION":
        return shader.type, None
    col = shader.inputs["Color"]
    if not col.links:
        return "EMISSION", [round(x, 3) for x in col.default_value[:3]]
    node = col.links[0].from_node
    return "EMISSION", node.type
res = {}
for mode in ("5", "6", "7", "4"):
    copies = CMP.ensure_textured()
    CMP.apply_materials(mode)
    res[mode] = {str(i): [emission_source(o) for o in obs] for i, obs in copies.items()}
again = CMP.ensure_textured()
print("RESULT", json.dumps({"res": res, "same": sorted(o.name for obs in again.values() for o in obs) == sorted(o.name for obs in copies.values() for o in obs),
                            "user_untouched": sorted(o.name for o in bpy.context.scene.objects) == user_objects,
                            "in_scratch": all(o.users_scene and o.users_scene[0].name == "LW_Compare" for obs in again.values() for o in obs)}))
'''


def test_data_modes_show_the_maps_and_a_missing_normal_map_is_flat(tmp_path):
    r = go(tmp_path, BODY)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    res = d["res"]
    flat, bumpy = "0", "1"
    assert res["5"][flat][0] == ["EMISSION", "TEX_IMAGE"], res["5"]
    assert res["6"][flat][0] == ["EMISSION", [0.5, 0.5, 1.0]], "no normal map baked: the flat colour is the finding"
    assert res["6"][bumpy][0] == ["EMISSION", "TEX_IMAGE"]
    assert res["7"][flat][0][0] == "EMISSION"
    assert res["4"][flat][0][0] == "BSDF_PRINCIPLED", "Textured restores the originals"
    assert d["same"] and d["user_untouched"] and d["in_scratch"]
