# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_unwrap extensions (specs/mixar_docs/uv_unwrap.md) in the real binary: margin in pixels, a seam rule that hides seams from a direction, the requested texel density ENFORCED, the worst stretch reported
and located (checked against a hand-computed Jacobian), and a checker material. The original keeps its UVs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_UV = '''
def box(name="Box", size=(2.0, 2.0, 2.0), loc=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    return link(ob)
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_UV + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_margin_px_derives_margin_and_the_default_is_one_pixel_per_256(tmp_path):
    d = one(go(tmp_path, '''
box()
a = call("uv_unwrap", object="Box", method="angle", margin_px=4, texture_size=1024)
b = call("uv_unwrap", object="Box", method="angle", texture_size=2048)
print("RESULT", json.dumps({"a": a.get("margin_used"), "b": b.get("margin_used"), "ma": a.get("margin_px_used"), "mb": b.get("margin_px_used")}))
'''))
    assert abs(d["a"] - 4 / 1024) < 1e-9 and d["ma"] == 4
    assert abs(d["b"] - 8 / 2048) < 1e-9 and d["mb"] == 8                                                # 1 px per 256 px: 8 px at 2K


def test_a_texel_density_is_enforced_scaled_and_a_request_that_cannot_fit_is_refused(tmp_path):
    d = one(go(tmp_path, '''
box()
natural = call("uv_unwrap", object="Box", method="angle", texture_size=1024)
nat = natural["report"]["achieved_texel_density"]
want = nat * 0.5
res = call("uv_unwrap", object="Box", method="angle", texture_size=1024, texel_density=want)
toobig = call("uv_unwrap", object="Box", method="angle", texture_size=1024, texel_density=nat * 3)
print("RESULT", json.dumps({"nat": nat, "want": want, "got": res["report"]["achieved_texel_density"], "fit_max": res["report"]["uv_max"], "toobig": toobig}))
'''))
    assert abs(d["got"] - d["want"]) / d["want"] < 0.03 and max(d["fit_max"]) <= 1.0001
    assert d["toobig"]["ok"] is False and "cannot fit" in d["toobig"]["error"] and "raise texture_size or lower texel_density" in d["toobig"]["error"]


def test_the_seam_rule_hides_every_seam_from_the_front_while_still_unfolding_the_box(tmp_path):
    d = one(go(tmp_path, '''
box()
res = call("uv_unwrap", object="Box", seam_rule={"hide_from": "-Y"})
new = bpy.data.objects[res["object"]]
import bmesh as bm_
bm = bm_.new(); bm.from_mesh(new.data); bm.faces.ensure_lookup_table()
seams = [e for e in bm.edges if e.seam]
front_touching = [e for e in seams if any(f.normal.y < -0.5 for f in e.link_faces)]
print("RESULT", json.dumps({"res": res, "seams": len(seams), "front": len(front_touching), "islands": res["report"]["islands"], "overlap": res["report"]["overlap_fraction"], "method": res["method"]}))
'''))
    assert d["front"] == 0 and d["seams"] >= 7 and d["method"] == "angle" and d["res"]["report"]["seam_rule"]["visible_seam_edges"] == 0
    assert d["overlap"] < 0.01


def test_hide_from_options_unknown_values_are_refused_listing_them_and_the_other_directions_work(tmp_path):
    d = one(go(tmp_path, '''
box()
bad = call("uv_unwrap", object="Box", seam_rule={"hide_from": "sideways"})
top = call("uv_unwrap", object="Box", seam_rule={"hide_from": "top"})
print("RESULT", json.dumps({"bad": bad, "top": top["report"]["seam_rule"]}))
'''))
    assert d["bad"]["ok"] is False and "hide_from" in d["bad"]["error"] and "-Y" in d["bad"]["error"] and "top" in d["bad"]["error"]
    assert d["top"]["visible_seam_edges"] == 0


def test_worst_stretch_equals_the_hand_computed_jacobian_on_a_stretched_quad_and_is_located(tmp_path):
    d = one(go(tmp_path, '''
bm = bmesh.new()
v = [bm.verts.new(c) for c in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
bm.verts.index_update()
bm.faces.new([v[0], v[1], v[2]]); bm.faces.new([v[0], v[2], v[3]])
uvl = bm.loops.layers.uv.new("UVMap")
uvs = {0: (0.0, 0.0), 1: (0.5, 0.0), 2: (0.5, 0.25), 3: (0.0, 0.25)}                  # u stretched to 0.5, v to 0.25: s1 = 0.5, s2 = 0.25 on the unit square: angle stretch 2
for f in bm.faces:
    for l in f.loops:
        l[uvl].uv = uvs[l.vert.index]
me = bpy.data.meshes.new("Strip"); bm.to_mesh(me); bm.free()
ob = link(bpy.data.objects.new("Strip", me))
from mixar.modules.lampway_tools.features import uv as UV
ws = UV.worst_stretch(ob)
print("RESULT", json.dumps(ws))
'''))
    assert abs(d["angle"] - 2.0) < 1e-6 and d["face"] in (0, 1) and abs(d["area"] - 1.0) < 1e-6 and len(d["location"]) == 3


def test_a_checker_material_is_added_to_the_new_object_only_and_nonuniform_scale_is_refused_with_the_fix(tmp_path):
    d = one(go(tmp_path, '''
src = box()
res = call("uv_unwrap", object="Box", method="angle", checker=True)
new = bpy.data.objects[res["object"]]
mats = [m.name for m in new.data.materials]
img = [n.image.generated_type for m in new.data.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE"]
src_mats = [m.name for m in src.data.materials]
src.scale = (1, 1, 2)
bad = call("uv_unwrap", object="Box")
print("RESULT", json.dumps({"res": res, "mats": mats, "img": img, "src_mats": src_mats, "bad": bad}))
'''))
    assert d["res"]["checker_material"] in d["mats"] and d["img"] == ["UV_GRID"] and d["src_mats"] == []
    assert d["bad"]["ok"] is False and "apply scale first (lampway_scene_cleanup)" in d["bad"]["error"]
