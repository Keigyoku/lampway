# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 6 (canon 15 B.5, B.6), lampway_garment_clearance:
* the GAP is measured on the piece's INNERMOST layer: a point counts only if the segment from it to its nearest skin point crosses no
  other piece surface (INV-15.3) - a medallion on a strap on a plate is not the gap; reported per material class (p50, p90);
* a body region (by bones) is HIDEABLE when, from every standard view where it shows, the armour covers at least 98 % of its projected
  skin (enclosed_pct per view); skin through armour there is not a defect (INV-15.4). REAL binary."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

SCENE = r'''
import math
def tube_obj(name, r, z0, z1, seg=48, rings=8, y_off=0.0):
    bm = bmesh.new()
    rows = []
    for k in range(rings + 1):
        z = z0 + (z1 - z0) * k / rings
        rows.append([bm.verts.new((r * math.cos(2 * math.pi * j / seg), y_off + r * math.sin(2 * math.pi * j / seg), z)) for j in range(seg)])
    for k in range(rings):
        for j in range(seg):
            bm.faces.new((rows[k][j], rows[k][(j + 1) % seg], rows[k + 1][(j + 1) % seg], rows[k + 1][j]))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob
arm = armature(bones=(("spine_01", (0, 0, 0), (0, 0, 1), None),))
body = tube_obj("body", 0.10, 0.0, 1.0, rings=20)
weights(body, arm, lambda c: {"spine_01": 1.0})
def piece(z0, z1):
    plate = tube_obj("piece", 0.12, z0, z1)
    bm = bmesh.new(); bm.from_mesh(plate.data)
    n0 = len(bm.verts)
    for a, b in ((0.13, 0.14),):                         # a medallion strip just outside the plate, in front (-y)
        q = [bm.verts.new((x, -a if i < 2 else -b, z)) for i, (x, z) in enumerate(((-0.02, 0.45), (0.02, 0.45), (0.02, 0.55), (-0.02, 0.55)))]
    for v in q: v.co.y = -0.13
    bm.faces.new(q)
    bm.to_mesh(plate.data); bm.free()
    g = plate.vertex_groups.new(name="plate"); g.add(list(range(n0)), 1.0, "REPLACE")
    m = plate.vertex_groups.new(name="medallion"); m.add(list(range(n0, n0 + 4)), 1.0, "REPLACE")
    return plate
'''


def _run(body):
    r = run_script(PRE + SCENE + body, timeout=300)
    assert r.rc == 0, r.out[-2000:]
    return r.results[-1]


def test_b5_the_gap_is_the_innermost_layers_per_class_and_a_medallion_is_not_counted():
    d = _run('''
piece(0.3, 0.7)
r = api.garment_clearance("piece", "body", "rig", body_open_band_m=0.01, gap_classes={"plate": "metal", "medallion": "metal"})
res({"ok": r.get("ok"), "error": r.get("error"), "gap": r.get("poses", [{}])[0].get("gap")})
''')
    assert d["ok"], d["error"]
    g = d["gap"]["metal"]
    assert g["p50_m"] == pytest.approx(0.02, abs=0.0015) and g["p90_m"] == pytest.approx(0.02, abs=0.0015), g      # the plate's 2 cm, not the medallion's 3
    assert g["excluded_outer"] == 4 and g["vertices"] == 48 * 9, g


def test_b6_a_region_the_armour_wraps_from_every_view_is_hideable_and_a_partial_wrap_is_not():
    d = _run('''
piece(-0.05, 1.05)
full = api.garment_clearance("piece", "body", "rig", body_open_band_m=0.01, hideable_regions={"torso": ["spine_01"]})
bpy.data.objects.remove(bpy.data.objects["piece"])
piece(0.3, 0.7)
part = api.garment_clearance("piece", "body", "rig", body_open_band_m=0.01, hideable_regions={"torso": ["spine_01"]})
res({"full": full.get("poses", [{}])[0].get("hideable") or full.get("error"), "part": part.get("poses", [{}])[0].get("hideable") or part.get("error")})
''')
    f, p = d["full"]["torso"], d["part"]["torso"]
    assert f["hideable"] is True and min(f["enclosed_pct_by_view"].values()) >= 98.0, f
    assert p["hideable"] is False and 30 < p["enclosed_pct_by_view"]["front"] < 50, p                    # 0.4 m of 1 m covered
    assert set(f["enclosed_pct_by_view"]) == {"front", "back", "left", "right"}, f                     # top/bottom: no region pixels (open tube)


def test_b6_the_region_is_rendered_alone_so_its_own_hidden_skin_does_not_count():
    """Two legs side by side; the armour wraps the RIGHT one only. From the left view the left leg hides the right: the visible region
    is the uncovered left leg (0 %). Counting the hidden right leg (covered) would read about half."""
    d = _run('''
for o in list(bpy.data.objects):
    if o.name in ("body",): bpy.data.objects.remove(o)
legs = tube_obj("legs", 0.06, 0.0, 0.8, rings=8)
bm = bmesh.new(); bm.from_mesh(legs.data)
dup = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
for v in [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]: v.co.x -= 0.15
for v in bm.verts[:]:
    if v not in set(g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)): v.co.x += 0.15
bm.to_mesh(legs.data); bm.free()
weights(legs, arm, lambda c: {"spine_01": 1.0})
armour = tube_obj("piece", 0.08, -0.05, 0.85)
for v in armour.data.vertices: v.co.x -= 0.15
r = api.garment_clearance("piece", "legs", "rig", body_open_band_m=0.01, hideable_regions={"legs": ["spine_01"]})
res(r.get("poses", [{}])[0].get("hideable") or r.get("error"))
''')
    v = d["legs"]["enclosed_pct_by_view"]
    assert v["left"] < 1.0 and 40 < v["front"] < 60 and d["legs"]["hideable"] is False, v
