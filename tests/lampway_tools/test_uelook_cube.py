# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look cube is DATA from the UE side (the captain's ruling, 2026-10-06): the profile names the cube
(``tonemap_cube``) and its sidecar (``tonemap_cube_meta``: engine version, tonemapper settings, generator version, sha256, grid,
domain, shaper). The validator answers valid / missing / mismatch and, for anything but valid, names the fix: "generate the cube
on the UE side, then point UE Look at it". Pure: a SYNTHETIC cube written by the test."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
import uelook_support as U  # noqa: E402
from mixar.modules.lampway_tools.ue import cube as CB  # noqa: E402
from mixar.modules.lampway_tools.ue import profile as PR  # noqa: E402

FIX = "generate the cube on the UE side, then point UE Look at it"


def test_a_synthetic_cube_with_its_sidecar_is_valid_and_only_its_path_and_hash_are_kept(tmp_path):
    p = PR.load(U.profile_with_cube(tmp_path))
    v = CB.validate(p)
    assert v["state"] == "valid", v
    assert v["sha256"] == json.loads(Path(p["tonemap_cube_meta"]).read_text())["cube"]["sha256"]
    assert v["engine_version"] == "5.8.2" and v["generator"] == {"name": "synthetic test generator", "version": "0.0-test"}
    assert v["size"] == 32 and v["shaper"] == U.SHAPER
    assert set(v) <= {"state", "why", "fix", "cube", "meta", "sha256", "engine_version", "generator", "size", "shaper", "domain"}
    assert all(not isinstance(x, list) or len(x) < 10 for x in v.values())              # nothing of the cube's data is carried


def test_the_shipped_profile_names_no_cube_and_is_missing_with_the_fix():
    v = CB.validate(PR.load(PR.DEFAULT_PROFILE))
    assert v["state"] == "missing" and FIX in v["fix"] and "tonemap_cube" in v["why"]


@pytest.mark.parametrize("break_it, state, why", [
    (lambda c, m: c.unlink(), "missing", "the cube"),
    (lambda c, m: m.unlink(), "missing", "the sidecar"),
    (lambda c, m: c.write_text(c.read_text().replace(" ", "  ", 1)), "mismatch", "sha256"),         # one byte more: the same values
    (lambda c, m: (U.write_cube(c, size=16), U.write_meta(m, c, cube__size=16)), "mismatch", "r.LUT.Size"),
    (lambda c, m: (U.write_cube(c, rows=100), U.write_meta(m, c)), "mismatch", "rows"),
    (lambda c, m: (U.write_cube(c, domain=((0, 0, 0), (2, 2, 2))), U.write_meta(m, c)), "mismatch", "domain"),
    (lambda c, m: U.write_meta(m, c, engine__version="5.7.4"), "mismatch", "engine version"),
    (lambda c, m: U.write_meta(m, c, tonemapper__film__toe=0.6), "mismatch", "tonemapper"),
    (lambda c, m: m.write_text("{not json"), "mismatch", "sidecar"),
    (lambda c, m: U.write_meta(m, c, schema="other/1"), "mismatch", "lampway.ue-cube-meta/1"),
])
def test_every_missing_or_bad_piece_is_refused_with_the_fix(tmp_path, break_it, state, why):
    p = PR.load(U.profile_with_cube(tmp_path))
    c, m = Path(p["tonemap_cube"]), Path(p["tonemap_cube_meta"])
    break_it(c, m)
    v = CB.validate(p)
    assert v["state"] == state and why in v["why"] and FIX in v["fix"], v
    with pytest.raises(CB.CubeError, match=FIX):
        CB.require(p)


def test_the_profile_carries_the_two_named_fields_and_refuses_a_bad_type(tmp_path):
    p = json.loads(PR.DEFAULT_PROFILE.read_text())
    assert p["tonemap_cube"] is None and p["tonemap_cube_meta"] is None and "tonemap_cube" in p["notes"]
    p["tonemap_cube"] = 3
    q = tmp_path / "bad.json"
    q.write_text(json.dumps(p))
    with pytest.raises(PR.ProfileError, match="tonemap_cube is a path or null"):
        PR.load(q)
