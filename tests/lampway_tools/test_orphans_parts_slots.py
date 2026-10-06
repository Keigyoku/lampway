# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The PIECE_PIPELINE known gap 'one material per piece; the parts are not material slots' (STATUS O32): the piece's material is split into one slot per part
(or per material class), each slot a copy of the piece's material sharing its images, faces assigned from the owner map; on a COPY. REAL binary."""

import json

from features_support import run

PIECE = '''
ob = boxes("chest", [((0, 0, 1.0), (0.5, 0.3, 0.6)), ((-0.4, 0, 1.25), (0.25, 0.25, 0.15)), ((0.4, 0, 1.25), (0.25, 0.25, 0.15))])
own = np.array([0] * 6 + [1] * 6 + [2] * 6, dtype=np.int64)
a = ob.data.attributes.new("part", "INT", "FACE"); a.data.foreach_set("value", own)
img = bpy.data.images.new("atlas", 8, 8)
mat = bpy.data.materials.new("chest_tex"); mat.use_nodes = True
tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
ob.data.materials.append(mat)
json.dump({"parts": {"cuirass": {"class": "metal"}, "pauldron_l": {"class": "leather"}, "pauldron_r": {"class": "leather"}}}, open(os.path.join(root, "recipe.json"), "w"))
def slots(name):
    o = bpy.data.objects[name]
    return {"names": [m.name for m in o.data.materials], "idx": [p.material_index for p in o.data.polygons],
            "images": sorted({n.image.name for m in o.data.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE"})}
'''


def _go(tmp_path, body):
    r = run(tmp_path, PIECE + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_each_part_becomes_a_slot_sharing_the_images_on_a_copy(tmp_path):
    res = _go(tmp_path, '''
r = call("parts_material_slots", object="chest", recipe="recipe.json")
print("RESULT", json.dumps({"r": r, "copy": slots(r["object"]) if r.get("ok") else None, "src": slots("chest")}))
''')
    r, copy, src = res["r"], res["copy"], res["src"]
    assert r["ok"] is True and r["object"] == "chest_slots" and r["by"] == "part", r
    assert copy["names"] == ["chest_tex_cuirass", "chest_tex_pauldron_l", "chest_tex_pauldron_r"], copy
    assert copy["idx"] == [0] * 6 + [1] * 6 + [2] * 6 and copy["images"] == ["atlas"], copy
    assert src["names"] == ["chest_tex"] and set(src["idx"]) == {0}, "the source keeps its one material"


def test_slots_by_material_class_merge_parts_of_one_class(tmp_path):
    res = _go(tmp_path, '''
r = call("parts_material_slots", object="chest", recipe="recipe.json", by="class")
print("RESULT", json.dumps({"r": r, "copy": slots(r["object"])}))
''')
    assert res["copy"]["names"] == ["chest_tex_metal", "chest_tex_leather"] and res["copy"]["idx"] == [0] * 6 + [1] * 12, res


def test_refusals(tmp_path):
    res = _go(tmp_path, '''
one = boxes("one", [((3, 0, 1), (0.3, 0.3, 0.3))])
print("RESULT", json.dumps({"noparts": call("parts_material_slots", object="one", recipe="recipe.json"),
                            "by": call("parts_material_slots", object="chest", recipe="recipe.json", by="colour")}))
''')
    assert res["noparts"]["ok"] is False and "part" in res["noparts"]["error"], res
    assert res["by"]["ok"] is False and "part | class" in res["by"]["error"], res
