# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""seamless_tile: ONE tool for three contracts (specs/generation/image_tile.md, specs/shelf/seamless_tile.md, specs/wiki/seamless_tile.md). A tile is BUILT by
rules (motif crop, quilt, cross-fade, or a motif cell tiled exactly), never repainted by a model, and gated by measurement. The shelf's falsifier suite
(test_seamless_gate.py) is ported as cases: every defect must fail the gate, every control must pass. New here: the TONE SEAM check (a luminance step across
the wrap that the seam/step ratio cannot see, the fix the image_tile contract names). Pure numpy + PIL: no Blender needed."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import seamless_tile as ST  # noqa: E402


def lattice(n=1024, kx=9, ky=8, jitter=0.0, seed=0):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    px, py = n / kx, n / ky
    dx = (x % px) - px / 2
    dy = (y % py) - py / 2
    bead = np.exp(-(dx ** 2 + dy ** 2) / (2 * 6.0 ** 2))
    lines = np.exp(-(((x / px + y / py) % 1) - 0.5) ** 2 / 0.0008) + np.exp(-(((x / px - y / py) % 1) - 0.5) ** 2 / 0.0008)
    base = np.stack([120 + 60 * bead - 25 * np.clip(lines, 0, 1), 12 + 20 * bead, 16 + 18 * bead], -1)
    rng = np.random.default_rng(seed)
    base += rng.normal(0, 2.0, base.shape)
    return np.clip(base, 0, 255)


def grain(n=1024, seed=1):
    """A non-periodic leather-like sheet: smoothed noise at two scales, NOT seamless at its edges."""
    rng = np.random.default_rng(seed)
    from mixar.modules.lampway_tools.pipeline.imgops import gaussian
    g = gaussian(rng.normal(0, 1, (n, n)), 3.0) * 40 + gaussian(rng.normal(0, 1, (n, n)), 12.0) * 60
    return np.clip(np.stack([110 + g, 80 + 0.8 * g, 60 + 0.6 * g], -1), 0, 255)


def _save(a, p):
    Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8)).save(p)
    return str(p)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("tiles")
    src = _save(grain(1400), d / "leather_sheet.png")
    res = ST.build(src, str(d / "leather"), mode="grain", size=512)
    return d, src, res


def test_a_grain_sheet_becomes_a_tile_that_passes_its_gate_and_writes_its_files(built):
    d, src, res = built
    assert res["passed"] is True and res["failures"] == [], res
    for f in ("leather.png", "leather_mosaic.png", "leather.qa.json"):
        assert (d / f).exists(), f
    qa = json.loads((d / "leather.qa.json").read_text())
    assert qa["tool"] == ST.VERSION and qa["gate_passed"] is True and "tone_seam_pct" in qa["metrics"]


def test_the_build_is_deterministic(built, tmp_path):
    d, src, res = built
    again = ST.build(src, str(tmp_path / "leather"), mode="grain", size=512)
    assert (tmp_path / "leather.png").read_bytes() == (d / "leather.png").read_bytes()
    a, b = json.loads((tmp_path / "leather.qa.json").read_text()), json.loads((d / "leather.qa.json").read_text())
    assert a["metrics"] == b["metrics"] and a["output_sha256"] == b["output_sha256"] and again["passed"] == res["passed"]


def test_the_shelf_falsifiers_every_defect_fails_and_every_control_passes(built):
    d, src, res = built
    t = np.asarray(Image.open(d / "leather.png").convert("RGB")).astype(float)
    raw = np.asarray(Image.open(src).convert("RGB").resize(t.shape[:2][::-1], Image.LANCZOS)).astype(float)
    cases = ST.falsifier_cases(t, raw)
    misses = []
    for name, (img, per) in cases.items():
        f = ST.gate(ST.metrics(np.clip(img, 0, 255), 0.10, per))
        ok = (not f) if name.startswith("control") else bool(f)
        if not ok:
            misses.append((name, f))
    assert not misses, misses
    assert len(cases) >= 14 and "tone seam across the wrap" in cases


def test_a_tone_seam_the_ratio_cannot_see_is_rejected():
    """The image_tile contract's gate fix: a noisy tile with an 8 % luminance ramp across x keeps its seam/step ratio near 1 (the wrap difference hides in
    the noise), yet the wrap shows a tone seam. The ratio passes it; the tone-seam check must not."""
    n = 512
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 20, (n, n))
    ramp = np.linspace(0.92, 1.0, n)[None, :]
    g = (128 + noise) * ramp
    t = np.stack([g, g * 0.8, g * 0.6], -1)
    m = ST.metrics(t, 0.10, False)
    assert m["ratio_x"] <= ST.RATIO_MAX, m
    assert m["tone_seam_pct"] > ST.TONE_SEAM_MAX and "tone seam at the wrap" in ST.gate(m), m
    flat = np.stack([128 + noise, (128 + noise) * 0.8, (128 + noise) * 0.6], -1)
    assert ST.metrics(flat, 0.10, False)["tone_seam_pct"] < 1.0


def test_a_motif_cell_tiles_exactly_and_is_reproducible(tmp_path):
    cell = lattice(128, kx=1, ky=1)
    p = _save(cell, tmp_path / "cell.png")
    a = ST.build(p, str(tmp_path / "meander_a"), mode="motif_cell", size=512, cell_px=128)
    b = ST.build(p, str(tmp_path / "meander_b"), mode="motif_cell", size=512, cell_px=128)
    # The contract asks ratio <= 0.5; under this gate's ratio (wrap line diff / mean interior neighbour diff) an EXACT tiling makes the wrap one more
    # interior line, so the ratio sits near 1 by construction. What is pinned instead: the wrap is no outlier among the interior lines.
    assert a["passed"] is True and a["metrics"]["ratio_x"] <= 1.0 and a["metrics"]["ratio_y"] <= 1.0 and a["metrics"]["wrap_line_z"] <= 1.0, a
    assert (tmp_path / "meander_a.png").read_bytes() == (tmp_path / "meander_b.png").read_bytes()


def test_refusals_never_overwrite_and_name_the_fix(built, tmp_path):
    d, src, res = built
    with pytest.raises(ST.TileRefused, match="no true repeat"):
        ST.build(src, str(tmp_path / "x"), mode="motif", size=512)
    with pytest.raises(ST.TileRefused, match="never overwritten"):
        ST.build(src, str(d / "leather"), mode="grain", size=512)
    with pytest.raises(ST.TileRefused, match="mode"):
        ST.build(src, str(tmp_path / "y"), mode="plaid", size=512)
    small = _save(grain(300), tmp_path / "small.png")
    with pytest.raises(ST.TileRefused, match="at least"):
        ST.build(small, str(tmp_path / "z"), mode="grain", size=512)


def test_the_tool_answers_through_api_with_the_root_as_its_jail_and_a_model_sheet_is_a_dry_run_until_live(tmp_path):
    from features_support import run
    _save(grain(1100), tmp_path / "sheet.png")
    r = run(tmp_path, '''
from mixar.modules.lampway_tools import orphans_api as OA
import io
from PIL import Image as _I
calls = []
def fake(prompt, reference_png, count=1, params_extra=None):
    calls.append({"prompt": prompt, "params": params_extra})
    b = io.BytesIO(); _I.open(os.path.join(root, "sheet.png")).save(b, "PNG"); return [b.getvalue()]
OA._generate_image = fake
out = {"built": call("seamless_tile", src="sheet.png", out="tiles/leather", mode="grain", size=512),
       "jail": call("seamless_tile", src="/etc/hostname", out="tiles/x", mode="grain", size=512),
       "dry": call("seamless_tile", prompt="dark tanned leather, flat even light", out="tiles/gen", mode="grain", size=512),
       "n_dry": len(calls),
       "live": call("seamless_tile", prompt="dark tanned leather, flat even light", out="tiles/gen", mode="grain", size=512, live=True),
       "calls": calls}
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["built"]["ok"] is True and o["built"]["passed"] is True and o["built"]["files"]["tile"].endswith("tiles/leather.png"), o["built"]
    assert o["jail"]["ok"] is False and "outside the project root" in o["jail"]["error"], o["jail"]
    assert o["dry"]["ok"] is True and o["dry"]["dry_run"] is True and o["n_dry"] == 0, o["dry"]
    assert o["live"]["ok"] is True and o["calls"][0]["params"] == {"purpose": "tile"} and o["live"]["sheet"].endswith("tiles/gen_sheet.png"), o["live"]
