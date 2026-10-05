# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""plate_pick / plate_prep (specs/shelf/plate_pick.md + specs/wiki/plate_prep.md, one tool): rank regenerated 4K plates against the approved V3 plate (silhouette IoU x
DoG structure x (1 - colour error)), cut the winner's alpha deterministically (luminance threshold, opening, fill holes, 1 px feather) and check scale, margins and
view correspondence. Pure numpy + PIL (Blender has both, scipy it has not). The REAL shelf plates are the fixtures where they exist on this machine."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import imgops, plates  # noqa: E402

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/path/to/shelf")
SCRATCH = SHELF / "scratch/scratch-tmp"
V3 = Path.home() / "Pictures/TitanAssets/greek-armor-turnarounds-transparent-v3"
REAL = (SCRATCH / "tripo_img/chest_front_4k_g1/4.jpg").exists() and (V3 / "Chest1/Front.png").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's chest plates are not on this machine")


# ------------------------------------------------------------------------------------------ the image operations (scipy's, in numpy)
def test_opening_fill_holes_and_gaussian_match_their_definitions():
    m = np.zeros((40, 40), bool)
    m[10:30, 10:30] = True
    m[18:22, 18:22] = False                                  # a hole
    m[5, 5] = True                                           # a speck
    assert imgops.fill_holes(m)[19, 19] and not imgops.fill_holes(m)[0, 0], "the hole fills, the outside does not"
    opened = imgops.binary_opening(m, 1)
    assert not opened[5, 5] and opened[15, 15], "opening removes the speck and keeps the body"
    edge_hole = m.copy()
    edge_hole[10:30, 10] = False                              # a notch open to the outside is NOT a hole
    assert not imgops.fill_holes(edge_hole)[15, 10]
    g = imgops.gaussian(np.pad(np.ones((1, 1)), 20).astype(float), 3.0)
    assert g.sum() == pytest.approx(1.0, abs=1e-6) and g[20, 20] == g.max() and g[20, 19] == pytest.approx(g[20, 21])


# ------------------------------------------------------------------------------------------ synthetic
def _plate(tmp_path, name, shift=0, blur=0.0, tint=0.0, mirror=False, size=256):
    """A black plate with a bright asymmetric figure (a shape and an inner detail), optionally degraded."""
    a = np.zeros((size, size, 3), float)
    a[40:216, 80:176] = (0.6, 0.5, 0.3)
    a[60:100, 80:130] = (0.9, 0.8, 0.2)                       # an asymmetric inner detail
    a[150:200, 140:176] = (0.2, 0.3, 0.7)
    if mirror:
        a = a[:, ::-1]
    a = np.roll(a, shift, axis=1)
    if blur:
        a = np.stack([imgops.gaussian(a[..., i], blur) for i in range(3)], -1)
    a = np.clip(a + tint * (a.sum(-1, keepdims=True) > 0.1), 0, 1)
    p = tmp_path / name
    Image.fromarray((a * 255).astype(np.uint8)).save(p)
    return p


def _v3(tmp_path):
    base = np.asarray(Image.open(_plate(tmp_path, "base.png"))).astype(float) / 255
    alpha = (base.sum(-1) > 0.1)
    rgba = np.dstack([base, alpha]).astype(float)
    p = tmp_path / "v3.png"
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(p)
    return p


def test_the_v3_plate_scored_against_itself_is_a_perfect_one(tmp_path):
    v3 = _v3(tmp_path)
    row = plates.score(v3, [tmp_path / "base.png"])[0]
    assert row["iou"] == pytest.approx(1.0, abs=0.01) and row["colour_mad"] == pytest.approx(0.0, abs=0.01) and row["structure"] > 0.99 and row["score"] > 0.97


def test_a_blurred_a_tinted_and_a_mirrored_variant_each_score_lower_on_the_measure_they_break(tmp_path):
    v3 = _v3(tmp_path)
    good = plates.score(v3, [tmp_path / "base.png"])[0]
    blur = plates.score(v3, [_plate(tmp_path, "blur.png", blur=2.5)])[0]
    tint = plates.score(v3, [_plate(tmp_path, "tint.png", tint=0.25)])[0]
    mirror = plates.score(v3, [_plate(tmp_path, "mirror.png", mirror=True)])[0]
    assert blur["structure"] < good["structure"] - 0.02, "blur loses the edges"
    assert tint["colour_mad"] > good["colour_mad"] + 0.05 and tint["score"] < good["score"], "a colour shift costs score"
    assert mirror["structure"] < good["structure"] - 0.1, "the same edges in different places: the falsifier of the structure measure"
    ranked = plates.score(v3, [tmp_path / "mirror.png", tmp_path / "tint.png", tmp_path / "blur.png", tmp_path / "base.png"])
    assert ranked[0]["file"] == "base.png" and [r["score"] for r in ranked] == sorted([r["score"] for r in ranked], reverse=True)


def test_the_cut_follows_the_threshold_and_refuses_a_plate_that_is_not_on_black(tmp_path):
    src = _plate(tmp_path, "p.png")
    lo = plates.cut(src, tmp_path / "o1.png", bg_threshold=0.06)
    hi = plates.cut(src, tmp_path / "o2.png", bg_threshold=0.5)
    assert lo["alpha_cover"] > hi["alpha_cover"] + 0.01, "the falsifier: a threshold of 0.5 must change the cover"
    out = np.asarray(Image.open(tmp_path / "o1.png"))
    assert out.shape[2] == 4 and out[0, 0, 3] == 0 and out[128, 128, 3] == 255 and 0 < out[..., 3].astype(float).mean() / 255 < 1, "RGBA, transparent outside, opaque inside"
    grey = tmp_path / "grey.png"
    Image.fromarray(np.full((128, 128, 3), 120, np.uint8)).save(grey)
    with pytest.raises(plates.PlateError, match="found no subject|not near-black|raise bg_threshold"):
        plates.cut(grey, tmp_path / "o3.png")
    with pytest.raises(plates.PlateError, match="never overwrit"):
        plates.cut(src, tmp_path / "o1.png")


def test_paired_pieces_take_front_and_back_only_and_fewer_than_four_variants_are_refused(tmp_path):
    with pytest.raises(plates.PlateError, match="paired pieces use Front and Back only"):
        plates.check_view("Left", paired=True)
    plates.check_view("Back", paired=True)
    with pytest.raises(plates.PlateError, match="never fewer than 4"):
        plates.run(tmp_path, piece="P", view="Front", v3_plate=_v3(tmp_path), variants=[tmp_path / "base.png"] * 3, out_dir=tmp_path / "out", min_px=64)


def test_run_ranks_cuts_the_best_checks_and_writes_the_manifest_once(tmp_path):
    v3 = _v3(tmp_path)
    vs = [_plate(tmp_path, "1.png", mirror=True), _plate(tmp_path, "2.png", blur=3.0), _plate(tmp_path, "3.png", tint=0.3), _plate(tmp_path, "4.png")]
    r = plates.run(tmp_path, piece="P", view="Front", v3_plate=v3, variants=vs, out_dir=tmp_path / "out", min_px=64)
    assert r["best"] == "4.png" and r["picked"] == "4.png" and (tmp_path / "out/Front.png").exists()
    man = json.loads((tmp_path / "out/alpha.json").read_text())
    assert man["plates"]["Front"]["source"] == "4.png" and len(man["plates"]["Front"]["sha256"]) == 64 and "luminance" in man["method"]
    assert set(r["checks"]) == {"margins_frac", "aspect", "view_correspondence"} and r["checks"]["view_correspondence"] > 0.9
    pick = plates.run(tmp_path, piece="P", view="Back", v3_plate=v3, variants=vs, out_dir=tmp_path / "out", pick=3, min_px=64)
    assert pick["picked"] == "3.png" and pick["best"] == "4.png", "a captain's override wins over the best score"


# ------------------------------------------------------------------------------------------ the shelf's real chest plates
@real
def test_the_real_chest_front_ranks_variant_4_first_and_its_cut_reproduces_the_recorded_cover():
    d = SCRATCH / "tripo_img/chest_front_4k_g1"
    rows = plates.score(V3 / "Chest1/Front.png", [d / f"{i}.jpg" for i in (1, 2, 3, 4)])
    assert rows[0]["file"] == "4.jpg", rows
    recorded = json.loads((d / "fidelity.json").read_text())
    ours = {r["file"]: r["score"] for r in rows}
    for r in recorded["variants"]:
        assert ours[r["file"]] == pytest.approx(r["score"], abs=0.01), (r["file"], ours[r["file"]], r["score"])
    out = Path(os.environ.get("TMPDIR", "/path/to/boxes")) / "chest_front_cut_test.png"
    out.unlink(missing_ok=True)
    cover3 = plates.cut(d / "4.jpg", out, bg_threshold=0.06, opening_iters=3)["alpha_cover"]
    out.unlink()
    cover2 = plates.cut(d / "4.jpg", out, bg_threshold=0.06, opening_iters=2)["alpha_cover"]
    out.unlink()
    print("opening x2 cover", cover2, "opening x3 cover", cover3)
    assert cover3 == pytest.approx(0.3739, abs=0.002), (cover2, cover3)
    hi = plates.cut(d / "4.jpg", out, bg_threshold=0.3)["alpha_cover"]
    out.unlink()
    assert hi != pytest.approx(cover3, abs=0.001)


def test_the_api_tool_runs_the_stages_inside_the_app(tmp_path):
    from features_support import run as brun
    plates_dir = tmp_path / "P" / "v3"
    var_dir = tmp_path / "P" / "front_4k"
    plates_dir.mkdir(parents=True)
    var_dir.mkdir(parents=True)
    import shutil
    v3 = _v3(tmp_path)
    shutil.copy(v3, plates_dir / "Front.png")
    for i, kw in enumerate([dict(mirror=True), dict(blur=3.0), dict(tint=0.3), {}], 1):
        shutil.copy(_plate(tmp_path, f"v{i}.png", **kw), var_dir / f"{i}.png")
    r = brun(tmp_path, f"""
a = call("plate_pick", stage="prompt", piece="P", view="Left", v3_dir="P/v3", design_words="a lion head")
b = call("plate_pick", stage="score", piece="P", view="Front", v3_dir="P/v3", variants_dir="P/front_4k")
c = call("plate_pick", stage="run", piece="P", view="Front", v3_dir="P/v3", variants_dir="P/front_4k", min_px=64)
d = call("plate_pick", stage="status", piece="P")
e = call("plate_pick", stage="score", piece="P", view="Left", paired=True, v3_dir="P/v3", variants_dir="P/front_4k")
f = call("plate_pick", stage="score", piece="P", view="Front", v3_dir="../outside", variants_dir="P/front_4k")
print("RESULT", json.dumps({{"a": a, "b": b, "c": c, "d": d, "e": e, "f": f}}))
""")
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["template"] == "plate-4k-crisper" and o["a"]["variables"]["view"] == "left side" and o["a"]["variables"]["design_inventory"] == "a lion head"
    assert o["b"]["best"] == "4.png" and o["c"]["picked"] == "4.png" and o["d"]["done"] == ["Front"] and o["d"]["missing"] == ["Back", "Left", "Right"]
    assert o["e"]["ok"] is False and "Front and Back only" in o["e"]["error"] and o["f"]["ok"] is False
