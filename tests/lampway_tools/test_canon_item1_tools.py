# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 1 at the TOOL level: the Lampway tools the plan names now measure with canon_geom.

* pipeline/validate.rigid_fit is canon 02's similarity fit (p95, collinear / too-few / non-finite refusals);
* uv_islands (lampway_uv_score) rasterises half-open: golden C09 reads overlap 0, not the inclusive rule's 0.0017;
* garment_clearance and rig.pose_test sign a distance by the angle-weighted pseudonormal: golden C05's point beside the
  needle apex is outside (the nearest face's normal said inside for some side of the apex).
Each of these was observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from mixar.modules.lampway_tools.pipeline import validate as V  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def test_validate_rigid_fit_is_the_canon_similarity_with_p95_and_refusals(goldens):
    inp = J(goldens, "C01_rigid/input.json")
    f = V.rigid_fit(np.array(inp["P"]), np.array(inp["Q_one_vertex_5mm"]))
    assert 0.004 <= f["max_m"] <= 0.005 and f["p95_m"] < f["max_m"] and f["scale"] == pytest.approx(1.07, abs=1e-3)
    line = np.array([[0.0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]])
    with pytest.raises(ValueError, match="line"):
        V.rigid_fit(line, line + 1)
    with pytest.raises(ValueError, match="at least 3"):
        V.rigid_fit(line[:2], line[:2])


def test_uv_score_measures_golden_c09_with_the_half_open_raster(goldens):
    r = run_script(PRE + LOAD_OBJ + f'''
from mixar.modules.lampway_tools.features import uv_islands as UI
rows = {{n: UI.measure_object(load_obj({str(goldens)!r} + "/C09_uv/" + n + ".obj", n), 1024) for n in ("three_islands", "overlap")}}
res(rows)
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    rows = r.results[-1]
    e = J(goldens, "C09_uv/expected.json")
    t = rows["three_islands"]
    assert t["overlap"] == 0.0, t
    assert t["utilization"] == pytest.approx(e["three_islands"]["utilization_1024"], abs=1e-4) and t["islands"] == 3
    assert t["flipped"] == pytest.approx(1 / 3, abs=1e-4)
    o = rows["overlap"]
    assert o["overlap"] == pytest.approx(e["overlap"]["overlap_fraction_of_covered"], abs=1e-4) and o["utilization"] == pytest.approx(0.3125, abs=1e-4)


SPIKE = r'''
arm = armature(bones=(("root", (0, 0, 0), (0, 0, 1), None),))
body = load_obj(GOLD + "/C05_clearance/spike.obj", "body"); weights(body, arm, lambda c: {})
q = json.load(open(GOLD + "/C05_clearance/queries.json"))["spike_point"]
sx, sy, sz = q
apex = [(sx, sy, sz), (-sx, sy, sz), (sy, sx, sz), (sy, -sx, sz)]          # round the apex: the nearest point is the apex
low = [(0.1, 0, 0.0), (-0.1, 0, 0.0), (0, 0.1, 0.0), (0, -0.1, 0.0)]       # far beside the base, outside (keeps the piece centred)
piece = points("piece", apex + low)
'''


def test_garment_clearance_signs_the_spike_apex_points_outside(goldens):
    r = run_script(PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + SPIKE + '''
out = api.garment_clearance("piece", "body", "rig", clearance_target_m=0.0)
res(out)
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    row = r.results[-1]["poses"][0]
    assert row["penetrating_vertices"] == 0 and row["min_clearance_m"] > 0, row


def test_pose_test_clearance_signs_the_spike_apex_points_outside(goldens):
    r = run_script(PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + SPIKE + '''
from mixar.modules.lampway_tools.features import rig
out = rig.pose_test("rig", "piece", [{"name": "rest"}], clearance_body="body")
res(out["poses"][0]["clearance"])
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    c = r.results[-1]
    assert c["penetrating_vertices"] == 0 and c["min_m"] > 0, c
