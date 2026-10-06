# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 2 at the TOOL level (canon 05): lampway_fit_validate's receipts in the real binary.

* expectations are measured on the posed JOINTS and a wrong-sign pose is REFUSED (golden C07); an expectation on the
  commanded Euler angle cannot fail and is refused as such;
* poses are named in the joint grammar (axis from the joints, through the bone's joint);
* the seam row is the SOURCE ledger measured in the pose (golden C03: 32 pairs, 8.208 cm under per-part bones);
* crossings are SURFACE crossings both ways (a panel crossing a sphere between its vertices: G15.4) and the positive control
  is capped at half the piece's extent (golden C14).
Each was observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from test_wave3_weights import PRE  # noqa: E402


def run(body, goldens=None):
    head = PRE + LOAD_OBJ + (f"GOLD = {str(goldens)!r}\n" if goldens else "")
    r = run_script(head + body, timeout=300)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


C07_ARM = '''
import math
sh = (0.2, 0.0, 1.4); a = math.radians(-40.0); el = (sh[0] + 0.3 * math.cos(a), 0.0, sh[2] + 0.3 * math.sin(a))
wr = (sh[0] + 0.55 * math.cos(a), 0.0, sh[2] + 0.55 * math.sin(a))
arm = armature(bones=(("upperarm_l", sh, el, None), ("lowerarm_l", el, wr, "upperarm_l")))
orig = tube("orig", r=0.065, z0=0.0, z1=0.1, seg=12, rings=2, loc=(0.6, 0.0, 1.0)); piece = tube("piece", r=0.065, z0=0.0, z1=0.1, seg=12, rings=2, loc=(0.6, 0.0, 1.0))
weights(piece, arm, lambda c: {"lowerarm_l": 1.0})
EXPECT = {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}
'''


def test_g05_5_a_joint_named_pose_moves_the_elbow_down_and_the_negated_axis_is_refused():
    d = run(C07_ARM + '''
poses = [{"name": "lower_20", "bones": [{"bone": "upperarm_l", "axis": [0, 1, 0], "deg": 20}], "expect": EXPECT},
         {"name": "negated", "bones": [{"bone": "upperarm_l", "axis": [0, -1, 0], "deg": 20}], "expect": EXPECT}]
v = api.fit_validate("measure", piece="p", bound="piece", original="orig", poses=poses, roles={"p": "metal"})
res({"ok": v.get("ok"), "error": v.get("error"), "rows": [{k: r.get(k) for k in ("name", "verdict", "why", "expect")} for r in v.get("poses", [])]})
''')
    assert d["ok"], d["error"]
    lower, neg = d["rows"]
    assert lower["verdict"] != "REFUSED" and lower["expect"]["measured_cm"] >= 2.0, lower
    assert neg["verdict"] == "REFUSED" and neg["expect"]["measured_cm"] < 0, neg


def test_an_expectation_on_the_commanded_euler_angle_is_refused_because_it_cannot_fail():
    d = run(C07_ARM + '''
poses = [{"name": "euler", "bone": "upperarm_l", "rotate": [60, 0, 0], "expect": {"bone": "upperarm_l", "axis": "x", "min_deg": 20}}]
v = api.fit_validate("measure", piece="p", bound="piece", original="orig", poses=poses, roles={"p": "metal"})
res(v["poses"][0])
''')
    assert d["verdict"] == "REFUSED" and "joint" in d["why"], d


def test_g05_2_the_seam_row_is_the_source_ledger_measured_in_the_pose(goldens):
    d = run('''
import math
arm = armature(bones=(("spine_01", (0, 0, 0.95), (0, 0, 1.2), None), ("spine_03", (0, 0, 1.2), (0, 0, 1.55), "spine_01")))
orig = load_obj(GOLD + "/C03_seam_tube/piece.obj", "orig"); piece = load_obj(GOLD + "/C03_seam_tube/piece.obj", "piece")
lo, hi = piece.vertex_groups.new(name="lower"), piece.vertex_groups.new(name="upper")
b1, b3 = piece.vertex_groups.new(name="spine_01"), piece.vertex_groups.new(name="spine_03")
for v in piece.data.vertices:                                   # one bone per part: the lower tube (192 vertices) and the upper
    (lo if v.index < 192 else hi).add([v.index], 1.0, "REPLACE")
    (b1 if v.index < 192 else b3).add([v.index], 1.0, "REPLACE")
weights(piece, arm, lambda c: {})
poses = [{"name": "twist", "bones": [{"bone": "spine_03", "axis": "up", "deg": 40}]}]
v = api.fit_validate("measure", piece="p", bound="piece", original="orig", poses=poses, roles={"lower": "metal", "upper": "metal"})
res({"ok": v.get("ok"), "error": v.get("error"), "seam": v["poses"][0]["pieces"]["upper"]["seam"] if v.get("ok") else None, "ledger": v.get("seam_ledger")})
''', goldens)
    assert d["ok"], d["error"]
    assert d["seam"]["pairs"] == 32 and d["seam"]["open_over_2mm"] == 32 and d["seam"]["max_cm"] == pytest.approx(8.2085, abs=1e-3), d["seam"]
    assert d["ledger"]["origin"] == "source-exact-coordinate-groups" and d["ledger"]["pairs"] == 32


PANEL = '''
import math
arm = armature(bones=(("root", (0, 0, 0.5), (0, 0, 1.5), None),))
body = load_obj(GOLD + "/C05_clearance/sphere.obj", "body"); weights(body, arm, lambda c: {"root": 1.0})
'''


def test_g15_4_a_panel_crossing_the_body_between_its_vertices_is_seen_by_surface_crossings_and_fails_metal(goldens):
    d = run(PANEL + '''
import numpy as np
Vb = np.array([v.co[:] for v in body.data.vertices]); top = Vb[np.argmax(Vb[:, 2])]          # a sphere vertex (the pole)
c = top + np.array([0, 0, -0.0003])                                                         # the panel's centre: just inside
quad = [tuple(c + np.array(o)) for o in ((-0.01, -0.01, 0), (0.01, -0.01, 0), (0.01, 0.01, 0), (-0.01, 0.01, 0))]
for name in ("orig", "panel"):
    me = bpy.data.meshes.new(name); me.from_pydata(quad, [], [(0, 1, 2, 3)]); me.update()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
panel = bpy.data.objects["panel"]; weights(panel, arm, lambda c: {"root": 1.0})
v = api.fit_validate("measure", piece="p", bound="panel", original="orig", poses=[{"name": "rest"}], roles={"p": "metal"}, body="body")
p = v["poses"][0]["pieces"]["p"]
res({"crossings": p.get("surface_crossings"), "inside": p.get("inside_vertices"), "verdict": p["judge"]["verdict"]})
''', goldens)
    assert d["inside"] == 0 and d["crossings"] > 0 and d["verdict"] == "FAIL", d


def test_g05_3_the_positive_control_is_capped_so_a_rivet_straddles_the_skin(goldens):
    d = run(PANEL + '''
rivet = load_obj(GOLD + "/C14_controls/rivet.obj", "rivet"); orig = load_obj(GOLD + "/C14_controls/rivet.obj", "orig")
weights(rivet, arm, lambda c: {"root": 1.0})
v = api.fit_validate("measure", piece="p", bound="rivet", original="orig", poses=[{"name": "rest"}], roles={"p": "metal"}, body="body")
res(v["crossing_control"])
''', goldens)
    sag = J(goldens, "C05_clearance/expected.json")["sphere"]["tol_m"]               # the mesh sphere lies up to 2 sag inside the analytic one
    want = J(goldens, "C14_controls/expected.json")["capped_half_extent"]["push_m"]
    assert d["ok"] is True and d["surface_crossings"] >= 4 and d["push_m"] == pytest.approx(want, abs=sag), d
