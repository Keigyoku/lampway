# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_parity's comparison maths (specs/ue_parity/contracts/ue_parity.md §5, §10): per-class metrics with the contract's
tolerances, on synthetic pairs whose answer is known (T-HAR-04), the capture-format checks (T-HAR-03) and the camera map
(T-HAR-02). Pure numpy: no UE and no Blender."""

import math
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.ue import parity_metrics as PM  # noqa: E402


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_inv(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def synthetic():
    """A 96x96 'render': COL patches on the top row, SHD discs' squares, NRM bumps lit from +Y, LGT probes, an object mask."""
    img = np.zeros((96, 96, 4))
    img[..., 3] = 0.0
    regions = {"COL": [], "SHD": [], "NRM": [], "LGT": []}
    for i, v in enumerate((0.02, 0.18, 0.5, 0.9)):                                 # chart patches
        x0 = 4 + i * 22
        img[4:20, x0:x0 + 16, :3] = v
        regions["COL"].append([x0 + 2, 6, x0 + 14, 18])
    for i, v in enumerate((0.9, 0.6, 0.3)):                                        # furnace spheres (flat stand-ins)
        x0 = 8 + i * 28
        img[26:42, x0:x0 + 16, :3] = v
        regions["SHD"].append([x0 + 2, 28, x0 + 14, 40])
    for i in range(3):                                                             # bumps: brighter on the +Y (upper) half
        x0 = 8 + i * 28
        img[48:56, x0:x0 + 16, :3] = 0.6
        img[56:64, x0:x0 + 16, :3] = 0.2
        regions["NRM"].append({"rect": [x0, 48, x0 + 16, 64], "axis": "y"})
    img[70:90, 10:86, :3] = 0.4                                                    # the lit plane
    regions["LGT"] = [[x, y] for x in (20, 48, 76) for y in (74, 80, 86)]
    img[2:92, 2:94, 3] = 1.0
    return img, regions


def test_har04_identical_pairs_pass_every_class():
    a, regions = synthetic()
    rep = PM.compare(a, a.copy(), regions, display=srgb)
    assert {c: r["verdict"] for c, r in rep["classes"].items()} == {"COL": "pass", "SHD": "pass", "NRM": "pass", "LGT": "pass", "GEO": "pass",
                                                                    "PST": "report", "TEX": "report"}


def test_har04_each_synthetic_error_fails_exactly_its_class():
    a, regions = synthetic()
    # a 1-code display offset on the chart: under the display tolerance (3 codes) but over the linear one (1 %)
    one = a.copy()
    one[4:20, :, :3] = srgb_inv(srgb(one[4:20, :, :3]) + 1 / 255)
    # a flipped green: every bump lit on the wrong half
    flip = a.copy()
    flip[48:56, :, :3], flip[56:64, :, :3] = a[56:64, :, :3], a[48:56, :, :3]
    # a 2 % light error on the lit plane
    light = a.copy()
    light[70:90, 10:86, :3] *= 1.02
    # a 4 % energy error on the furnace
    shd = a.copy()
    shd[26:42, :, :3] *= 1.04
    for ue, cls in ((one, "COL"), (flip, "NRM"), (light, "LGT"), (shd, "SHD")):
        rep = PM.compare(a, ue, regions, display=srgb)
        failed = sorted(c for c, r in rep["classes"].items() if r["verdict"] == "fail")
        assert failed == [cls], (cls, failed, rep["classes"][cls])
    assert PM.compare(a, one, regions, display=srgb)["classes"]["COL"]["display_max_codes"] <= 1.01


def test_geo_silhouette_and_the_edge_band():
    a, regions = synthetic()
    b = a.copy()
    b[2:92, 2:6, 3] = 0.0                                                          # four columns of silhouette lost
    rep = PM.compare(a, b, regions, display=srgb)
    assert rep["classes"]["GEO"]["verdict"] == "fail" and rep["classes"]["GEO"]["silhouette_iou"] < 0.995
    assert rep["classes"]["PST"]["verdict"] == "report" and rep["classes"]["PST"]["edge_band_px"] == 3


def test_col_without_a_display_cube_is_needs_decision_for_its_display_half():
    a, regions = synthetic()
    rep = PM.compare(a, a.copy(), regions, display=None)
    assert rep["classes"]["COL"]["verdict"] == "pass" and rep["classes"]["COL"]["display"] == "needs_decision"


def test_de2000_reference_pairs():
    """CIEDE2000 against the published test data (Sharma, Wu and Dalal 2005, pairs 1, 7 and 17)."""
    lab1 = np.array([[50.0, 2.6772, -79.7751], [50.0, 0.0, 0.0], [50.0, 2.5, 0.0]])
    lab2 = np.array([[50.0, 0.0, -82.7485], [50.0, -1.0, 2.0], [73.0, 25.0, -18.0]])
    np.testing.assert_allclose(PM.de2000(lab1, lab2), [2.0425, 2.3669, 27.1492], atol=1e-4)


def test_har03_capture_format_checks(tmp_path):
    exr_bytes = b"\x76\x2f\x31\x01" + b"\0" * 60
    png = tmp_path / "capture.png"
    png.write_bytes(exr_bytes)
    with pytest.raises(PM.CaptureError, match="mislabelled"):
        PM.check_capture(png, linear=True)
    hdr = tmp_path / "capture.hdr"
    hdr.write_bytes(b"#?RADIANCE\n" + b"\0" * 20)
    with pytest.raises(PM.CaptureError, match="1 % quantisation"):
        PM.check_capture(hdr, linear=True)
    good = tmp_path / "capture.exr"
    good.write_bytes(exr_bytes)
    assert PM.check_capture(good, linear=True) == "exr"


def test_har02_lens_to_ue_fov_and_identical_patch_centres():
    assert round(PM.ue_hfov_deg(50.0, 36.0), 3) == 39.598
    w = h = 768
    pts = np.array([[0.0, 3.0, 0.0], [0.4, 3.0, 0.2], [-0.5, 3.0, -0.3]])           # camera at the origin looking +Y, Z up
    bl = PM.project_blender(pts, lens_mm=50.0, sensor_mm=36.0, width=w, height=h)
    ue = PM.project_ue(pts, hfov_deg=PM.ue_hfov_deg(50.0, 36.0), width=w, height=h)
    np.testing.assert_allclose(bl, ue, atol=1e-6)
    assert np.allclose(bl[0], [w / 2, h / 2])
