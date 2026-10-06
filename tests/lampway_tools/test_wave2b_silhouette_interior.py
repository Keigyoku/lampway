# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""silhouette_compare amendment (specs/mrmak/BUILD_ORDER_ADDENDUM section 2): an interior-difference band and an enclosed-background-hole check beside IoU, area and centroid."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

SPHERES = '''
def sph(name, kind="plain", subdiv=4):
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=0.5)
    if kind == "dimple":
        for v in bm.verts:
            if v.co.y < -0.3 and abs(v.co.x) < 0.2 and abs(v.co.z) < 0.2:
                v.co.y += 0.12 * (1 - (v.co.x ** 2 + v.co.z ** 2) / 0.04)
    if kind == "holed":
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.calc_center_median().x) < 0.08 and abs(f.calc_center_median().z) < 0.08 and abs(f.calc_center_median().y) > 0.3], context="FACES")
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    for p in me.polygons: p.use_smooth = True
    return link(ob)
'''


def test_the_interior_difference_separates_a_dimple_that_iou_cannot_see(tmp_path):
    r = run(tmp_path, SPHERES + '''
a = sph("a"); b = sph("b"); c = sph("c", "dimple")
same = call("silhouette_compare", a="a", b="b", piece="p", views=["Front"], size=256, interior=True)
dim = call("silhouette_compare", a="a", b="c", piece="p", views=["Front"], size=256, interior=True)
print("RESULT", json.dumps({"same": same, "dim": dim}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    s, m = d["same"]["views"][0], d["dim"]["views"][0]
    assert s["iou"] > 0.99 and m["iou"] > 0.99                                    # the outlines are the same: IoU cannot tell them apart
    assert s["interior_diff"] < 1e-3 and m["interior_diff"] > 0.01, (s, m)
    assert m["cells_compared"] > 1000 and len(m["interior_bands"]) == 10 and m["evidence"] == "ok"


def test_an_enclosed_background_hole_is_reported_for_the_view_that_sees_through(tmp_path):
    r = run(tmp_path, SPHERES + '''
a = sph("a"); h = sph("h", "holed")
res = call("silhouette_compare", a="a", b="h", piece="p", views=["Front", "Left"], size=256, interior=True)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    rows = {v["view"]: v for v in r.results[0]["views"]}
    assert rows["Front"]["hole_count_b"] >= 1 and rows["Front"]["hole_count_a"] == 0 and rows["Left"]["hole_count_b"] == 0


def test_interior_is_off_by_default_and_never_computed_against_a_plate_image(tmp_path):
    r = run(tmp_path, SPHERES + '''
sph("a"); sph("b")
res = call("silhouette_compare", a="a", b="b", piece="p", views=["Front"], size=128)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0 and "interior_diff" not in r.results[0]["views"][0]
