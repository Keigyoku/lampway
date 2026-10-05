# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_place (specs/shelf/fit_place.md): enclosure placement with one uniform scale for the five kinds. The shelf's body-derived self-test pieces (the MetaHuman's own region offset 15 mm
along its normals) must come back at scale 1.0 and no translation: the falsifier of the enclosure rule. A piece shifted 4 cm forward is put back (an ICP-style registration would not)."""

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import fit_place as FP  # noqa: E402
from mixar.modules.lampway_tools.pipeline import sections as SEC  # noqa: E402

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
BODY = SCR / "proportion/audit/body.npz"
ST = SCR / "proportion/piece_selftest"
REAL = BODY.exists() and (ST / "helmet.npz").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's body and self-test pieces are not on this machine")


def _shifted(src, dst, dy):
    d = np.load(src)
    np.savez(dst, V=d["V"] + np.array([0, dy, 0]), T=d["T"])
    return dst


# What the self-test can promise (measured 2026-10-05 on the shelf fixtures): the "body offset 15 mm along its normals" piece is not exactly the body + 2C (curvature: the helmet reads 1.025),
# and two of the pieces start at the cut, not at the landmark (waist z 28 mm, gauntlets). The tolerances are those residuals, stated, not hidden.
SELF = {"helmet": (0.04, 0.01), "waist": (0.04, 0.03), "boots": (0.06, 0.02), "gauntlets": (0.06, 0.04)}


@real
@pytest.mark.parametrize("kind,anchor", [("helmet", None), ("waist", None), ("boots", "width"), ("boots", "foot"), ("gauntlets", None)])
def test_the_body_derived_self_test_comes_back_near_scale_one_and_near_no_translation(kind, anchor):
    f = ST / f"{kind}.npz"
    V, T, meta, rep = FP.place(kind, BODY, f, turn=0.0, scale_anchor=anchor)
    ts, tt = SELF[kind]
    assert meta["scale"] == pytest.approx(1.0, abs=ts), (kind, meta, rep)
    assert np.abs(np.array(meta["anchor_shift"])).max() < tt, (kind, meta["anchor_shift"], "how far the landmark moved; the raw translation also carries (1 - scale) x its distance from the origin")
    assert meta["uniform_scale"] is True and V.shape[0] == np.load(f)["V"].shape[0]


@real
@pytest.mark.parametrize("kind", ["helmet", "waist", "boots", "gauntlets"])
def test_a_piece_shifted_4_cm_forward_is_enclosed_back_where_it_belongs(tmp_path, kind):
    f = ST / f"{kind}.npz"
    moved = _shifted(f, tmp_path / "moved.npz", -0.04)
    _, _, meta, _ = FP.place(kind, BODY, moved, turn=0.0, scale_anchor="width" if kind == "boots" else None)
    # enclosure puts it back within 10 mm (measured residuals 0.5-7.5 mm); an ICP-style placement biased to the thick side would not
    assert abs(meta["anchor_shift"][1] - 0.04) < 0.010, (kind, meta["anchor_shift"])


@real
def test_boots_need_a_ruled_anchor_and_the_three_anchors_give_different_scales():
    with pytest.raises(FP.PlaceError, match="no ruled scale anchor"):
        FP.place("boots", BODY, SCR / "tripo_mesh/Boots1_g1/variant1.npz", turn=-90.0)
    scales = {a: FP.place("boots", BODY, SCR / "tripo_mesh/Boots1_g1/variant1.npz", turn=-90.0, scale_anchor=a)[2]["scale"] for a in FP.ANCHORS}
    assert scales["height"] == pytest.approx(0.52, abs=0.02) and scales["foot"] == pytest.approx(0.624, abs=0.02), scales
    assert len({round(v, 3) for v in scales.values()}) == 3


@real
def test_the_applied_map_is_a_similarity_and_refusals_name_the_fix(tmp_path):
    V0 = np.load(ST / "helmet.npz")["V"].astype(float)
    V, T, meta, _ = FP.place("helmet", BODY, ST / "helmet.npz")
    s = meta["scale"]
    A = np.linalg.lstsq(np.c_[V0, np.ones(len(V0))], V, rcond=None)[0][:3]
    sv = np.linalg.svd(A, compute_uv=False)
    assert np.allclose(sv, s, atol=1e-6), "singular values of the applied linear map are equal"
    with pytest.raises(FP.PlaceError, match="clear_mm is 0 to 40"):
        FP.place("helmet", BODY, ST / "helmet.npz", clear_mm=80)
    with pytest.raises(FP.PlaceError, match="run mesh_to_npz first"):
        FP.place("helmet", tmp_path / "none.npz", ST / "helmet.npz")
    with pytest.raises(FP.PlaceError, match="kind is one of"):
        FP.place("cape", BODY, ST / "helmet.npz")


@real
def test_the_section_helpers_match_the_proportion_scorers_copy():
    spec = importlib.util.spec_from_file_location("piece_ratios_script", Path(SEC.__file__).parents[1] / "scripts/proportion/piece_ratios.py")
    sys.path.insert(0, str(Path(SEC.__file__).parents[1] / "scripts"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = np.load(ST / "helmet.npz")
    V, T = d["V"].astype(float), d["T"]
    a = SEC.section(V, T, np.zeros(3), SEC.Z, SEC.X, 1.75)
    b = mod.section(V, T, np.zeros(3), mod.Z, mod.X, 1.75)
    assert a[0] == pytest.approx(b[0]) and a[1] == pytest.approx(b[1]) and np.allclose(a[2], b[2])


@real
def test_the_chest_keeps_the_audits_placement_byte_for_byte(tmp_path):
    """No drift while extending: kind=chest IS place_piece.build (the torso region of the body stands in for a chest seed, as no chest npz ships with the shelf)."""
    d = np.load(BODY)
    V, T = d["V"].astype(float), d["T"]
    keep = (V[:, 2] > 0.95) & (V[:, 2] < 1.62)
    tri = T[keep[T].all(1)]
    used = np.unique(tri)
    remap = np.zeros(len(V), int)
    remap[used] = np.arange(len(used))
    chest = tmp_path / "chest.npz"
    np.savez(chest, V=V[used], T=remap[tri])
    ours = FP.place("chest", BODY, chest, turn=0.0)
    spec = importlib.util.spec_from_file_location("pp", Path(SEC.__file__).parents[1] / "scripts/proportion/place_piece.py")
    sys.path.insert(0, str(Path(SEC.__file__).parents[1] / "scripts/proportion"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    theirs = mod.build(str(BODY), str(chest), 0.0)
    assert np.array_equal(ours[0], theirs[0]) and np.array_equal(ours[1], theirs[1]) and ours[2]["scale"] == theirs[2]["scale"]


@real
def test_the_api_tool_writes_the_placed_mesh_and_its_meta_inside_the_project_root(tmp_path):
    from features_support import run as brun
    import shutil
    shutil.copy(BODY, tmp_path / "body.npz")
    shutil.copy(ST / "helmet.npz", tmp_path / "helmet.npz")
    r = brun(tmp_path, """
a = call("fit_place", kind="helmet", piece="helmet.npz", body="body.npz", out="P/placed.npz")
b = call("fit_place", kind="boots", piece="helmet.npz", body="body.npz")
c = call("fit_place", kind="helmet", piece="../x.npz", body="body.npz")
print("RESULT", json.dumps({"a": a, "b": b, "c": c, "meta": json.load(open(root + "/P/placed.npz.json"))}))
""")
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["ok"] is True and (tmp_path / "P/placed.npz").exists() and o["meta"]["kind"] == "helmet" and o["meta"]["uniform_scale"] is True
    assert o["b"]["ok"] is False and "no ruled scale anchor" in o["b"]["error"] and o["c"]["ok"] is False
