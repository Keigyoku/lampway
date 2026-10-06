# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_upscale (specs/generation/image_upscale.md): a plate raised to 2048..4096 px WITHOUT changing its content. Lanczos is the exact baseline; a model's
upscale is accepted only when it passes a faithfulness gate (structure kept, colours kept, more detail than the baseline); the original is never replaced.
Pure numpy + PIL with a recording fake for the image slot."""

import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import upscale as UP  # noqa: E402


def plate(n=1024, seed=0):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n] / n
    base = np.stack([150 + 60 * np.sin(12 * x) * np.cos(9 * y), 110 + 50 * np.cos(7 * x + 3 * y), 70 + 40 * np.sin(5 * y)], -1)
    for _ in range(40):                                                   # crisp ornament strokes: edges a repaint would move
        cx, cy, r = rng.integers(60, n - 60, 2).tolist() + [int(rng.integers(8, 30))]
        base[cy - r:cy + r, cx - 2:cx + 2] = (240, 210, 90)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "Front.png"
    plate().save(p)
    return str(p)


def _png(im):
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def test_lanczos_is_the_exact_baseline_and_never_replaces_the_original(src, tmp_path):
    before = Path(src).read_bytes()
    r = UP.upscale(src, target=4096, method="lanczos")
    assert r["size"] == [4096, 4096] and r["source_size"] == [1024, 1024] and r["gate"]["passed"] is True, r
    assert r["faithfulness"]["ssim"] > 0.99 and Path(r["file"]).exists() and Path(src).read_bytes() == before
    side = json.loads(Path(r["file"] + ".upscale.json").read_text())
    assert side["method"] == "lanczos" and side["source_sha256"] and side["output_sha256"]
    with pytest.raises(UP.UpscaleRefused, match="never overwritten"):
        UP.upscale(src, target=4096, method="lanczos")


def test_the_model_route_is_a_dry_run_until_live_and_refuses_past_its_pixel_budget(src):
    calls = []
    gen = lambda *a, **k: calls.append(a) or [b""]                        # noqa: E731
    dry = UP.upscale(src, target=2048, method="model", generate=gen)
    assert dry["dry_run"] is True and calls == []
    with pytest.raises(UP.UpscaleRefused, match="2880x2880 within 8.3 MP"):
        UP.upscale(src, target=4096, method="model", live=True, generate=gen)


def test_a_faithful_model_upscale_passes_and_a_recoloured_or_soft_one_is_rejected(src, tmp_path):
    good = plate().resize((2048, 2048), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=0))
    swapped = Image.fromarray(np.asarray(good)[..., ::-1].copy())                       # red and blue swapped: a repaint
    soft = plate().resize((512, 512), Image.BILINEAR).resize((2048, 2048), Image.BILINEAR)
    out = {}
    for name, im in (("good", good), ("swapped", swapped), ("soft", soft)):
        out[name] = UP.upscale(src, target=2048, method="model", live=True, generate=lambda *a, _im=im, **k: [_png(_im)], suffix=f"_{name}")
    assert out["good"]["gate"]["passed"] is True, out["good"]
    assert out["swapped"]["gate"]["passed"] is False and any("repainted" in r for r in out["swapped"]["gate"]["reasons"]), out["swapped"]
    assert out["soft"]["gate"]["passed"] is False and any("no detail" in r for r in out["soft"]["gate"]["reasons"]), out["soft"]


def test_a_tiny_source_and_a_bad_target_are_refused(tmp_path):
    p = tmp_path / "small.png"; plate(256).save(p)
    with pytest.raises(UP.UpscaleRefused, match="512"):
        UP.upscale(str(p), target=4096)
    big = tmp_path / "b.png"; plate().save(big)
    with pytest.raises(UP.UpscaleRefused, match="2048..4096"):
        UP.upscale(str(big), target=1000)


def test_the_tripo_route_is_a_plan_that_clicks_nothing(src):
    r = UP.upscale(src, target=4096, method="tripo")
    assert r["needs_approval"] is True and r["studio_action"] == "tripo.image" and r["plan_args"]["refs"] == [src] and "price must read back 0" in r["how"], r
    assert Path(r["plan_args"]["prompt_file"]).read_text().startswith("Reproduce this image exactly"), r


def test_the_tool_answers_through_api(tmp_path):
    from features_support import run
    plate().save(tmp_path / "Front.png")
    r = run(tmp_path, '''
print("RESULT", json.dumps({"l": call("image_upscale", image="Front.png", target=2048), "j": call("image_upscale", image="/etc/hostname")}))
''')
    assert r.rc == 0, r.out[-2000:]
    o = r.results[0]
    assert o["l"]["ok"] is True and o["l"]["size"] == [2048, 2048] and o["l"]["gate"]["passed"] is True, o["l"]
    assert o["j"]["ok"] is False and "outside the project root" in o["j"]["error"], o["j"]
