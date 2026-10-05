# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""silhouette_compare (specs/wiki/silhouette_compare.md): the same cameras for the approved source and the candidate; IoU, area ratio, centroid shift, landmark drift per view.
REAL binary, Workbench renders."""

import json
import os
from pathlib import Path

import pytest

from features_support import run

SHAPE = '''
def shape(name, mirror_y=False, scale=1.0, hole=False):
    """An L-shaped piece, asymmetric front to back: a long bar along Y with a tall block at its +Y end."""
    s = -1.0 if mirror_y else 1.0
    ob = boxes(name, [((0, 0.0, 0), (0.4, 1.6, 0.4)), ((0, s * 0.6, 0.5), (0.4, 0.4, 1.0))])
    me = ob.data
    for v in me.vertices:
        v.co = (v.co.x * scale, v.co.y * scale, v.co.z * scale)
    return ob

def ring(name, filled):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=0.5, segments=32, matrix=Matrix.Rotation(math.pi / 2, 4, "X"))
    if not filled:
        pass
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
'''


def test_identical_meshes_agree_in_every_view_and_write_side_by_side_images(tmp_path):
    r = run(tmp_path, SHAPE + '''
shape("src"); shape("same")
res = call("silhouette_compare", a="src", b="same", piece="P", size=256)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is True and res["pass"] is True and res["worst_iou"] > 0.99 and [v["view"] for v in res["views"]] == ["Front", "Back", "Left", "Right"]
    assert all(v["area_ratio"] == pytest.approx(1.0, abs=0.01) and v["centroid_shift_frac"] < 0.01 for v in res["views"]) and len(res["images"]) == 4
    assert all(Path(p).exists() for p in res["images"])


def test_a_front_to_back_mirror_fails_the_side_views_and_not_the_front(tmp_path):
    r = run(tmp_path, SHAPE + '''
shape("src"); shape("flipped", mirror_y=True)
print("RESULT", json.dumps(call("silhouette_compare", a="src", b="flipped", size=256)))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    by = {v["view"]: v for v in res["views"]}
    assert by["Front"]["iou"] > 0.98 and by["Back"]["iou"] > 0.98, "looking along Y the mirror is invisible"
    assert by["Left"]["iou"] < 0.8 and by["Right"]["iou"] < 0.8 and res["pass"] is False, by


def test_zero_tolerance_fails_a_one_percent_scale_change_and_a_loose_one_passes_it(tmp_path):
    r = run(tmp_path, SHAPE + '''
shape("src"); shape("big", scale=1.01)
strict = call("silhouette_compare", a="src", b="big", size=512, min_iou=1.0, views=["Front"])
loose = call("silhouette_compare", a="src", b="big", size=512, min_iou=0.9, views=["Front"])
print("RESULT", json.dumps({"s": strict, "l": loose}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["s"]["pass"] is False and o["l"]["pass"] is True and o["s"]["views"][0]["area_ratio"] > 1.0


def test_a_filled_cap_changes_the_area_ratio_and_landmarks_report_their_drift(tmp_path):
    r = run(tmp_path, SHAPE + '''
shape("src")
cap = shape("capped")
for v in cap.data.vertices:
    if v.co.z > 0.9: v.co.z += 0.5                                                  # the tall block taller by 0.5: a different top
res = call("silhouette_compare", a="src", b="capped", views=["Front"], size=256, landmarks=[{"name": "block_top", "point": [0, 0.6, 1.0]}, {"name": "bar_end", "point": [0, -0.8, 0.0]}])
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    v = r.results[0]["views"][0]
    drift = {d["name"]: d["d"] for d in v["landmark_drift_m"]}
    # the landmark is inside the taller block now: the drift is the distance to the nearest SURFACE (its side wall, 0.2 m)
    assert v["area_ratio"] > 1.1 and drift["block_top"] == pytest.approx(0.2, abs=0.03) and drift["bar_end"] < 0.05


def test_refusals_and_a_plate_with_no_alpha_and_no_flat_background(tmp_path):
    from PIL import Image
    import numpy as np
    noisy = tmp_path / "noisy.png"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)).save(noisy)
    r = run(tmp_path, SHAPE + f'''
a = shape("src"); b = shape("scaled"); b.scale = (2, 2, 2)
print("RESULT", json.dumps({{"same": call("silhouette_compare", a="src", b="src"), "unapplied": call("silhouette_compare", a="src", b="scaled"),
                            "plate": call("silhouette_compare", a="src", b={str(noisy)!r}, views=["Front"]), "views": call("silhouette_compare", a="src", b="scaled", views=["Top"])}}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert "same object" in o["same"]["error"] and "scale not applied on scaled" in o["unapplied"]["error"]
    assert "alpha or a flat background" in o["plate"]["error"] and "views are" in o["views"]["error"]
