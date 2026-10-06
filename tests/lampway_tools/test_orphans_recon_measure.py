# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The reconstruction instrument's remainder (STATUS O39; ported from the astra-1 shelf's spike measure.py): six-view silhouette IoU against the approved
plates after a search over the 24 proper axis-aligned orientations, the cavity ratio (a ray up through the crown centre: floor to first surface over height,
~0 solid, high for a hollow crown) and the shell ratio, the crest-fin width and length ratios from the top view, and the left/right albedo luminance ratio
(a baked directional light shows as one side brighter). Views are on the WEARER's axes in the canonical frame (front -Y, wearer's left +X, +Z up)."""

import itertools
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import recon_measure as RM  # noqa: E402


def box(lo, hi):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    t = [(a, b, c) for a, b, c, d in q] + [(a, c, d) for a, b, c, d in q]
    return v, np.array(t)


def merge(*parts):
    vs, ts, n = [], [], 0
    for v, t in parts:
        vs.append(v); ts.append(t + n); n += len(v)
    return np.concatenate(vs), np.concatenate(ts)


def lshape():
    """An asymmetric solid: no axis flip or swap maps it onto itself."""
    return merge(box((0, 0, 0), (3, 1, 1)), box((0, 0, 1), (1, 1, 4)), box((0, 1, 0), (1, 2, 1)))


def test_the_24_orientations_are_the_proper_axis_rotations():
    rs = list(RM.rotations())
    assert len(rs) == 24 and all(abs(np.linalg.det(r) - 1) < 1e-9 for r in rs) and len({r.tobytes() for r in rs}) == 24


def test_every_derived_view_equals_a_direct_raster_for_every_orientation():
    v, t = lshape()
    v = RM.normalise(v)
    base = RM.base_masks(v, t, 48)
    for R in RM.rotations():
        for view in RM.VIEWS:
            direct = RM.raster(v @ R.T, t, view, 48)
            assert np.array_equal(RM.view_mask(base, R, view), direct), (R.tolist(), view)


def test_the_search_recovers_how_the_reconstruction_was_turned_and_scores_all_six_views():
    v, t = lshape()
    plates = {view: RM.crop(RM.raster(RM.normalise(v), t, view, 96)) for view in RM.VIEWS}
    R0 = [r for r in RM.rotations()][7]
    out = RM.measure(v @ R0.T, t, plates, size=96)
    assert out["iou_mean_search"] == pytest.approx(1.0) and np.allclose(np.array(out["orientation"]) @ R0, np.eye(3)), out["orientation"]
    assert set(out["iou"]) == set(RM.VIEWS) and min(out["iou"].values()) > 0.99 and out["orientation_is_identity"] is False
    plain = RM.measure(v, t, plates, size=96)
    assert plain["orientation_is_identity"] is True


def test_a_hollow_crown_has_a_high_cavity_ratio_and_a_solid_one_does_not():
    wall = 0.05
    shell = merge(box((-1, -1, 0), (-1 + wall, 1, 1)), box((1 - wall, -1, 0), (1, 1, 1)), box((-1, -1, 0), (1, -1 + wall, 1)),
                  box((-1, 1 - wall, 0), (1, 1, 1)), box((-1, -1, 1 - wall), (1, 1, 1)))
    hollow = RM.cavity(*shell)
    solid = RM.cavity(*box((-1, -1, 0), (1, 1, 1)))
    assert hollow["cavity_ratio"] == pytest.approx(1 - wall, abs=0.02) and hollow["shell_ratio"] == pytest.approx(wall, abs=0.02) and hollow["ray_hits"] == 2
    assert solid["cavity_ratio"] == pytest.approx(0.0, abs=1e-6) and solid["shell_ratio"] == pytest.approx(1.0, abs=1e-6)


def test_the_crest_fin_shows_in_the_top_view_and_a_plain_dome_has_none():
    head = box((-1, -1.2, 0), (1, 1.2, 1.5))
    fin = box((-0.1, -1.8, 1.5), (0.1, 1.8, 2.0))
    with_fin = RM.crest(RM.raster(RM.normalise(merge(head, fin)[0]), merge(head, fin)[1], "top", 120))
    plain = RM.crest(RM.raster(RM.normalise(head[0]), head[1], "top", 120))
    # the fin is 0.2 wide on a 2.0-wide head (ratio 0.1) and overhangs 0.6 of 3.6 at each end (1/3 of the rows); the shelf's code divided by the longest
    # COLUMN (3.6, front to back) and would read 0.056
    assert with_fin["crest_fin_width_ratio"] == pytest.approx(0.1, abs=0.015) and with_fin["crest_fin_length_ratio"] == pytest.approx(1 / 3, abs=0.03), with_fin
    assert plain["crest_fin_width_ratio"] is None and plain["crest_fin_length_ratio"] == 0.0


def test_the_luminance_ratio_is_the_wearers_left_over_the_wearers_right():
    x = np.array([-1.0, -0.5, 0.5, 1.0]); lum = np.array([50.0, 50.0, 100.0, 100.0])
    assert RM.lum_ratio(x, lum) == pytest.approx(2.0), "canonical +X is the wearer's left"
    assert RM.lum_ratio(np.array([1.0]), np.array([1.0])) is None


def test_a_plate_needs_alpha_and_the_search_views_must_be_given(tmp_path):
    from PIL import Image
    Image.new("RGB", (8, 8)).save(tmp_path / "front.png")
    with pytest.raises(ValueError, match="alpha"):
        RM.plate_mask(str(tmp_path / "front.png"))
    v, t = lshape()
    with pytest.raises(ValueError, match="front"):
        RM.measure(v, t, {"top": np.ones((4, 4), bool)}, size=32)


def test_the_tool_measures_a_turned_scene_object_against_its_plates_through_api(tmp_path):
    from features_support import run
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.pipeline import recon_measure as RM
from PIL import Image
ob = boxes("recon", [((1.5, 0.5, 0.5), (3, 1, 1)), ((0.5, 0.5, 2.5), (1, 1, 3)), ((0.5, 1.5, 0.5), (1, 1, 1))])
me = ob.data
v = np.array([list(x.co) for x in me.vertices]); t = np.array([list(p.vertices) for p in me.polygons])
tris = np.concatenate([t[:, [0, 1, 2]], t[:, [0, 2, 3]]])
os.makedirs(os.path.join(root, "plates"), exist_ok=True)
plates = {}
for view in RM.VIEWS:
    m = RM.raster(RM.normalise(v), tris, view, 128)
    a = np.zeros(m.shape + (4,), np.uint8); a[m] = (200, 150, 50, 255)
    Image.fromarray(a).save(os.path.join(root, "plates", view + ".png")); plates[view] = "plates/" + view + ".png"
ca = me.color_attributes.new("albedo", "FLOAT_COLOR", "POINT")
for i, vx in enumerate(me.vertices):
    g = 0.8 if vx.co.x > 1.4 else 0.4
    ca.data[i].color = (g, g, g, 1.0)
me.color_attributes.active_color = ca
ob.rotation_euler = (0, 0, math.radians(90)); bpy.context.view_layer.update()
res = call("recon_measure", object="recon", plates=plates, size=128)
nofile = call("recon_measure", object="recon", plates={"front": "plates/none.png"})
print("RESULT", json.dumps({"res": res, "nofile": nofile}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    res = o["res"]
    assert res["ok"] and res["orientation_is_identity"] is False and res["iou_mean_all"] > 0.97, res
    assert res["lum_left_right_ratio"] > 1.5 and res["lum_source"].startswith("colour attribute"), res
    assert res["cavity_ratio"] is not None and res["crest_fin_length_ratio"] >= 0, res
    assert o["nofile"]["ok"] is False and "no plate" in o["nofile"]["error"], o["nofile"]
