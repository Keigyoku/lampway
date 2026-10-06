# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""auto_rig additions (specs/mixar_docs/auto_rig.md, wiki/auto_rig.md): body plans beyond the humanoid (legged: quadruped, hexapod, octopod; chains:
serpentine, aquatic; avian), naming options (ue, mixamo, metahuman), and parts rigged as ONE character. REAL binary, synthetic box creatures."""

import json

from features_support import run

CREATURES = '''
def quad(name="dog"):
    """Body along Y (head toward -Y), four legs at the corners, standing on Z."""
    return boxes(name, [((0, 0, 0.7), (0.4, 1.2, 0.35)), ((0, -0.75, 0.95), (0.25, 0.3, 0.25)),
                        ((-0.15, -0.45, 0.3), (0.1, 0.1, 0.6)), ((0.15, -0.45, 0.3), (0.1, 0.1, 0.6)),
                        ((-0.15, 0.45, 0.3), (0.1, 0.1, 0.6)), ((0.15, 0.45, 0.3), (0.1, 0.1, 0.6))])
def snake(name="snake"):
    return boxes(name, [((0, y, 0.1), (0.15, 0.4, 0.15)) for y in (-1.6, -1.2, -0.8, -0.4, 0.0, 0.4, 0.8, 1.2)])
def bones_of(arm):
    a = bpy.data.objects[arm]; mw = a.matrix_world
    return {b.name: [round(x, 3) for x in (mw @ b.head_local)] for b in a.data.bones}
'''


def _go(tmp_path, body):
    r = run(tmp_path, CREATURES + body, timeout=600)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_a_quadruped_gets_four_legs_where_its_legs_are(tmp_path):
    res = _go(tmp_path, '''
quad("dog")
r = call("auto_rig", object="dog", kind="quadruped")
print("RESULT", json.dumps({"r": r, "bones": bones_of(r["armature"]) if r.get("ok") else None}))
''')
    r, b = res["r"], res["bones"]
    assert r["ok"] is True and r["kind"] == "quadruped" and r["report"]["unweighted_vertices"] == 0, r
    feet = sorted([v for k, v in b.items() if "_foot_" in k], key=lambda p: (p[1], p[0]))
    assert len(feet) == 4, b
    for f, (x, y) in zip(feet, [(-0.15, -0.45), (0.15, -0.45), (-0.15, 0.45), (0.15, 0.45)]):
        assert abs(f[0] - x) < 0.06 and abs(f[1] - y) < 0.06 and f[2] < 0.3, (f, x, y)
    assert any(k.startswith("head") for k in b) and any(k.startswith("spine") for k in b)


def test_hexapod_and_octopod_count_their_legs(tmp_path):
    res = _go(tmp_path, '''
legs6 = [((s * 0.3, y, 0.15), (0.08, 0.08, 0.3)) for s in (-1, 1) for y in (-0.5, 0.0, 0.5)]
boxes("bug", [((0, 0, 0.4), (0.4, 1.4, 0.2))] + legs6)
legs8 = [((s * 0.3, y, 0.15), (0.08, 0.08, 0.3)) for s in (-1, 1) for y in (-0.6, -0.2, 0.2, 0.6)]
boxes("spider", [((5, 0, 0.4), (0.4, 1.6, 0.2))] + [((p[0] + 5, p[1], p[2]), sz) for p, sz in legs8])
out = {k: call("auto_rig", object=k, kind=v) for k, v in (("bug", "hexapod"), ("spider", "octopod"))}
out["feet"] = {k: sum(1 for n in bones_of(out[k]["armature"]) if "_foot_" in n) for k in ("bug", "spider")}
print("RESULT", json.dumps(out))
''')
    assert res["feet"] == {"bug": 6, "spider": 8}, res


def test_a_serpent_is_a_chain_along_its_length_and_auto_infers_it(tmp_path):
    res = _go(tmp_path, '''
snake("snake")
r = call("auto_rig", object="snake", kind="auto")
print("RESULT", json.dumps({"r": r, "bones": bones_of(r["armature"])}))
''')
    r, b = res["r"], res["bones"]
    assert r["kind"] == "serpentine" and r["report"]["kind_inferred"] is True, r
    ys = sorted(v[1] for k, v in b.items() if k.startswith("spine"))
    assert len(ys) >= 6 and ys[0] < -1.4 and ys[-1] > 1.0, ys


def test_naming_mixamo_and_metahuman_and_tripo_refused(tmp_path):
    res = _go(tmp_path, '''
humanoid("body")
mx = call("auto_rig", object="body", naming="mixamo")
humanoid("body2")
mh = call("auto_rig", object="body2", naming="metahuman")
humanoid("body3")
tp = call("auto_rig", object="body3", naming="tripo")
print("RESULT", json.dumps({"mx": sorted(bones_of(mx["armature"])), "mh": sorted(bones_of(mh["armature"])), "tp": tp,
                            "groups": sorted(g.name for g in bpy.data.objects[mx["mesh"]].vertex_groups)}))
''')
    assert "mixamorig:Hips" in res["mx"] and "mixamorig:LeftForeArm" in res["mx"] and "pelvis" not in res["mx"], res["mx"]
    assert set(res["groups"]) <= set(res["mx"]) and "mixamorig:LeftUpLeg" in res["groups"], "the weights follow the names"
    assert "pelvis" in res["mh"] and "upperarm_l" in res["mh"], res["mh"]
    assert res["tp"]["ok"] is False and "tripo" in res["tp"]["error"], res["tp"]


def test_parts_rig_as_one_character_with_one_armature(tmp_path):
    res = _go(tmp_path, '''
boxes("torso", [((0, 0, 1.15), (0.40, 0.22, 0.60)), ((0, 0, 1.62), (0.18, 0.18, 0.22))])
boxes("arms", [((-0.55, 0, 1.30), (0.60, 0.12, 0.12)), ((0.55, 0, 1.30), (0.60, 0.12, 0.12))])
boxes("legs", [((-0.12, 0, 0.45), (0.16, 0.16, 0.85)), ((0.12, 0, 0.45), (0.16, 0.16, 0.85))])
r = call("auto_rig", object="torso", parts=["arms", "legs"])
arms = [o.name for o in bpy.data.objects if o.type == "ARMATURE"]
mods = {n: [m.object.name for m in bpy.data.objects[n].modifiers if m.type == "ARMATURE"] for n in r.get("meshes", [])}
print("RESULT", json.dumps({"r": r, "arms": arms, "mods": mods}))
''')
    r = res["r"]
    assert r["ok"] is True and res["arms"] == [r["armature"]] and len(r["meshes"]) == 3, res
    assert all(v == [r["armature"]] for v in res["mods"].values()) and r["report"]["unweighted_vertices"] == 0, res
    assert r["report"]["bones"] >= 20, "the skeleton comes from all the parts together (arms and legs are found)"


def test_unknown_kind_refused_with_the_kinds(tmp_path):
    res = _go(tmp_path, '''
quad("dog")
print("RESULT", json.dumps(call("auto_rig", object="dog", kind="centaur")))
''')
    assert res["ok"] is False and "quadruped" in res["error"] and "serpentine" in res["error"], res
