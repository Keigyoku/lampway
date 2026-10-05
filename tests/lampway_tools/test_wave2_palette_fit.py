# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""palette_fit (shelf/palette_fit.md section 10): the per-class Hue/Saturation/Value fit of the studio colours to the mesh-paint albedo, measured and applied in LINEAR space."""

import colorsys
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import palette_fit as PF  # noqa: E402

# the recorded fit (scratch palette_A_to_albedo.json) as (tripo_hsv, target_hsv) per class; the multipliers it recorded are the pinned expectation
RECORDED = {"gold": ((0.12, 0.742, 0.522), (0.12, 0.726, 0.682), 0.978, 1.306), "plate": ((0.60, 0.696, 0.365), (0.60, 0.565, 0.247), 0.812, 0.677)}


def _srgb(lin):
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.maximum(lin, 0), 1 / 2.4) - 0.055)


def _rgb(hsv, space):
    rgb = np.array(colorsys.hsv_to_rgb(*hsv))            # the HSV is meant in `space`
    return _srgb(rgb) if space == "linear" else rgb      # what the PNG stores


def _scene(tmp_path, classes, space="linear", size=64):
    """studio / albedo / masks: class k owns the horizontal band k; each band is one flat colour."""
    studio = np.zeros((size, size, 3))
    albedo = np.zeros((size, size, 3))
    md = tmp_path / "masks"
    md.mkdir()
    band = size // len(classes)
    for k, (name, (s_hsv, a_hsv)) in enumerate(classes.items()):
        studio[k * band:(k + 1) * band] = _rgb(s_hsv, space)
        albedo[k * band:(k + 1) * band] = _rgb(a_hsv, space)
        m = np.zeros((size, size), np.uint8)
        m[k * band:(k + 1) * band] = 255
        Image.fromarray(m).save(md / f"mask_{name}.png")
    Image.fromarray((np.clip(studio, 0, 1) * 255 + .5).astype(np.uint8)).save(tmp_path / "studio.png")
    Image.fromarray((np.clip(albedo, 0, 1) * 255 + .5).astype(np.uint8)).save(tmp_path / "albedo.png")
    return str(tmp_path / "studio.png"), str(tmp_path / "albedo.png"), str(md)


def test_the_fit_reproduces_the_recorded_multipliers(tmp_path):
    studio, albedo, masks = _scene(tmp_path, {k: (v[0], v[1]) for k, v in RECORDED.items()}, size=128)
    res = PF.fit(studio, albedo, masks, list(RECORDED), space="linear", min_texels=100)
    for k, (_a, _b, sat, val) in RECORDED.items():
        row = res["palette"][k]
        assert row["sat_mul"] == pytest.approx(sat, abs=0.02) and row["val_mul"] == pytest.approx(val, abs=0.02), (k, row)
        assert abs(row["hue_shift"]) < 0.02


def test_feeding_the_studio_base_as_the_albedo_is_the_identity(tmp_path):                 # the falsifier
    classes = {"gold": ((0.12, 0.74, 0.5), (0.12, 0.74, 0.5)), "plate": ((0.6, 0.7, 0.37), (0.6, 0.7, 0.37))}
    studio, _albedo, masks = _scene(tmp_path, classes)
    res = PF.fit(studio, studio, masks, list(classes), space="linear", min_texels=100)
    for row in res["palette"].values():
        assert row["hue_shift"] == pytest.approx(0, abs=1e-6) and row["sat_mul"] == pytest.approx(1, abs=1e-6) and row["val_mul"] == pytest.approx(1, abs=1e-6)
    assert max(res["residual"].values()) < 1e-6


def test_measuring_in_linear_leaves_a_smaller_residual_than_measuring_in_srgb(tmp_path):
    # the consumer (Blender's Hue/Saturation node) works on LINEAR colour: the target is the studio colour x 1.3 in linear light
    rng = np.random.default_rng(3)
    size = 64
    lin = rng.uniform(0.05, 0.5, (size, size, 1)) * np.ones((1, 1, 3))
    studio_png = (np.clip(_srgb(lin), 0, 1) * 255 + .5).astype(np.uint8)
    albedo_png = (np.clip(_srgb(lin * 1.3), 0, 1) * 255 + .5).astype(np.uint8)
    Image.fromarray(studio_png).save(tmp_path / "s.png")
    Image.fromarray(albedo_png).save(tmp_path / "a.png")
    md = tmp_path / "m"
    md.mkdir()
    Image.fromarray(np.full((size, size), 255, np.uint8)).save(md / "mask_gold.png")
    lin_fit = PF.fit(str(tmp_path / "s.png"), str(tmp_path / "a.png"), str(md), ["gold"], space="linear", min_texels=100)
    srgb_fit = PF.fit(str(tmp_path / "s.png"), str(tmp_path / "a.png"), str(md), ["gold"], space="srgb", min_texels=100)
    assert lin_fit["residual"]["gold"] < srgb_fit["residual"]["gold"]


def test_a_missing_mask_refuses_and_a_tiny_one_is_skipped_with_a_reason(tmp_path):
    studio, albedo, masks = _scene(tmp_path, {"gold": ((0.1, 0.7, 0.5), (0.1, 0.7, 0.6))})
    with pytest.raises(PF.PaletteError, match="no mask_leather.png: run material_masks"):
        PF.fit(studio, albedo, masks, ["gold", "leather"], min_texels=100)
    Image.fromarray(np.eye(64, dtype=np.uint8) * 255).save(Path(masks) / "mask_leather.png")      # 64 texels
    res = PF.fit(studio, albedo, masks, ["gold", "leather"], min_texels=1000)
    assert "leather" not in res["palette"] and "64 texels" in res["skipped"]["leather"]
    assert "gold" in res["palette"] and "gold" not in res["skipped"]


def test_images_of_different_size_are_resampled_to_the_larger_and_the_receipt_says_so(tmp_path):
    studio, albedo, masks = _scene(tmp_path, {"gold": ((0.1, 0.7, 0.5), (0.1, 0.7, 0.6))}, size=64)
    Image.open(albedo).resize((32, 32)).save(albedo)
    res = PF.fit(studio, albedo, masks, ["gold"], min_texels=100)
    assert any("resampled" in n for n in res["notes"])


def test_write_params_matches_the_consumer_shape_and_refuses_metal_on_cloth(tmp_path):
    palette = {"gold": {"hue_shift": 0.03, "sat_mul": 0.978, "val_mul": 1.3}, "red": {"hue_shift": 0.0, "sat_mul": 1.0, "val_mul": 0.9}}
    out = tmp_path / "pbr/live_material_params.json"
    res = PF.write_params(palette, ["gold", "red"], str(out), metal_zero_on=["red"])
    data = json.loads(out.read_text())
    assert data["order"] == ["gold", "red"] and data["palette_hsv"]["gold"] == [pytest.approx(0.53), 0.978, 1.3] and data["metal_zero_on"] == ["red"]
    assert "normal_strength_live" in data and res["params"] == str(out)
    with pytest.raises(PF.PaletteError, match="red is cloth: metallic must be 0 there"):
        PF.write_params(palette, ["gold", "red"], str(tmp_path / "x.json"), metal_zero_on=[])


def test_apply_the_palette_the_way_blenders_node_does(tmp_path):
    out = PF.apply_palette(np.array([[0.2, 0.1, 0.05]]), (0.5, 1.0, 2.0))             # no hue shift, value x2 in linear
    assert out == pytest.approx(np.array([[0.4, 0.2, 0.1]]))


# ---- the live half runs in the real binary (headless)
LIVE = r'''
import json, sys, tempfile, os
import bpy, numpy as np
from PIL import Image
sys.path.insert(0, os.environ["LW_SRC"])
from mixar.modules.lampway_tools import palette_live as PL
tmp = tempfile.mkdtemp()
for c in ("gold", "red"):
    Image.fromarray(np.full((8, 8), 255, np.uint8)).save(os.path.join(tmp, f"mask_{c}.png"))
bpy.ops.wm.read_factory_settings(use_empty=True)
mat = bpy.data.materials.new("textured_chest"); mat.use_nodes = True
palette = {"gold": {"hue_shift": 0.03, "sat_mul": 0.978, "val_mul": 1.3}, "red": {"hue_shift": 0.0, "sat_mul": 1.0, "val_mul": 0.9}}
PL.apply("textured_chest", tmp, palette, ["gold", "red"])
PL.apply("textured_chest", tmp, palette, ["gold", "red"])           # idempotent
nt = bpy.data.materials["textured_chest_pal"].node_tree
labels = sorted(n.label for n in nt.nodes if n.label.startswith("PAL:"))
PL.set_slider("textured_chest_pal", "gold", val=1.1)
back = PL.read("textured_chest_pal")
orig_nodes = sorted(n.name for n in bpy.data.materials["textured_chest"].node_tree.nodes)
print("RESULT " + json.dumps({"labels": labels, "gold_val": back["gold"]["val_mul"], "gold_hue": back["gold"]["hue_shift"], "source_untouched": not any(n.label.startswith("PAL:") for n in bpy.data.materials["textured_chest"].node_tree.nodes)}))
'''


def test_apply_live_twice_leaves_one_node_set_and_read_live_returns_the_slider():
    import os
    from blender_run import run_script
    run = run_script(LIVE, env={"LW_SRC": str(Path(__file__).resolve().parents[2] / "src/scripts")}, timeout=240)
    assert run.rc == 0, run.out[-1500:]
    r = run.results[-1]
    assert r["labels"].count("PAL: gold hsv") == 1 and r["labels"].count("PAL: red mix") == 1 and len([l for l in r["labels"] if l.endswith(" hsv")]) == 2
    assert r["gold_val"] == 1.1 and abs(r["gold_hue"] - 0.03) < 1e-3 and r["source_untouched"]


def test_the_real_chest_reproduces_the_recorded_fit_as_the_median_in_srgb():
    """The measured answer to the contract's open question: on the user's chest (shelf pieces; skipped when the shelf is not configured) the recorded multipliers are the sRGB MEDIAN."""
    import os
    shelf = os.environ.get("LAMPWAY_SHELF_SCRATCH")
    if not shelf or not (Path(shelf) / "tripo_texture/palette_A_to_albedo.json").exists():
        pytest.skip("LAMPWAY_SHELF_SCRATCH not set to the shelf's scratch folder")
    import tempfile
    Image.MAX_IMAGE_PIXELS = None
    rec = json.loads((Path(shelf) / "tripo_texture/palette_A_to_albedo.json").read_text())
    base = next((Path(shelf) / "tripo_texture/pbrA").glob("pbrA_BaseColor_*.png"), None)
    md = Path(shelf) / "relief_proj/p17_albedo_4k"
    if base is None or not md.exists():
        pytest.skip("the chest's pbrA base or p17 masks are not on this shelf")
    tmp = Path(tempfile.mkdtemp()) / "studio4k.png"
    Image.open(base).convert("RGB").resize((4096, 4096), Image.LANCZOS).save(tmp)
    classes = ["gold", "plate", "red", "linen", "leather", "embroidery"]
    res = {sp: PF.fit(str(tmp), str(md / "v3_colour_atlas.png"), str(md), classes, "median", sp) for sp in ("srgb", "linear")}
    err = {sp: max(max(abs(r["palette"][c]["sat_mul"] - rec[c]["sat_mul"]), abs(r["palette"][c]["val_mul"] - rec[c]["val_mul"])) for c in classes) for sp, r in res.items()}
    assert err["srgb"] < 0.25 and err["linear"] > 1.0, err
    assert abs(res["srgb"]["palette"]["plate"]["val_mul"] - rec["plate"]["val_mul"]) < 0.02 and abs(res["srgb"]["palette"]["gold"]["val_mul"] - rec["gold"]["val_mul"]) < 0.02
