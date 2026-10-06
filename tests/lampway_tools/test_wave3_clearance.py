# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""garment_clearance (wiki/garment_clearance.md): signed distance between a piece and the posed body, per pose, in the real binary. The bodies here are open tubes:
since canon 15 an open body declares the band round its openings (body_open_band_m) or is refused."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def run(body, **kw):
    return run_script(PRE + body, timeout=300, **kw)


def test_a_piece_inside_the_body_reports_penetration_depth_and_a_larger_one_is_deeper():
    r = run('''
arm = armature(bones=(("root", (0, 0, 0), (0, 0, 2), None),))
body = tube("body", r=0.30, z0=0, z1=2, rings=24); weights(body, arm, lambda c: {"root": 1.0})
inner = tube("inner", r=0.25, z0=0.4, z1=1.6)
a = api.garment_clearance("inner", "body", "rig", body_open_band_m=0.01)
smaller = tube("smaller", r=0.20, z0=0.4, z1=1.6)
b = api.garment_clearance("smaller", "body", "rig", body_open_band_m=0.01)
res({"a": a["poses"][0], "b": b["poses"][0]})
''')
    assert r.rc == 0, r.out[-1200:]
    a, b = r.results[-1]["a"], r.results[-1]["b"]
    assert a["penetrating_vertices"] > 0 and abs(a["max_depth_m"] - 0.05) < 0.01 and a["min_clearance_m"] < 0
    assert b["max_depth_m"] > a["max_depth_m"] + 0.04                       # the falsifier: a smaller piece sits deeper inside
    assert len(a["worst_region"]) == 3


def test_the_clearance_target_is_a_pass_fail_boundary_and_classes_get_their_own_tolerance():
    r = run('''
arm = armature(bones=(("root", (0, 0, 0), (0, 0, 2), None),))
body = tube("body", r=0.30, z0=0, z1=2, rings=24); weights(body, arm, lambda c: {"root": 1.0})
piece = tube("piece", r=0.32, z0=0.4, z1=1.6)                                   # 2 cm clear of the body
ok = api.garment_clearance("piece", "body", "rig", clearance_target_m=0.015, body_open_band_m=0.01)["poses"][0]
bad = api.garment_clearance("piece", "body", "rig", clearance_target_m=0.03, body_open_band_m=0.01)["poses"][0]
for v in piece.data.vertices: pass
vg = piece.vertex_groups.new(name="cloth"); vg.add([v.index for v in piece.data.vertices], 1.0, "REPLACE")
cls = api.garment_clearance("piece", "body", "rig", clearance_target_m=0.015, classes={"cloth": 0.03}, body_open_band_m=0.01)["poses"][0]
res({"ok": ok, "bad": bad, "cls": cls})
''')
    d = r.results[-1]
    assert d["ok"]["pass"] is True and d["bad"]["pass"] is False and d["cls"]["pass"] is False
    assert abs(d["ok"]["min_clearance_m"] - 0.02) < 0.004


def test_a_pose_that_swings_the_body_into_the_piece_fails_and_the_pose_is_reset_afterwards():
    r = run('''
import math
arm = armature(bones=(("root", (0, 0, 0), (0, 0, 1), None), ("limb", (0, 0, 1), (0, 0, 2), "root")))
body = tube("body", r=0.1, z0=0, z1=2, rings=40); weights(body, arm, lambda c: {"root": 1.0 if c.z < 1 else 0.0, "limb": 0.0 if c.z < 1 else 1.0})
piece = tube("piece", r=0.4, z0=0.5, z1=1.5, loc=(0, 0, 0))                    # a sleeve around the joint, 0.3 clear at rest
out = api.garment_clearance("piece", "body", "rig", pose_set=[{"name": "rest"}, {"name": "limb_out", "bone": "limb", "rotate": [90, 0, 0]}], clearance_target_m=0.015, body_open_band_m=0.01)
pb = arm.pose.bones["limb"]
res({"poses": out["poses"], "pass_count": out["pass_pose_count"], "closest": out["closest_pose"], "after": [round(x, 6) for x in pb.rotation_euler]})
''')
    d = r.results[-1]
    names = {p["name"]: p for p in d["poses"]}
    assert names["rest"]["pass"] is True and names["limb_out"]["pass"] is False and names["limb_out"]["penetrating_vertices"] > 0
    assert d["pass_count"] == 1 and d["closest"] == "rest" and d["after"] == [0.0, 0.0, 0.0]


def test_an_unskinned_body_and_a_piece_that_was_never_placed_are_refused_with_the_fix():
    r = run('''
arm = armature(bones=(("root", (0, 0, 0), (0, 0, 2), None),))
body = tube("body"); piece = tube("piece", loc=(0, 0, 0))
a = api.garment_clearance("piece", "body", "rig").get("error")
weights(body, arm, lambda c: {"root": 1.0}); far = tube("far", loc=(3, 0, 0))
b = api.garment_clearance("far", "body", "rig").get("error")
res({"a": a, "b": b})
''')
    d = r.results[-1]
    assert "the body needs an armature" in d["a"] and "run place_piece first" in d["b"]
