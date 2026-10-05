# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""piece_ratios / proportion_score (specs/shelf/piece_ratios.md + specs/wiki/proportion_score.md): scale-free landmark ratios of a helmet / waist / boots / gauntlet against the
MetaHuman body, score = RMS log deviation. The shelf's own recorded self-tests and seeds are the fixtures (the numbers must reproduce); the output says validated: false."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import runner as R  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
BODY = SCR / "proportion/audit/body.npz"
REAL = BODY.exists() and (SCR / "proportion/piece_selftest/boots.npz").exists() and (SCR / "tripo_mesh/Boots1_g1/variant1.npz").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's proportion fixtures are not on this machine")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("LAMPWAY_PYTHON_SCIENCE", raising=False)
    s = S.load()
    s.project_root = tmp_path
    return s


def score(cfg, tmp_path, kind, pieces, clear=None):
    out = tmp_path / f"{kind}.json"
    args = [kind, str(out), str(BODY)] + pieces + (["--clear-mm", str(clear)] if clear is not None else [])
    cmd = R.command("piece_ratios", args, cfg)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout, (json.loads(out.read_text()) if out.exists() else None)


@real
@pytest.mark.parametrize("kind", ["boots", "helmet", "waist", "gauntlets"])
def test_the_body_offset_15_mm_scores_near_zero_for_each_kind(cfg, tmp_path, kind):
    """The shelf's recorded self-test JSONs are the oracle (its header quotes earlier runs: waist 0.022 became 0.0144, helmet 0.032 became 0.0373)."""
    rc, out, j = score(cfg, tmp_path, kind, [f"self={SCR}/proportion/piece_selftest/{kind}.npz:0"])
    assert rc == 0, out[-1500:]
    row = j["pieces"]["self"]
    recorded = json.loads((SCR / f"proportion/piece_selftest/{kind}.json").read_text())["pieces"]["self"]["rms_logdev"]
    assert row["rms_logdev"] < 0.06 and row["rms_logdev"] == pytest.approx(recorded, abs=1e-4), row
    assert j["validated"] is False and j["kind"] == kind, "the four non-chest kinds stay unvalidated until an auditor's falsification is recorded"


@real
@pytest.mark.parametrize("piece", ["Boots1", "Gauntlets1", "Helmet1", "Waist1"])
def test_the_recorded_g1_seeds_reproduce_the_shelfs_scores(cfg, tmp_path, piece):
    kind = {"Boots1": "boots", "Gauntlets1": "gauntlets", "Helmet1": "helmet", "Waist1": "waist"}[piece]
    shelf = json.loads((SCR / f"proportion/pieces_g1/{piece}.json").read_text())
    specs = [f"{n}={SCR}/tripo_mesh/{piece}_g1/variant{i}.npz:-90" for i, n in enumerate(shelf["pieces"], 1)]
    rc, out, j = score(cfg, tmp_path, kind, specs, clear=shelf["clearance_mm"])
    assert rc == 0, out[-1500:]
    assert j["ranking"] == shelf["ranking"], (j["ranking"], shelf["ranking"])
    for n, row in shelf["pieces"].items():
        if "rms_logdev" in row:
            assert j["pieces"][n]["rms_logdev"] == pytest.approx(row["rms_logdev"], abs=1e-4), (piece, n)


def _transformed(src, dst, fn):
    d = np.load(src)
    V, T = fn(d["V"].astype(float), d["T"])
    np.savez(dst, V=V, T=T)
    return dst


@real
def test_a_gauntlet_turned_180_degrees_about_z_scores_the_same_and_one_upside_down_is_refused(cfg, tmp_path):
    src = SCR / "tripo_mesh/Gauntlets1_g1/variant1.npz"
    rc, out, base = score(cfg, tmp_path, "gauntlets", [f"a={src}:-90"])
    assert rc == 0 and "rms_logdev" in base["pieces"]["a"], out[-800:]
    spun = _transformed(src, tmp_path / "spun.npz", lambda V, T: (V * np.array([-1.0, -1.0, 1.0]), T))
    rc, out, j = score(cfg, tmp_path, "gauntlets", [f"a={spun}:-90"])
    assert rc == 0 and j["pieces"]["a"]["rms_logdev"] == pytest.approx(base["pieces"]["a"]["rms_logdev"], abs=0.01), "section frames are PCA-based: roll-free"
    down = _transformed(src, tmp_path / "down.npz", lambda V, T: (V * np.array([-1.0, 1.0, -1.0]), T))                  # rotated 180 degrees about Y: the cuff is now the lower end
    rc, out, j = score(cfg, tmp_path, "gauntlets", [f"a={down}:-90"])
    row = j["pieces"]["a"]
    assert "rms_logdev" not in row and "not cuff-up" in row["error"], row


@real
def test_a_mirrored_boot_pair_scores_the_same_and_a_boot_deeper_by_10_percent_moves_dw_by_about_10(cfg, tmp_path):
    src = SCR / "tripo_mesh/Boots1_g1/variant1.npz"
    rc, out, base = score(cfg, tmp_path, "boots", [f"a={src}:-90"])
    b = base["pieces"]["a"]
    mirrored = _transformed(src, tmp_path / "m.npz", lambda V, T: (V * np.array([-1.0, 1.0, 1.0]), T))
    rc, out, m = score(cfg, tmp_path, "boots", [f"a={mirrored}:90"])                                                       # the turn mirrors too (x -> -x under the -90 turn is y -> -y)
    deep = _transformed(src, tmp_path / "d.npz", lambda V, T: (V * np.array([1.1, 1.0, 1.0]), T))                          # Tripo FBX is turned -90: the file x becomes the front-back depth
    rc, out, d = score(cfg, tmp_path, "boots", [f"a={deep}:-90"])
    assert d["pieces"]["a"]["dev_pct"]["DW"] - b["dev_pct"]["DW"] == pytest.approx(10.0, abs=4.0), (d["pieces"]["a"]["dev_pct"], b["dev_pct"])
    assert "rms_logdev" in m["pieces"]["a"]


def test_a_missing_file_and_a_body_without_joints_are_refused_with_the_fix(cfg, tmp_path):
    rc, out, _ = score(cfg, tmp_path, "boots", [f"a={tmp_path}/none.npz:-90"]) if REAL else (1, "error: none.npz not found: run mesh_to_npz first", None)
    assert "not found" in out and "mesh_to_npz" in out
    nojoints = tmp_path / "bad_body.npz"
    np.savez(nojoints, V=np.zeros((3, 3)), T=np.zeros((1, 3), int))
    p = subprocess.run(R.command("piece_ratios", ["boots", str(tmp_path / "o.json"), str(nojoints), f"a={nojoints}:0"], cfg), capture_output=True, text=True)
    assert "no joints" in p.stdout and "mesh_to_npz" in p.stdout
