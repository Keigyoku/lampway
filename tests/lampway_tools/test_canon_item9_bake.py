# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 9 (canon 14 B.3): the bake's `auto` cage and ray come from the MEASURED LP<->HP distances - the cage
encloses the HP's greatest height above the LP, the ray reaches the cage plus the HP's greatest depth below it - and an explicit cage
under the median distance is refused. Golden C10 (the bump, and the bump sunk 1 cm). Plan only: no Cycles runs here."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import goldens  # noqa: E402,F401
from test_canon_item6_tools import run  # noqa: E402

BODY = '''
from mixar.modules.lampway_tools.features import bake as BK
low = load_obj(GOLD + "/C10_bake/lp_plane.obj", "low")
high = load_obj(GOLD + "/C10_bake/hp_bump.obj", "high")
a = BK.plan("high", "low", ["normal"], 256, None, None, None, 4, "gl", False, "bake", False, root)
high.location.z = -0.01; bpy.context.view_layer.update()
b = BK.plan("high", "low", ["normal"], 256, None, None, None, 4, "gl", False, "bake", False, root)
try:
    BK.plan("high", "low", ["normal"], 256, None, 0.004, None, 4, "gl", False, "bake", False, root); small = None
except Exception as e:
    small = str(e)
res({"a": {k: a[k] for k in ("cage_extrusion_m", "max_ray_m", "measured")}, "b": {k: b[k] for k in ("cage_extrusion_m", "max_ray_m", "measured")},
     "pad": BK.AUTO_PAD, "small": small})
'''


def test_g14_auto_cage_and_ray_come_from_the_measured_distances(goldens):
    d = run(BODY, goldens)
    pad = d["pad"]
    a, b = d["a"], d["b"]
    assert a["measured"]["height_max_m"] == pytest.approx(0.05, abs=1e-6) and a["measured"]["depth_max_m"] == pytest.approx(0.0, abs=1e-6), a
    assert a["cage_extrusion_m"] == pytest.approx(0.05 * pad, abs=1e-6) and a["max_ray_m"] == pytest.approx(0.05 * pad, abs=1e-6), a
    assert b["measured"]["height_max_m"] == pytest.approx(0.04, abs=1e-6) and b["measured"]["depth_max_m"] == pytest.approx(0.01, abs=1e-6), b
    assert b["cage_extrusion_m"] == pytest.approx(0.04 * pad, abs=1e-6) and b["max_ray_m"] == pytest.approx((0.04 + 0.01) * pad, abs=1e-6), b
    assert b["measured"]["median_m"] == pytest.approx(0.01, abs=1e-6)
    assert d["small"] and "median" in d["small"] and "0.01" in d["small"], d["small"]
