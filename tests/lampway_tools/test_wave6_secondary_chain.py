# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""secondary_chain_rig (specs/wiki/secondary_chain_rig.md) in the real binary: a tail chain extruded along the region's principal axis under an existing bone, on COPIES
of the armature and the mesh; the region weighted only to the chain and its parent (competing influences removed); damped-track preview constraints; capsule
collider proxies that enclose the body segments; no numeric physics presets."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

CREATURE = '''
rig = armature(bones=(("root", (0, 0, 0), (0, 0, 0.5)), ("spine", (0, 0, 0.5), (0, 0, 1.0))))
body = boxes("creature", [((0, 0, 0.25), (0.4, 0.3, 0.5)), ((0, 0, 0.75), (0.36, 0.26, 0.5)), ((0, -0.7, 0.4), (0.1, 1.0, 0.1))])   # torso low, torso high, a tail along -Y
groups = {n: body.vertex_groups.new(name=n) for n in ("root", "spine")}
for v in body.data.vertices:
    in_tail = v.co.y < -0.18                                         # the torso's back face sits at y = -0.15: clear of it
    name = "spine" if (v.co.z > 0.5 or in_tail) else "root"           # the tail is weighted to spine on purpose: a competing influence to remove
    groups[name].add([v.index], 1.0, "REPLACE")
mod = body.modifiers.new("Armature", "ARMATURE"); mod.object = rig
REGION = [[-0.2, -1.3, 0.3], [0.2, -0.18, 0.5]]
def snapshot():
    return {"bones": sorted(b.name for b in rig.data.bones), "groups": sorted(g.name for g in body.vertex_groups)}
'''


def test_chain_bones_are_children_in_order_connected_and_on_copies(tmp_path):
    d = one(go(tmp_path, CREATURE + '''
before = snapshot()
res = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=4, naming="tail_", region=REGION)
arm = bpy.data.objects[res["armature"]]
bb = {b.name: {"parent": b.parent.name if b.parent else None, "connect": b.use_connect, "head": [round(x, 3) for x in b.head_local], "tail": [round(x, 3) for x in b.tail_local]}
      for b in arm.data.bones}
print("RESULT", json.dumps({"res": res, "bb": bb, "before": before, "after": snapshot()}))
'''))
    res, bb = d["res"], d["bb"]
    assert res["ok"], res
    assert res["chain"] == ["tail_01", "tail_02", "tail_03", "tail_04"] and res["armature"] == "rig_chain" and res["object"] == "creature_chain"
    assert d["before"] == d["after"]                                                  # the original armature and mesh are untouched
    assert bb["tail_01"]["parent"] == "root" and not bb["tail_01"]["connect"]
    for a, b in zip(res["chain"], res["chain"][1:]):
        assert bb[b]["parent"] == a and bb[b]["connect"] is True and bb[b]["head"] == bb[a]["tail"]
    ys = [bb[n]["head"][1] for n in res["chain"]] + [bb["tail_04"]["tail"][1]]
    assert all(b < a for a, b in zip(ys, ys[1:])) and ys[0] > -0.3 and ys[-1] < -1.1          # from the body outward along -Y
    assert res["preview_constraints"] and all(c["type"] == "DAMPED_TRACK" for c in res["preview_constraints"])
    assert res["physics_notes"] == "numeric presets are not provided"


def test_region_vertices_weighted_only_to_the_chain_and_parent_and_the_rest_untouched(tmp_path):
    d = one(go(tmp_path, CREATURE + '''
res = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=4, naming="tail_", region=REGION)
ob = bpy.data.objects[res["object"]]
names = {g.index: g.name for g in ob.vertex_groups}
region, rest = [], []
for v, v0 in zip(ob.data.vertices, body.data.vertices):
    w = {names[g.group]: round(g.weight, 4) for g in v.groups if g.weight > 0}
    inside = all(REGION[0][i] <= v.co[i] <= REGION[1][i] for i in range(3))
    (region if inside else rest).append((w, {body.vertex_groups[g.group].name: round(g.weight, 4) for g in v0.groups if g.weight > 0}))
print("RESULT", json.dumps({"res": res, "region": region, "rest": rest}))
'''))
    res = d["res"]
    allowed = set(res["chain"]) | {"root"}
    assert d["region"] and all(set(w) <= allowed and abs(sum(w.values()) - 1) < 1e-3 for w, _ in d["region"])
    assert any(set(w) & set(res["chain"]) for w, _ in d["region"])
    assert all(w == w0 for w, w0 in d["rest"])                                      # outside the region nothing changed
    assert res["weights"]["vertices"] == len(d["region"]) and res["weights"]["competing_removed"] == len(d["region"])   # every tail vertex lost its spine weight


def test_collider_proxies_enclose_the_body_segment(tmp_path):
    d = one(go(tmp_path, CREATURE + '''
res = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=3, naming="tail_", region=REGION)
arm = bpy.data.objects[res["armature"]]
out = {}
for c in res["colliders"]:
    b = arm.data.bones[c["bone"]]
    h, t = arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local
    worst = 0.0
    for v in body.data.vertices:
        if v.co.y < -0.18:
            continue
        g = max(v.groups, key=lambda e: e.weight)
        if body.vertex_groups[g.group].name != c["bone"]:
            continue
        p = body.matrix_world @ v.co
        ab = t - h; s = max(0.0, min(1.0, (p - h).dot(ab) / ab.length_squared))
        worst = max(worst, (p - (h + ab * s)).length)
    out[c["bone"]] = {"radius": c["radius_m"], "worst": worst, "length": c["length_m"], "proxy": c["proxy"] in bpy.data.objects,
                      "parent": bpy.data.objects[c["proxy"]].parent_bone}
print("RESULT", json.dumps({"res": res, "out": out}))
'''))
    out = d["out"]
    assert set(out) == {"root", "spine"}
    for bone, c in out.items():
        assert c["proxy"] and c["parent"] == bone and c["worst"] <= c["radius"] + 1e-6 and c["radius"] < 0.4 and abs(c["length"] - 0.5) < 1e-6


def test_refusals_more_than_24_bones_a_missing_parent_bone_and_an_empty_region(tmp_path):
    d = one(go(tmp_path, CREATURE + '''
many = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=30, region=REGION)
nobone = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="pelvis", bones=4, region=REGION)
empty = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=4, region=[[5, 5, 5], [6, 6, 6]])
print("RESULT", json.dumps({"many": many, "nobone": nobone, "empty": empty}))
'''))
    assert d["many"]["ok"] is False and "split into several chains" in d["many"]["error"]
    assert d["nobone"]["ok"] is False and "pelvis" in d["nobone"]["error"] and "root" in d["nobone"]["error"] and "spine" in d["nobone"]["error"]
    assert d["empty"]["ok"] is False and "region" in d["empty"]["error"]


def test_a_base_rig_that_fails_weight_audit_is_refused(tmp_path):
    d = one(go(tmp_path, CREATURE + '''
groups["root"].remove([2])                                                   # one body vertex left with no weight at all
res = call("secondary_chain_rig", object="creature", armature="rig", parent_bone="root", bones=4, region=REGION)
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    assert d["res"]["ok"] is False and "weight_audit" in d["res"]["error"] and "rig_chain" not in d["objects"]
