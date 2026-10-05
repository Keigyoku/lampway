# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_openings / opening_gasket (specs/shelf/fit_openings.md + specs/wiki/opening_gasket.md): every cap a seed put across a limb, neck or waist opening gets a typed decision
keep | gasket | delete. A gasket cuts the POSED limb's cross-section plus the wear clearance into the cap plane, removes the inside and forms a collar - the user's "manifold it" read as an
engine exhaust / intake MANIFOLD PORT: a formed tubular collar whose free edge is a ROLLED lip, not a raw cut hole. The collar depth (the "flange length") is his number and unruled: building it
without one answers needs_decision, and `variants` renders three depths for him to pick. REAL binary."""

import json

import pytest

from features_support import run

SCENE = '''
def capped_cylinder(name="piece", radius=0.5, depth=1.0, segments=32):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth, matrix=Matrix.Translation((0, 0, depth / 2)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))

def limb(name="limb", radius=0.3, segments=24):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=segments, radius1=radius, radius2=radius, depth=2.0, matrix=Matrix.Translation((0, 0, 0.5)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))

POSE = {"entries": [{"bone": "neck_01", "axis": "forward", "deg": -4}], "posed": True}

def stats(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bnd = [e for e in bm.edges if len(e.link_faces) == 1]
    # winding: every interior edge must be used once in each direction
    bad = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            dirs = []
            for f in e.link_faces:
                for l in f.loops:
                    if l.edge == e: dirs.append((l.vert.index, l.link_loop_next.vert.index))
            if dirs[0] == dirs[1]: bad += 1
    seen, loops = set(), 0
    for e in bnd:
        if e in seen: continue
        loops += 1; st = [e]; seen.add(e)
        while st:
            c = st.pop()
            for v in c.verts:
                for nb in v.link_edges:
                    if len(nb.link_faces) == 1 and nb not in seen: seen.add(nb); st.append(nb)
    deg = sum(1 for f in bm.faces if f.calc_area() < 1e-12)
    out = {"faces": len(bm.faces), "non_manifold": nm, "boundary_loops": loops, "bad_winding": bad, "zero_area": deg}
    bm.free(); return out
'''


def scene(tmp_path, body):
    return run(tmp_path, SCENE + body)


def test_detect_finds_the_capped_site_and_an_open_tube_has_none(tmp_path):
    r = scene(tmp_path, '''
capped_cylinder("capped")
bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=0.5, radius2=0.5, depth=1.0, matrix=Matrix.Translation((4, 0, 0.5)))
me = bpy.data.meshes.new("open"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("open", me))
a = call("fit_openings", stage="detect", object="capped", axis=[0, 0, 1])
b = call("fit_openings", stage="detect", object="open", axis=[0, 0, 1])
print("RESULT", json.dumps({"a": a, "b": b}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    caps = [c for c in o["a"]["candidates"] if c["state"] == "capped"]
    assert len(caps) == 2 and {round(c["plane_origin_m"][2], 2) for c in caps} == {0.0, 1.0}, "a closed cylinder has a cap at each end"
    assert o["b"]["candidates"] == [], "the falsifier: an open tube has no capped site"


def test_gasket_opens_the_cap_into_a_rolled_collar_that_is_manifold_and_clears_the_limb_by_the_clearance(tmp_path):
    r = scene(tmp_path, '''
capped_cylinder("piece"); limb("limb")
before = stats(bpy.data.objects["piece"])
res = call("fit_openings", stage="apply", object="piece", limb="limb", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "gasket"}, flange_mm=20, lip_mm=4,
           clearance_mm=15, captain_words="make a hole, base on the base body, and manifold it")
new = bpy.data.objects[res["object"]]
s = stats(new)
import mathutils
# every vertex of the free inner ring: distance to the limb outline (radius 0.3 about z)
ring = [v.co for v in new.data.vertices if abs(v.co.z - 1.0) < 1e-6 and 0.28 < math.hypot(v.co.x, v.co.y) < 0.4]
poly = [(0.3 * math.cos(2 * math.pi * k / 24), 0.3 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))
dist = [min(seg_dist((v.x, v.y), poly[k], poly[(k + 1) % 24]) for k in range(24)) for v in ring]                 # to the limb's OUTLINE (a 24-gon), not to a circle
print("RESULT", json.dumps({"res": res, "before": before, "after": s, "clear_min": min(dist), "clear_max": max(dist), "n_ring": len(ring)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"]["ok"] is True and o["res"]["openings"][0]["verdict"] == "gasket" and o["res"]["openings"][0]["manifold"] is True
    a = o["after"]
    assert a["non_manifold"] == 0 and a["bad_winding"] == 0 and a["zero_area"] == 0, a
    assert a["boundary_loops"] == 1, "exactly one free (rolled) rim loop where the cap was: the opening, nothing else open"
    assert o["clear_min"] == pytest.approx(0.015, abs=0.001) and o["clear_max"] == pytest.approx(0.015, abs=0.001), "15 mm from the limb outline (within 1 mm)"
    assert o["res"]["openings"][0]["collar_depth_mm"] == 20 and o["res"]["openings"][0]["lip_rings"] >= 4


def test_zero_clearance_fails_the_clearance_assertion_the_falsifier(tmp_path):
    r = scene(tmp_path, '''
capped_cylinder("piece"); limb("limb")
res = call("fit_openings", stage="apply", object="piece", limb="limb", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "gasket"}, flange_mm=20, clearance_mm=0)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is False and "clearance_mm" in res["error"] and "5" in res["error"], "the clearance is bounded 5..40 mm (the pipeline's wear clearance)"


def test_keep_changes_no_geometry_and_logs_the_decision_and_delete_leaves_the_rim_open(tmp_path):
    r = scene(tmp_path, '''
ob = capped_cylinder("piece"); limb("limb")
def sig(o): return [tuple(round(c, 6) for c in v.co) for v in o.data.vertices], len(o.data.polygons)
h0 = sig(ob)
k = call("fit_openings", stage="apply", object="piece", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "keep"}, piece="P", captain_words="hidden, keep it")
h1 = sig(ob)
d = call("fit_openings", stage="apply", object="piece", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "delete"}, piece="P")
new = bpy.data.objects[d["object"]]
print("RESULT", json.dumps({"k": k, "same": h0 == h1, "d": d, "after": stats(new), "before_faces": len(ob.data.polygons)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["k"]["ok"] is True and o["same"] is True and o["k"]["openings"][0]["verdict"] == "keep"
    assert o["after"]["boundary_loops"] == 1 and o["after"]["faces"] == o["before_faces"] - 1, "delete: the cap goes, the rim stays open"
    rows = [json.loads(line) for line in (tmp_path / "P" / "fit" / "decisions.jsonl").read_text().splitlines()]
    assert [x["answer"] for x in rows] == ["keep", "delete"] and rows[0]["question"] == "opening_decision" and rows[0]["captain_words"] == "hidden, keep it"


def test_the_pose_the_flange_and_the_texture_are_guarded(tmp_path):
    r = scene(tmp_path, '''
capped_cylinder("piece"); limb("limb")
base = dict(stage="apply", object="piece", limb="limb", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], answers={"OP001": "gasket"})
nopose = call("fit_openings", flange_mm=20, **base)
noflange = call("fit_openings", pose=POSE, **base)
badans = call("fit_openings", pose=POSE, flange_mm=20, **dict(base, answers={"OP001": "burn"}))
unknown = call("fit_openings", pose=POSE, flange_mm=20, **dict(base, answers={"OP999": "keep"}))
bpy.data.objects["piece"]["lw_studio_textured"] = True
tex = call("fit_openings", pose=POSE, flange_mm=20, **base)
ack = call("fit_openings", pose=POSE, flange_mm=20, texture_discard_ack=True, **base)
print("RESULT", json.dumps({"nopose": nopose, "noflange": noflange, "badans": badans, "unknown": unknown, "tex": tex, "ack": ack}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["nopose"]["ok"] is False and "never the rest pose" in o["nopose"]["error"] and "fit_pose" in o["nopose"]["error"]
    nd = o["noflange"]
    assert nd["ok"] is True and nd["needs_decision"]["what"] == "collar depth (flange length)" and nd["needs_decision"]["suggested_mm"] == [10, 20, 35] and "variants" in nd["needs_decision"]["how"]
    assert "keep | gasket | delete" in o["badans"]["error"] and "OP999" in o["unknown"]["error"]
    assert o["tex"]["ok"] is False and "discards the studio texture" in o["tex"]["error"] and o["ack"]["ok"] is True


def test_variants_builds_three_collar_depths_and_renders_each_for_the_captain_to_pick(tmp_path):
    r = scene(tmp_path, '''
capped_cylinder("piece"); limb("limb")
res = call("fit_openings", stage="variants", object="piece", limb="limb", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, depths_mm=[10, 20, 35], lip_mm=4, piece="P", size=256)
print("RESULT", json.dumps({"res": res, "names": sorted(o.name for o in bpy.data.objects)}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert [int(v["collar_depth_mm"]) for v in o["res"]["variants"]] == [10, 20, 35] and all(v["manifold"] for v in o["res"]["variants"])
    assert all(__import__("os").path.exists(v["image"]) for v in o["res"]["variants"]) and len({v["image"] for v in o["res"]["variants"]}) == 3
    assert not [n for n in o["names"] if "collar_variant" in n], "the variant objects are removed after rendering: nothing is applied until he picks"
