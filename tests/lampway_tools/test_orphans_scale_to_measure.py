# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scale_to_measure (specs/wiki/scale_to_measure.md): a piece at its measured real size, applied safely, never blindly on a skinned mesh or an armature, with the old
transform kept for a rollback. REAL binary."""

import json

from features_support import run


def _go(tmp_path, body):
    r = run(tmp_path, body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_scales_to_target_height(tmp_path):
    res = _go(tmp_path, '''
ob = boxes("chest", [((0, 0, 0.5), (0.4, 0.3, 1.0))]); canon("chest", scale="any")
r = call("scale_to_measure", object="chest", target={"axis": "z", "length_m": 0.62})
doc = json.loads(ob["lw_canon"])
from mixar.modules.lampway_tools import canon_asset as CA, canon_io
print("RESULT", json.dumps({"r": r, "dims": list(ob.dimensions), "scale": list(ob.scale), "state": doc["scale"],
                            "check": CA.check(doc, canon_io.facts(ob))}))
''')
    r = res["r"]
    assert r["ok"] is True and abs(r["factor"] - 0.62) < 1e-6 and r["applied"] is True, r
    assert abs(res["dims"][2] - 0.62) < 1e-5 and abs(res["dims"][0] - 0.248) < 1e-5, res
    assert all(abs(s - 1.0) < 1e-9 for s in res["scale"]), "applied: the scale is in the mesh"
    assert r["dimensions_before"][2] == 1.0 and abs(r["dimensions_after"][2] - 0.62) < 1e-5
    # the route to real scale: the scaled mesh is re-stamped canonical, its scale state real on the measured length (SCHEMA 3.1)
    assert res["state"]["state"] == "real" and res["state"]["evidence"]["method"] == "scale_to_measure" and res["check"] == [], res


def test_max_axis_and_reference_object(tmp_path):
    res = _go(tmp_path, '''
boxes("a", [((0, 0, 0), (2.0, 0.5, 0.5))])
boxes("ref", [((3, 0, 0), (0.1, 0.1, 0.9))])
boxes("b", [((5, 0, 0), (0.2, 0.2, 0.3))])
canon("a", "b", scale="any")
ra = call("scale_to_measure", object="a", target={"axis": "max", "length_m": 1.0}, apply=False)
rb = call("scale_to_measure", object="b", target={"axis": "z"}, reference_object="ref")
print("RESULT", json.dumps({"ra": ra, "rb": rb, "a": list(bpy.data.objects["a"].scale), "b": list(bpy.data.objects["b"].dimensions)}))
''')
    assert res["ra"]["ok"] and abs(res["ra"]["factor"] - 0.5) < 1e-9 and res["ra"]["applied"] is False and abs(res["a"][0] - 0.5) < 1e-9, res
    assert res["rb"]["ok"] and abs(res["b"][2] - 0.9) < 1e-5, res


def test_skinned_mesh_apply_refused(tmp_path):
    res = _go(tmp_path, '''
ob = boxes("arm_plate", [((0, 0, 1), (0.1, 0.1, 0.3))])
arm = bpy.data.armatures.new("rig"); rig = link(bpy.data.objects.new("rig", arm))
canon("arm_plate", scale="any")
mod = ob.modifiers.new("Armature", "ARMATURE"); mod.object = rig
out = {"mesh": call("scale_to_measure", object="arm_plate", target={"axis": "z", "length_m": 0.5}),
       "armature": call("scale_to_measure", object="rig", target={"axis": "z", "length_m": 1.8}),
       "scale": list(ob.scale), "dims": list(ob.dimensions)}
out["no_apply"] = call("scale_to_measure", object="rig", target={"axis": "max", "length_m": 1.8}, apply=False)
print("RESULT", json.dumps(out))
''')
    assert res["mesh"]["ok"] is False and "breaks the rig" in res["mesh"]["error"], res
    # an armature is not a mesh: the door refuses it before the tool's own rig rule
    assert res["armature"]["ok"] is False and "normalize first" in res["armature"]["error"], res
    assert res["scale"] == [1.0, 1.0, 1.0], "a refusal changes nothing"


def test_prev_scale_allows_rollback(tmp_path):
    res = _go(tmp_path, '''
ob = boxes("helm", [((0, 0, 1.7), (0.25, 0.3, 0.3))]); canon("helm", scale="any")
stamp0 = ob["lw_canon"]
before = [round(v, 6) for v in ob.dimensions]
r = call("scale_to_measure", object="helm", target={"axis": "z", "length_m": 0.32})
mid = [round(v, 6) for v in ob.dimensions]
prev = json.loads(ob["lw_prev_scale"])
back = call("scale_to_measure", object="helm", rollback=True)
print("RESULT", json.dumps({"before": before, "mid": mid, "after": [round(v, 6) for v in ob.dimensions], "scale": list(ob.scale), "prev": prev, "back": back,
                            "stamp_restored": ob["lw_canon"] == stamp0}))
''')
    # a canonical input has its transform applied, so the previous scale is 1 and the rollback restores the mesh and its stamp
    assert res["prev"]["scale"] == [1.0, 1.0, 1.0] and res["mid"][2] == 0.32, res
    assert res["back"]["ok"] is True and res["after"] == res["before"] and res["scale"] == [1.0, 1.0, 1.0] and res["stamp_restored"], res


def test_length_bounds_shape_keys_and_unit_scale(tmp_path):
    res = _go(tmp_path, '''
ob = boxes("p", [((0, 0, 0), (1.0, 1.0, 1.0))]); canon("p", scale="any")
tiny = call("scale_to_measure", object="p", target={"axis": "z", "length_m": 0.0001})
q = boxes("q", [((3, 0, 0), (1.0, 1.0, 1.0))]); q.shape_key_add(name="Basis"); canon("q", scale="any")
keys = call("scale_to_measure", object="q", target={"axis": "z", "length_m": 0.5})
cm = call("scale_to_measure", object="p", target={"axis": "z", "length_m": 1.8}, unit_scale=0.01)
print("RESULT", json.dumps({"tiny": tiny, "keys": keys, "cm": cm, "dz": ob.dimensions.z}))
''')
    assert res["tiny"]["ok"] is False and "0.001..1000" in res["tiny"]["error"], res
    assert res["keys"]["ok"] is False and "shape keys" in res["keys"]["error"], res
    assert res["cm"]["ok"] is True and abs(res["dz"] - 180.0) < 1e-3 and res["cm"]["unit_scale"] == 0.01, res


def test_children_follow_or_keep_their_world_place(tmp_path):
    res = _go(tmp_path, '''
out = {}
for mode in ("include", "skip"):
    p = boxes("p_" + mode, [((0, 0, 0), (1.0, 1.0, 1.0))])
    canon(p.name, scale="any")
    c = boxes("c_" + mode, [((0, 0, 0), (0.2, 0.2, 0.2))]); c.location = (2.0, 0, 0); c.parent = p
    bpy.context.view_layer.update()
    call("scale_to_measure", object=p.name, target={"axis": "z", "length_m": 0.5}, children=mode)
    bpy.context.view_layer.update()
    out[mode] = {"x": round(c.matrix_world.translation.x, 6), "dz": round(c.dimensions.z * c.matrix_world.to_scale().z / c.scale.z, 6)}
print("RESULT", json.dumps(out))
''')
    assert res["include"]["x"] == 1.0 and res["include"]["dz"] == 0.1, res
    assert res["skip"]["x"] == 2.0 and res["skip"]["dz"] == 0.2, res
