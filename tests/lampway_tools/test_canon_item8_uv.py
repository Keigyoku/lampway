# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 8 (canon 13): uv.uv_report (the report of lampway_uv_unwrap) measures with the ONE definition -
canon_geom's half-open raster at the canon's resolution and its corner-joined islands - so it agrees with uv_islands /
lampway_uv_score on golden C09. Observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from test_wave3_weights import PRE  # noqa: E402


def test_uv_report_and_uv_score_agree_on_golden_c09(goldens):
    r = run_script(PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + '''
from mixar.modules.lampway_tools.features import uv as U, uv_islands as UI
out = {}
for n in ("three_islands", "overlap"):
    ob = load_obj(GOLD + "/C09_uv/" + n + ".obj", n)
    a, b = U.uv_report(ob), UI.measure_object(ob, 1024)
    out[n] = {"coverage": a["coverage"], "overlap": a["overlap_fraction"], "islands": a["islands"], "score_util": b["utilization"], "score_overlap": b["overlap"], "score_islands": b["islands"]}
res(out)
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    e = J(goldens, "C09_uv/expected.json")
    t, o = r.results[-1]["three_islands"], r.results[-1]["overlap"]
    assert t["overlap"] == 0.0 and t["coverage"] == pytest.approx(e["three_islands"]["utilization_1024"], abs=1e-4) and t["islands"] == 3, t
    assert (t["coverage"], t["overlap"], t["islands"]) == (t["score_util"], t["score_overlap"], t["score_islands"])
    assert o["overlap"] == pytest.approx(e["overlap"]["overlap_fraction_of_covered"], abs=1e-4) and o["overlap"] == o["score_overlap"], o
