# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""material_palette (specs/resources/material_palette.md): named area and accent colours from an image (alpha-aware, deterministic), locked colours, Principled
materials on request, and a CIELAB palette distance so colour drift has a number. Pure numpy + Pillow (the features/palette.py module), exercised through the
api door in the real binary."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from mixar.modules.lampway_tools.features import palette as PAL  # noqa: E402


def three_colour(path, alpha_border=False):
    a = np.zeros((100, 100, 4), dtype=np.uint8)
    a[..., :3] = (128, 128, 128)
    a[:, :15, :3] = (200, 30, 30)                            # 15 % red
    rng = np.random.default_rng(3)                           # 0.5 % small saturated blue accent, speckled over many 5-bit bins (no single bin stands out)
    a[45:55, 45:50, :3] = np.stack([rng.integers(0, 70, (10, 5)), rng.integers(20, 90, (10, 5)), rng.integers(170, 256, (10, 5))], axis=-1)
    a[..., 3] = 255
    if alpha_border:
        b = np.zeros((140, 140, 4), dtype=np.uint8)
        b[20:120, 20:120] = a
        b[:20, :, :3] = (0, 255, 0)                          # a green background that is fully transparent
        a = b
    Image.fromarray(a, "RGBA").save(path)
    return path


def test_notable_keeps_the_small_accent_that_kmeans_can_merge(tmp_path):
    p = three_colour(tmp_path / "three.png")
    notable = PAL.extract(str(p), n=3, method="notable")
    assert len(notable["palette"]) == 3 and any(c["kind"] == "accent" and c["srgb"][2] > 0.8 for c in notable["palette"])
    assert any(abs(c["srgb"][0] - 0.5) < 0.05 and c["kind"] == "area" for c in notable["palette"])
    km = PAL.extract(str(p), n=3, method="kmeans")
    assert len(km["palette"]) == 3                              # kmeans may merge the accent into a neighbour: documented, not asserted


def test_locked_colours_and_determinism(tmp_path):
    p = three_colour(tmp_path / "three.png")
    a = PAL.extract(str(p), n=4, locked=[{"name": "Bronze", "hex": "#a0702c"}], seed=0)
    b = PAL.extract(str(p), n=4, locked=[{"name": "Bronze", "hex": "#a0702c"}], seed=0)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    locked = [c for c in a["palette"] if c["kind"] == "locked"]
    assert locked == [dict(locked[0], name="Bronze", hex="#a0702c")]
    with pytest.raises(PAL.PaletteError, match="more than n"):
        PAL.extract(str(p), n=2, locked=[{"name": "a", "hex": "#000000"}, {"name": "b", "hex": "#ffffff"}, {"name": "c", "hex": "#ff0000"}])


def test_transparent_pixels_do_not_enter_the_palette(tmp_path):
    p = three_colour(tmp_path / "alpha.png", alpha_border=True)
    out = PAL.extract(str(p), n=3)
    assert abs(sum(c["coverage"] for c in out["palette"]) - 1.0) < 1e-6
    assert not any(c["srgb"][1] > 0.8 and c["srgb"][0] < 0.2 for c in out["palette"])        # no pure green from the transparent border
    clear = tmp_path / "clear.png"
    Image.fromarray(np.zeros((8, 8, 4), np.uint8), "RGBA").save(clear)
    with pytest.raises(PAL.PaletteError, match="no pixels above alpha_min"):
        PAL.extract(str(clear), n=3)


def test_compare_to_itself_is_zero_and_a_hue_shift_is_far(tmp_path):
    a = np.zeros((64, 64, 4), np.uint8); a[..., 3] = 255                      # a saturated image: a grey one barely moves under a hue shift
    for i, c in enumerate([(200, 40, 40), (40, 180, 60), (50, 70, 210), (220, 190, 40)]):
        a[i * 16:(i + 1) * 16, :, :3] = c
    p = tmp_path / "colours.png"
    Image.fromarray(a, "RGBA").save(p)
    img = Image.open(p).convert("RGB")
    h, s, v = img.convert("HSV").split()
    shifted = Image.merge("HSV", (h.point(lambda x: (x + int(30 / 360 * 255)) % 256), s, v)).convert("RGB")
    shifted.save(tmp_path / "shifted.png")
    same = PAL.extract(str(p), n=3, compare_to=str(p))
    far = PAL.extract(str(p), n=3, compare_to=str(tmp_path / "shifted.png"))
    assert same["distance"]["mean_lab"] == 0.0 and far["distance"]["mean_lab"] > 10


def test_pantone_is_refused_with_the_licence_sentence(tmp_path):
    p = three_colour(tmp_path / "three.png")
    with pytest.raises(PAL.PaletteError, match="does not include or redistribute proprietary Pantone libraries"):
        PAL.extract(str(p), n=3, pms=True)


def test_the_api_tool_writes_the_json_the_swatch_and_materials(tmp_path):
    from wave6_support import go, one
    three_colour(tmp_path / "plate.png")
    d = one(go(tmp_path, '''
res = call("material_palette", image="plate.png", n=3, make_materials=True)
mats = sorted(m.name for m in bpy.data.materials if m.name.startswith("PAL_"))
again = call("material_palette", image="plate.png", n=3, make_materials=True)
mats2 = sorted(m.name for m in bpy.data.materials if m.name.startswith("PAL_"))
outside = call("material_palette", image="/etc/hostname")
print("RESULT", json.dumps({"res": res, "mats": mats, "mats2": mats2, "outside": outside,
                            "files": sorted(os.listdir(os.path.join(root, "palettes")))}))
'''))
    res = d["res"]
    assert res["ok"] and len(res["materials"]) == 3 and d["mats"] == sorted(res["materials"]) and len(d["mats2"]) == 6       # never overwrites: a suffix
    assert d["files"] == ["plate.palette.json", "plate.swatch.png"]
    assert d["outside"]["ok"] is False and "outside the project root" in d["outside"]["error"]
