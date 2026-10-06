# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""face_rig_validate (specs/wiki/face_rig_validate.md) in the real binary: shape-key coverage against the ARKit and viseme lists, a separate mouth interior, and the
wiki's six acceptance expressions MEASURED on the evaluated mesh (lip gap, brow asymmetry, teeth clearance), with every shape value restored."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

HEAD = '''
def quad(bm, c, w=0.02, d=0.01):
    vs = [bm.verts.new((c[0] + x, c[1] + y, c[2])) for x, y in ((-w, -d), (w, -d), (w, d), (-w, d))]
    bm.faces.new(vs)
    return vs
bm = bmesh.new()
parts = {"lip_upper": quad(bm, (0, -0.1, 0.01)), "lip_lower": quad(bm, (0, -0.1, -0.01)),
         "brow_l": quad(bm, (0.03, -0.09, 0.06), w=0.01), "brow_r": quad(bm, (-0.03, -0.09, 0.06), w=0.01)}
bm.verts.index_update()
ids = {k: [v.index for v in vs] for k, vs in parts.items()}
me = bpy.data.meshes.new("head"); bm.to_mesh(me); bm.free()
head = link(bpy.data.objects.new("head", me))
for k, vs in ids.items():
    head.vertex_groups.new(name=k).add(vs, 1.0, "REPLACE")
head.shape_key_add(name="Basis")
def key(name, moves):
    sk = head.shape_key_add(name=name, from_mix=False)
    for group, dz in moves:
        for i in ids[group]:
            sk.data[i].co.z += dz
    return sk
key("mouthClose", [("lip_lower", 0.02)])
key("jawOpen", [("lip_lower", -0.03)])
key("browOuterUpLeft", [("brow_l", 0.008)])
key("eyeBlinkLeft", []); key("eyeBlinkRight", [])
teeth = boxes("teeth", [((0, -0.05, 0.0), (0.06, 0.04, 0.03))])          # 2 cm behind the lips
'''


def test_lips_together_key_closes_the_gap_and_a_zero_key_gives_the_neutral_gap(tmp_path):
    d = one(go(tmp_path, HEAD + '''
head.data.shape_keys.key_blocks["browOuterUpLeft"].value = 0.3                    # a value the user left set: it must come back
values0 = [k.value for k in head.data.shape_keys.key_blocks]
res = call("face_rig_validate", object="head", shape_key_profile="arkit", teeth="teeth")
zero = call("face_rig_validate", object="head", shape_key_profile="arkit", teeth="teeth", poses=[{"name": "wide_zero", "keys": {"jawOpen": 0.0}}])
print("RESULT", json.dumps({"res": res, "zero": zero, "values": [k.value for k in head.data.shape_keys.key_blocks], "values0": values0}))
'''))
    res = d["res"]
    assert res["ok"], res
    ex = {e["name"]: e for e in res["expressions"]}
    assert set(ex) == {"neutral_blink", "asymmetric_brow", "wide_mouth", "lips_together", "teeth_tongue_clearance", "speech_line"}
    neutral = res["neutral"]["lip_gap_m"]
    assert abs(neutral - 0.02) < 1e-6
    assert ex["lips_together"]["measured"]["lip_gap_m"] < 1e-6 and ex["lips_together"]["pass"] is True
    assert ex["wide_mouth"]["measured"]["lip_gap_m"] > neutral and ex["wide_mouth"]["pass"] is True
    assert abs(ex["asymmetric_brow"]["measured"]["brow_asym_m"] - 0.008) < 1e-6 and ex["asymmetric_brow"]["pass"] is True
    assert abs(d["zero"]["expressions"][0]["measured"]["lip_gap_m"] - neutral) < 1e-9          # the falsifier: the wide key at 0 gives the neutral gap
    assert d["values"] == d["values0"] and 0.3 in [round(v, 3) for v in d["values"]]        # every shape value restored


def test_missing_arkit_keys_listed_and_visemes_counted_when_asked(tmp_path):
    d = one(go(tmp_path, HEAD + '''
a = call("face_rig_validate", object="head", shape_key_profile="arkit")
v = call("face_rig_validate", object="head", shape_key_profile="arkit+visemes")
key("custom_smirk", [])
x = call("face_rig_validate", object="head", shape_key_profile="arkit")
print("RESULT", json.dumps({"a": a["keys"], "v": v["keys"], "x": x["keys"]}))
'''))
    a, v = d["a"], d["v"]
    assert sorted(a["present"]) == ["browOuterUpLeft", "eyeBlinkLeft", "eyeBlinkRight", "jawOpen", "mouthClose"]
    assert len(a["missing"]) == 47 and "tongueOut" in a["missing"] and "mouthSmileLeft" in a["missing"] and a["expected"] == 52
    assert v["expected"] == 52 + 15 and len(v["missing"]) == 47 + 15 and "viseme_PP" in v["missing"]
    assert d["x"]["extra"] == ["custom_smirk"]


def test_teeth_penetrating_a_lip_is_flagged(tmp_path):
    d = one(go(tmp_path, HEAD + '''
ok = call("face_rig_validate", object="head", teeth="teeth")
teeth.location.y = -0.05                                                       # slide the teeth forward through the lips
bpy.context.view_layer.update()
bad = call("face_rig_validate", object="head", teeth="teeth")
print("RESULT", json.dumps({"ok": ok, "bad": bad}))
'''))
    ok = {e["name"]: e for e in d["ok"]["expressions"]}["teeth_tongue_clearance"]
    bad = {e["name"]: e for e in d["bad"]["expressions"]}["teeth_tongue_clearance"]
    assert ok["pass"] is True and ok["measured"]["teeth_clearance_m"] > 0
    assert bad["pass"] is False and bad["measured"]["teeth_clearance_m"] < 0 and bad["measured"]["penetrating_lip_vertices"] > 0
    assert d["ok"]["interior"] == {"teeth_separate": True, "tongue_separate": False, "cavity": True}


def test_no_shape_keys_and_a_closed_mouth_with_an_interior_check_are_refused(tmp_path):
    d = one(go(tmp_path, HEAD + '''
bare = sphere("bare", 0.1)
nokeys = call("face_rig_validate", object="bare", shape_key_profile="arkit")
for i in ids["lip_lower"]:
    head.data.shape_keys.key_blocks["Basis"].data[i].co.z = 0.01
    head.data.vertices[i].co.z = 0.01
closed = call("face_rig_validate", object="head", teeth="teeth")
none_ok = call("face_rig_validate", object="head", shape_key_profile="arkit")
print("RESULT", json.dumps({"nokeys": nokeys, "closed": closed, "none_ok": none_ok}))
'''))
    assert d["nokeys"]["ok"] is False and "no shape keys on bare; generate them first (Faceit or manual)" in d["nokeys"]["error"]
    assert d["closed"]["ok"] is False and "open-mouth source needed or accept no interior check" in d["closed"]["error"]
    assert d["none_ok"]["ok"] is True and d["none_ok"]["interior"]["cavity"] is False
