# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The live material toggle that uses the projected albedo as base colour (the shelf's v3_colour_atlas.png from the mesh-paint
projection is a usable albedo; the captain built the toggle in his live material textured_chest_p17_albedo, nodes labelled
'AB:'). A copy of the textured material gets an image node on the UV map and a Mix between the original base colour and the
albedo, driven by one Value node; the original material is untouched. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, json, os
from mixar.modules.lampway_tools import albedo as AB
work = WORK
im = bpy.data.images.new("v3_colour_atlas.png", 8, 8); im.filepath_raw = work + "/v3_colour_atlas.png"; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
mat = bpy.data.materials.new("textured_chest_p17"); mat.use_nodes = True; nt = mat.node_tree
bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
rgb = nt.nodes.new("ShaderNodeRGB"); rgb.outputs[0].default_value = (0.2, 0.1, 0.05, 1); nt.links.new(rgb.outputs[0], bs.inputs["Base Color"])
'''


def run(tmp_path, body):
    return run_script(PRE.replace("WORK", repr(str(tmp_path))) + body)


def test_the_toggle_is_built_on_a_copy_and_the_original_is_untouched(tmp_path):
    r = run(tmp_path, '''
res = AB.apply("textured_chest_p17", work + "/v3_colour_atlas.png")
new = bpy.data.materials[res["material"]]
ab = [n for n in new.node_tree.nodes if n.label.startswith("AB:")]
bs = next(n for n in new.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
mix = bs.inputs["Base Color"].links[0].from_node
orig_bs = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
print("RESULT", json.dumps({"res": res, "n_ab": len(ab), "labels": sorted(n.label for n in ab), "base_from": mix.label,
    "a_from": mix.inputs[6].links[0].from_node.type if mix.inputs[6].links else None,
    "b_from": mix.inputs[7].links[0].from_node.label if mix.inputs[7].links else None,
    "factor": round(mix.inputs[0].links[0].from_node.outputs[0].default_value, 2),
    "orig_untouched": orig_bs.inputs["Base Color"].links[0].from_node.type, "orig_ab": sum(n.label.startswith("AB:") for n in mat.node_tree.nodes),
    "cs": next(n for n in ab if n.type == "TEX_IMAGE").image.colorspace_settings.name}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["res"]["material"] == "textured_chest_p17_albedo" and res["res"]["on"] is True
    assert res["labels"] == ["AB: albedo", "AB: mix", "AB: use albedo", "AB: uv"]
    assert res["base_from"] == "AB: mix" and res["a_from"] == "RGB" and res["b_from"] == "AB: albedo" and res["factor"] == 1.0
    assert res["orig_untouched"] == "RGB" and res["orig_ab"] == 0 and res["cs"] == "sRGB"


def test_set_albedo_flips_between_the_textured_look_and_the_albedo(tmp_path):
    r = run(tmp_path, '''
name = AB.apply("textured_chest_p17", work + "/v3_colour_atlas.png")["material"]
AB.set_albedo(name, False)
off = next(n for n in bpy.data.materials[name].node_tree.nodes if n.label == "AB: use albedo").outputs[0].default_value
AB.set_albedo(name, True)
on = next(n for n in bpy.data.materials[name].node_tree.nodes if n.label == "AB: use albedo").outputs[0].default_value
print("RESULT", json.dumps({"off": off, "on": on, "state": AB.state(name)}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results == [{"off": 0.0, "on": 1.0, "state": True}]


def test_applying_again_replaces_its_own_nodes_and_can_point_at_a_new_albedo(tmp_path):
    r = run(tmp_path, '''
im = bpy.data.images.new("second.png", 8, 8); im.filepath_raw = work + "/second.png"; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
a = AB.apply("textured_chest_p17", work + "/v3_colour_atlas.png")["material"]
b = AB.apply("textured_chest_p17", work + "/second.png")["material"]
nodes = bpy.data.materials[b].node_tree.nodes
img = next(n for n in nodes if n.label == "AB: albedo").image.filepath
print("RESULT", json.dumps({"same": a == b, "n_ab": sum(n.label.startswith("AB:") for n in nodes), "img": os.path.basename(img), "mats": sorted(m.name for m in bpy.data.materials if "albedo" in m.name)}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results == [{"same": True, "n_ab": 4, "img": "second.png", "mats": ["textured_chest_p17_albedo"]}]


def test_a_missing_albedo_image_or_material_is_refused(tmp_path):
    r = run(tmp_path, '''
out = []
for args in (("textured_chest_p17", work + "/nope.png"), ("no_such_material", work + "/v3_colour_atlas.png")):
    try:
        AB.apply(*args); out.append("no error")
    except (FileNotFoundError, LookupError) as e:
        out.append(type(e).__name__)
print("RESULT", json.dumps({"out": out, "made": [m.name for m in bpy.data.materials if "albedo" in m.name]}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results == [{"out": ["FileNotFoundError", "LookupError"], "made": []}]
