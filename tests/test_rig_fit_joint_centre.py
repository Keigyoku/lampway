# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact canon11 B8 mean-hit centering; an absent correction is functional RED."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / "src/scripts/mixar/modules/lampway_tools/features/rig_fit_measure.py"


def centre(point, along, ray_cast, finger=False):
    if not PATH.exists():
        return {"position": list(point), "passes": [], "skipped": "centering unavailable"}
    spec = importlib.util.spec_from_file_location("joint_measure", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.centre(point, along, ray_cast, finger=finger)


def circle(origin, direction, reach):
    a = np.dot(direction[:2], direction[:2])
    b = 2 * np.dot(origin[:2], direction[:2])
    c = np.dot(origin[:2], origin[:2]) - 0.04**2
    disc = b*b - 4*a*c
    if disc < 0:
        return None
    roots = [v for v in ((-b-np.sqrt(disc))/(2*a), (-b+np.sqrt(disc))/(2*a)) if 0 <= v <= reach]
    return origin + min(roots)*direction if roots else None


def test_circle_retains_exact_three_pass_mean_rule_and_along_coordinate():
    result = centre((0.01, 0, 0.7), (0, 0, 1), circle)
    assert np.allclose(result["position"], (0.00125, 0, 0.7), atol=1e-10), result
    assert [p["hits"] for p in result["passes"]] == [16, 16, 16]
    assert result["skipped"] is None


@pytest.mark.parametrize("finger,hits,moves", [(False,11,False),(False,12,True),(True,9,False),(True,10,True)])
def test_open_ring_threshold_is_an_actual_refusal(finger, hits, moves):
    count = 0
    def cast(origin, direction, reach):
        nonlocal count
        index = count % 16
        count += 1
        return np.asarray((0.02,0,origin[2])) if index < hits else None
    result = centre((0,0,0.7), (0,0,1), cast, finger=finger)
    assert (result["position"][0] > 0) == moves, result
    assert bool(result["skipped"]) != moves


@pytest.mark.parametrize("along", [(0,0,0),(float("nan"),0,1)])
def test_undefined_axis_refuses(along):
    with pytest.raises(ValueError, match="axis"):
        centre((0,0,0), along, circle)


def test_a_ring_that_opens_after_a_pass_retains_the_base_measurement():
    calls = 0
    def cast(origin, direction, reach):
        nonlocal calls
        calls += 1
        return np.asarray((0.02,0,origin[2])) if calls <= 16 else None
    result = centre((0.01,0,0.7), (0,0,1), cast)
    assert result["position"] == [0.01,0,0.7] and result["displacement_m"] == 0, result
    assert result["skipped"]
