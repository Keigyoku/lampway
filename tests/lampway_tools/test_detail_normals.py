# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Micro depth for a textured_atlas material without the relief map (the shelf's texlib/detail_normals.py): per-material
tiling DETAIL NORMALS box-projected in object space; metals take their ambientCG NormalGL maps, cloth and leather a small
bump from their colour's brightness; the per-texel masks blend them. Idempotent: its nodes are labelled 'DN:' and
replaced on a re-run; the relief bump stays in the chain (strength 0 = off). REAL binary, a synthetic material."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, json, os
from mixar.modules.lampway_tools import detail_normals as DN
work = WORK
acg = work + "/acg"
for d, f in (("Metal009", "Metal009_2K-PNG_NormalGL.png"), ("Metal048C", "Metal048C_2K-PNG_NormalGL.png")):
    os.makedirs(acg + "/" + d, exist_ok=True)
    im = bpy.data.images.new(f, 4, 4); im.filepath_raw = acg + "/" + d + "/" + f; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
mat = bpy.data.materials.new("textured_x"); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear(); N = nt.nodes; L = nt.links
out = N.new("ShaderNodeOutputMaterial"); bs = N.new("ShaderNodeBsdfPrincipled"); L.new(bs.outputs["BSDF"], out.inputs["Surface"])
tc = N.new("ShaderNodeTexCoord"); bump = N.new("ShaderNodeBump"); L.new(bump.outputs["Normal"], bs.inputs["Normal"])
def img(path, box=False):
    im = bpy.data.images.new(os.path.basename(path), 4, 4); im.filepath_raw = path; im.file_format = "PNG"; im.save()
    t = N.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(path)
    if box: t.projection = "BOX"
    return t
os.makedirs(work + "/tex", exist_ok=True)
for k in ("plate", "gold", "red", "linen", "leather"): img(work + "/tex/mask_%s.png" % k)
img(work + "/tex/Titan_Crimson_Cape_Lattice_BaseColor.png", box=True)
img(work + "/tex/Titan_Black_Linen_BaseColor.png", box=True)
'''


def run(tmp_path, body):
    return run_script(PRE.replace("WORK", repr(str(tmp_path))) + body)


def test_it_builds_a_blend_per_material_with_masks_and_feeds_the_bump(tmp_path):
    r = run(tmp_path, '''
res = DN.apply("textured_x", acg_dir=acg)
nt = bpy.data.materials["textured_x"].node_tree
dn = [n for n in nt.nodes if n.label.startswith("DN:")]
bump = next(n for n in nt.nodes if n.type == "BUMP")
print("RESULT", json.dumps({"res": res, "n": len(dn), "mixes": sum(n.type == "MIX" for n in dn), "bump_fed_by_dn": bump.inputs["Normal"].links[0].from_node.label.startswith("DN:")}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["res"]["layers"] == ["plate", "gold", "red", "linen"]            # leather: no colour tile in this material
    assert res["res"]["masks_found"] == ["gold", "leather", "linen", "plate", "red"]
    assert res["mixes"] == 4 and res["bump_fed_by_dn"] is True
    assert res["res"]["strengths"] == {"plate": 0.6, "gold": 0.45, "cloth": 0.25, "leather": 0.3}


def test_a_second_run_replaces_its_own_nodes(tmp_path):
    r = run(tmp_path, '''
DN.apply("textured_x", acg_dir=acg)
n1 = sum(n.label.startswith("DN:") for n in bpy.data.materials["textured_x"].node_tree.nodes)
DN.apply("textured_x", strengths={"plate": 0.9}, acg_dir=acg)
n2 = sum(n.label.startswith("DN:") for n in bpy.data.materials["textured_x"].node_tree.nodes)
nm = next(n for n in bpy.data.materials["textured_x"].node_tree.nodes if n.label == "DN:plate normal nm")
print("RESULT", json.dumps({"n1": n1, "n2": n2, "plate": round(nm.inputs["Strength"].default_value, 2)}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["n1"] == res["n2"] and res["plate"] == 0.9


def test_a_missing_normal_map_is_refused_naming_the_file(tmp_path):
    r = run(tmp_path, '''
try:
    DN.apply("textured_x", acg_dir=work + "/nowhere"); out = "no error"
except FileNotFoundError as e:
    out = str(e)
print("RESULT", json.dumps({"msg": out}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "Metal009_2K-PNG_NormalGL.png" in r.results[0]["msg"]
