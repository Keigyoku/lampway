# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_lineage (specs/wiki/asset_lineage.md): one record of where a derivative came from (three hashes of the source, the transformation, three identity
anchors that must not move), verified later by the nearest-point distance of each anchor to the derivative. REAL binary, synthetic shapes."""

import json

from features_support import run

PRE = '''
import os
src = boxes("boot", [((0, 0, 0), (1, 1, 1)), ((0, 0, 1.2), (0.6, 0.6, 0.4))])
ANCH = [{"name": "toe", "point": [0.5, 0, 0]}, {"name": "heel", "point": [-0.5, 0, 0]}, {"name": "top", "point": [0, 0, 1.4]}]
'''


def test_record_then_verify_passes_for_an_unchanged_copy_and_a_move_inside_tolerance(tmp_path):
    r = run(tmp_path, PRE + '''
rec = call("asset_lineage", action="record", object="boot", transform="approved seed", anchors=ANCH)
cp = src.copy(); cp.data = src.data.copy(); cp.name = "boot_copy"; bpy.context.scene.collection.objects.link(cp)
cp["lw_lineage"] = src["lw_lineage"]
same = call("asset_lineage", action="verify", object="boot_copy")
cp.data.vertices[0].co.x += 0.005                                     # 5 mm, inside the 1 cm tolerance
inside = call("asset_lineage", action="verify", object="boot_copy")
lines = open(root + "/boot/lineage.jsonl").read().splitlines()
print("RESULT", json.dumps({"rec": rec, "same": same, "inside": inside, "lines": len(lines)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    L = o["rec"]["lineage"]
    assert o["rec"]["ok"] is True and L["parent_id"] is None and set(L["source_hash"]) == {"geometry", "uv", "material"} and len(L["source_hash"]["geometry"]) == 64
    assert [a["name"] for a in L["anchors"]] == ["toe", "heel", "top"] and o["lines"] == 1
    assert o["same"]["verify"]["pass"] is True and o["same"]["verify"]["anchors_moved"] == []
    assert o["inside"]["verify"]["pass"] is True


def test_verify_fails_when_an_anchor_moves_beyond_tolerance_and_names_it(tmp_path):
    r = run(tmp_path, PRE + '''
call("asset_lineage", action="record", object="boot", anchors=ANCH)
for v in src.data.vertices:
    if v.co.z > 0.9: v.co.z += 0.3                                    # the top plate rises 30 cm: the 'top' anchor (z 1.4) ends in mid-air
bad = call("asset_lineage", action="verify", object="boot")
print("RESULT", json.dumps(bad))
''')
    assert r.rc == 0, r.out[-2500:]
    v = r.results[0]["verify"]
    assert v["pass"] is False and [m["name"] for m in v["anchors_moved"]] == ["top"] and v["anchors_moved"][0]["distance_m"] > 0.01


def test_a_uv_only_edit_changes_the_uv_hash_only_and_a_child_chains_to_its_parent(tmp_path):
    r = run(tmp_path, PRE + '''
bm = bmesh.new(); bm.from_mesh(src.data); uv = bm.loops.layers.uv.new("UVMap")
for f in bm.faces:
    for l in f.loops: l[uv].uv = (l.vert.co.x * 0.5 + 0.5, l.vert.co.y * 0.5 + 0.5)
bm.to_mesh(src.data); bm.free()
a = call("asset_lineage", action="record", object="boot", anchors=ANCH, transform="seed")
for d in src.data.uv_layers[0].data: d.uv = (d.uv[0] * 0.9, d.uv[1])
again = call("asset_lineage", action="record", object="boot", anchors=ANCH, transform="uv edit")
b = call("asset_lineage", action="record", object="boot", anchors=ANCH, transform="uv edit", parent=a["lineage"]["id"])
shown = call("asset_lineage", action="show", object="boot")
print("RESULT", json.dumps({"a": a, "again": again, "b": b, "shown": shown}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    A, B = o["a"]["lineage"], o["b"]["lineage"]
    assert A["hash"]["geometry"] == B["hash"]["geometry"] and A["hash"]["uv"] != B["hash"]["uv"] and A["hash"]["material"] == B["hash"]["material"]
    assert o["again"]["ok"] is False and "already derived from" in o["again"]["error"] and A["id"] in o["again"]["error"]
    assert B["parent_id"] == A["id"] and [x["id"] for x in o["shown"]["chain"]] == [A["id"], B["id"]]


def test_refusals_name_what_is_missing(tmp_path):
    r = run(tmp_path, PRE + '''
two = call("asset_lineage", action="record", object="boot", anchors=ANCH[:2])
outside = call("asset_lineage", action="record", object="boot", anchors=[dict(ANCH[0], point=[9, 9, 9])] + ANCH[1:])
none = call("asset_lineage", action="verify", object="boot")
bad = call("asset_lineage", action="nonsense", object="boot")
print("RESULT", json.dumps({"two": two, "outside": outside, "none": none, "bad": bad}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert "three identity anchors" in o["two"]["error"] and "bounding box" in o["outside"]["error"]
    assert "no lineage" in o["none"]["error"] and "record" in o["none"]["error"] and "record|verify|show" in o["bad"]["error"]
