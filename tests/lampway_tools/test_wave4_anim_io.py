# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The file-level animation steps (anim_multiview_fit, anim_check, anim_loop_export) on synthetic files: keypoints in, fit out, gates with numbers."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
import test_wave4_anim_gates as G  # noqa: E402
import test_wave4_multiview as M  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_gates as AG  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_io as IO  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_mv as MV  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_ref as AR  # noqa: E402


def _files(tmp_path, J=None, swap=True):
    J = M._walk() if J is None else J
    front, side = M._panels(J, swap_side_legs=swap)
    (tmp_path / "front.json").write_text(json.dumps({"keypoints": front.tolist()}))
    (tmp_path / "side.json").write_text(json.dumps({"keypoints": side.tolist()}))
    return J


def test_the_fit_file_carries_the_joints_the_leg_identity_the_sync_and_the_scale(tmp_path):
    J = _files(tmp_path)
    out = IO.multiview_fit(str(tmp_path / "front.json"), str(tmp_path / "side.json"), calibration={"px_per_m": M.PX_PER_M}, out=str(tmp_path / "fit.json"))
    assert out["ok"] and out["views"] == 2 and out["sync_score"] > 0.8 and Path(out["file"]).exists()
    j = np.asarray(out["joints_m"])
    assert j.shape == J.shape and MV.leg_identity_accuracy(J, j) == 1.0
    assert out["leg_identity"]["accuracy_vs_front"] > 0.99 and out["duplicate_frames"]["held"] == []


def test_the_single_view_option_fails_leg_identity_and_warns_on_the_same_files(tmp_path):
    J = _files(tmp_path)
    out = IO.multiview_fit(str(tmp_path / "front.json"), str(tmp_path / "side.json"), calibration={"px_per_m": M.PX_PER_M}, single_view=True, out=str(tmp_path / "fit1.json"))
    assert out["views"] == 1 and "cannot be told apart" in out["warning"] and MV.leg_identity_accuracy(J, np.asarray(out["joints_m"])) < 0.9


def test_a_missing_scale_a_wrong_shape_and_panels_out_of_sync_are_refused(tmp_path):
    _files(tmp_path)
    f, s = str(tmp_path / "front.json"), str(tmp_path / "side.json")
    with pytest.raises(IO.IOError_, match="the scale is the figure's, never guessed"):
        IO.multiview_fit(f, s)
    (tmp_path / "bad.json").write_text(json.dumps({"keypoints": [[[0, 0]]]}))
    with pytest.raises(IO.IOError_, match="keypoints must be"):
        IO.multiview_fit(str(tmp_path / "bad.json"), s, calibration={"px_per_m": 400})
    side = np.roll(np.asarray(json.loads(Path(s).read_text())["keypoints"]), 7, axis=0)
    (tmp_path / "shifted.json").write_text(json.dumps({"keypoints": side.tolist()}))
    with pytest.raises(MV.MultiviewError, match="panels out of sync; re-generate"):
        IO.multiview_fit(f, str(tmp_path / "shifted.json"), calibration={"px_per_m": M.PX_PER_M})


def test_the_grid_parallax_gives_the_root_speed_and_the_held_frames_are_listed(tmp_path):
    J = M._walk(24)
    front, side = M._panels(J)
    front[5] = front[4]                                                                   # a held frame
    (tmp_path / "front.json").write_text(json.dumps({"keypoints": front.tolist()}))
    (tmp_path / "side.json").write_text(json.dumps({"keypoints": side.tolist()}))
    row = np.random.default_rng(3).random(512)
    grid = [np.tile(np.roll(row, 16 * t)[None, :], (40, 1)) for t in range(6)]
    out = IO.multiview_fit(str(tmp_path / "front.json"), str(tmp_path / "side.json"), calibration={"px_per_m": 400.0}, fps=24.0, grid_images=grid, out=str(tmp_path / "fit.json"))
    assert out["root_speed_mps"] == pytest.approx(16 / 400 * 24, abs=0.05) and 5 in out["duplicate_frames"]["held"]
    j = np.asarray(out["joints_m"])
    assert j[-1, MV.IDX["pelvis"], 1] - j[0, MV.IDX["pelvis"], 1] == pytest.approx(out["root_speed_mps"] / 24 * 23, rel=0.01)


def _png_dir(tmp_path, name, masks):
    from PIL import Image
    d = tmp_path / name
    d.mkdir()
    for i, m in enumerate(masks):
        Image.fromarray((m * 255).astype(np.uint8)).save(d / f"{i:04d}.png")
    return str(d)


def _gray(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("L"), float) / 255.0


def test_anim_check_over_files_reads_the_masks_draws_the_stand_in_silhouette_and_names_every_gate(tmp_path):
    J = G._walk(24 * 2 + 1)
    fit = {"joints_m": J.tolist(), "fps": G.FPS}
    (tmp_path / "fit.json").write_text(json.dumps(fit))
    cams = {"cameras": {v: AR.camera_record(v, [0, 0, 1.0], 2.0, (180, 320)) for v in ("front", "side")}}
    cams["cameras"]["front"]["center"] = [0, 0, 1.0]
    (tmp_path / "cameras.json").write_text(json.dumps(cams))
    masks = {v: [IO.capsule_masks_cam(j, {w: cams["cameras"][w] for w in ("front", "side")})[v] for j in J[:6]] for v in ("front", "side")}
    out = IO.check(str(tmp_path / "fit.json"), masks={v: _png_dir(tmp_path, f"m_{v}", masks[v]) for v in masks}, cameras=str(tmp_path / "cameras.json"), load_gray=_gray, out=str(tmp_path / "check.json"))
    ids = {g["id"] for g in out["gates"]}
    assert {"G-OUT-front", "G-OUT-side", "G-LEGS", "G-FOOT-SLIDE", "G-FOOT-PLANT"} <= ids and out["frames"] == 6
    assert [g for g in out["gates"] if g["id"] == "G-OUT-front"][0]["value"] > 0.95 and "capsule stand-in" in out["silhouette_source"] and Path(out["file"]).exists()
    with pytest.raises(AG.GateError, match="no side-view mask"):
        IO.check(str(tmp_path / "fit.json"), masks={"front": _png_dir(tmp_path, "only_front", masks["front"])}, cameras=str(tmp_path / "cameras.json"), load_gray=_gray)


def _take_file(tmp_path, strides=4, drift=0.0, speed_planted=G.SPEED):
    q = G._take(strides, drift)
    root = [G.SPEED / G.FPS * t for t in range(len(q))]
    (tmp_path / "take.json").write_text(json.dumps({"quats": q.tolist(), "bones": ["a", "b", "c"], "root_y_m": root, "fps": G.FPS, "planted_foot_speed_mps": speed_planted}))
    return str(tmp_path / "take.json")


def test_loop_export_over_files_finds_the_period_gates_the_loop_and_says_the_ue_leg_did_not_run(tmp_path):
    out = IO.loop_export(_take_file(tmp_path), reference_bones=["a", "b", "c"], out=str(tmp_path / "loop"))
    assert out["ok"] is True and out["period_frames"] == pytest.approx(G.PERIOD, abs=0.3) and out["strides"] == 4
    assert out["export"]["state"] == "not_run" and "UE editor leg" in out["export"]["reason"] and out["sequence"] is None
    assert set(out["unverified"]) == {"G-FIDELITY", "G-ENGINE"} and (tmp_path / "loop" / "loop.json").exists()
    bad = IO.loop_export(_take_file(tmp_path, drift=3.4), reference_bones=["a", "b", "c"], out=str(tmp_path / "loop2"))
    assert bad["ok"] is False and "use more strides" in bad["gates"]["G-LOOP"]["message"]
    with pytest.raises(AG.GateError, match="Manny animations stay on Manny-based rigs"):
        IO.loop_export(_take_file(tmp_path), skeleton="SK_Manny")
    (tmp_path / "chk.json").write_text(json.dumps({"passed": False, "gates": [{"id": "G-LEGS", "passed": False}]}))
    with pytest.raises(AG.GateError, match="run anim_check; G-LEGS failed"):
        IO.loop_export(_take_file(tmp_path), check_result=str(tmp_path / "chk.json"))


def test_panels_with_different_floor_rows_and_a_drifting_camera_give_the_same_fit(tmp_path):
    J = M._walk()
    front, side = M._panels(J)
    n = len(J)
    drift = (3.0 * np.arange(n))[:, None]
    front[..., 0] += drift                                                           # the whole figure drifts across the front panel
    side[..., 0] += 2.0 * np.arange(n)[:, None]
    side[..., 1] += 37.0                                                              # the side panel's floor is lower than the front's
    (tmp_path / "front.json").write_text(json.dumps({"keypoints": front.tolist()}))
    (tmp_path / "side.json").write_text(json.dumps({"keypoints": side.tolist()}))
    out = IO.multiview_fit(str(tmp_path / "front.json"), str(tmp_path / "side.json"), calibration={"px_per_m": M.PX_PER_M}, out=str(tmp_path / "fit.json"))
    j = np.asarray(out["joints_m"])
    rel = J - J[:, :1]
    assert MV.leg_identity_accuracy(J, j) == 1.0
    assert np.abs(j[:, MV.IDX["pelvis"], :2]).max() < 0.03                      # a drifting camera does not become travel: the pelvis stays at the origin of both horizontal axes
    assert np.abs((j - j[:, :1])[:, :, 2] - rel[:, :, 2]).max() < 0.03 and np.abs((j - j[:, :1])[:, :, 0] - rel[:, :, 0]).max() < 0.03
