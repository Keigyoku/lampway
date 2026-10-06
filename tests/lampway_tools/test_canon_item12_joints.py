# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 12 (canon 11): lampway_joints_from_views, the static rig-from-views tool, on its keypoints_json path.

Joints are triangulated from orthographic keypoints (golden C08), the corrupt view dropped, and calibrated by offsets measured on a
body with known joints in the SAME cameras (G11.4, built here: a constant per-joint keypoint bias recovered exactly and removed from a
second body). The 2D detector is a model slot: asking for it names what is missing. Pure python: no Blender."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens  # noqa: E402,F401
from mixar.modules.lampway_tools.pipeline import joints_views as JV  # noqa: E402


def _inputs(goldens, tmp_path, bias_px=None, shift=(0.0, 0.0, 0.0), name="kp.json"):
    inp, exp = J(goldens, "C08_multiview/input.json"), J(goldens, "C08_multiview/expected.json")
    cams = {c["name"]: c for c in inp["cameras"]}
    kp = {}
    for joint, p in exp["joints_m"].items():
        q = np.asarray(p) + np.asarray(shift)
        kp[joint] = {}
        for v, cam in cams.items():
            x, y = JV.project(cam, q)
            b = (bias_px or {}).get(joint, (0.0, 0.0))
            kp[joint][v] = [x + b[0], y + b[1], 1.0]
    (tmp_path / "cams.json").write_text(json.dumps({"cameras": inp["cameras"]}))
    (tmp_path / name).write_text(json.dumps({"keypoints_px": kp}))
    truth = {j: (np.asarray(p) + np.asarray(shift)).tolist() for j, p in exp["joints_m"].items()}
    return truth


def test_g11_1_the_joints_are_triangulated_exactly_from_four_views(goldens, tmp_path):
    truth = _inputs(goldens, tmp_path)
    out = JV.run(cameras="cams.json", keypoints="kp.json", root=tmp_path, rig=False)
    worst = max(np.abs(np.array(out["joints"][j]["pos_m"]) - truth[j]).max() for j in truth)
    assert worst < 1e-9 and all(len(out["joints"][j]["views_used"]) == 4 for j in truth) and out["calibrated"] is False


def test_g11_4_a_constant_keypoint_bias_is_calibrated_on_a_known_body_and_removed_from_another(goldens, tmp_path):
    bias = {"hand_l": (1.5, -6.0), "calf_r": (-2.0, 5.0)}                     # a detector's bias: the same pixels in every view (within max_px across)
    truth_a = _inputs(goldens, tmp_path, bias_px=bias, name="kp_a.json")
    (tmp_path / "known.json").write_text(json.dumps({"joints_m": truth_a}))
    cal = JV.calibrate(cameras="cams.json", keypoints="kp_a.json", known="known.json", root=tmp_path, out="cal.json")
    assert set(cal["offsets"]) == set(truth_a) and cal["out"] == "cal.json"
    truth_b = _inputs(goldens, tmp_path, bias_px=bias, shift=(0.02, -0.01, 0.05), name="kp_b.json")
    out = JV.run(cameras="cams.json", keypoints="kp_b.json", calibration="cal.json", root=tmp_path, rig=True)
    worst = max(np.abs(np.array(out["joints"][j]["pos_m"]) - truth_b[j]).max() for j in truth_b)
    assert worst < 1e-9 and out["calibrated"] is True and out["calibration_sha256"] == cal["sha256"]


def test_g11_4_falsifier_offsets_from_a_different_camera_framing_are_refused(goldens, tmp_path):
    _inputs(goldens, tmp_path)
    (tmp_path / "known.json").write_text(json.dumps({"joints_m": J(goldens, "C08_multiview/expected.json")["joints_m"]}))
    JV.calibrate(cameras="cams.json", keypoints="kp.json", known="known.json", root=tmp_path, out="cal.json")
    cams = json.loads((tmp_path / "cams.json").read_text())
    cams["cameras"][0]["ortho"] *= 1.1
    (tmp_path / "cams2.json").write_text(json.dumps(cams))
    with pytest.raises(JV.JointsError, match="camera"):
        JV.run(cameras="cams2.json", keypoints="kp.json", calibration="cal.json", root=tmp_path, rig=True)


def test_a_rig_run_needs_a_calibration_and_one_view_is_refused(goldens, tmp_path):
    _inputs(goldens, tmp_path)
    with pytest.raises(JV.JointsError, match="calibration"):
        JV.run(cameras="cams.json", keypoints="kp.json", root=tmp_path, rig=True)
    kp = json.loads((tmp_path / "kp.json").read_text())
    kp["keypoints_px"] = {"head": {"front": kp["keypoints_px"]["head"]["front"]}}
    (tmp_path / "one.json").write_text(json.dumps(kp))
    with pytest.raises(JV.JointsError, match="head"):
        JV.run(cameras="cams.json", keypoints="one.json", root=tmp_path, rig=False)


def _corrupt(goldens, tmp_path, axis, view=None):
    inp = J(goldens, "C08_multiview/input.json")
    _inputs(goldens, tmp_path)
    kp = json.loads((tmp_path / "kp.json").read_text())
    c = inp["corrupt"]
    kp["keypoints_px"][c["joint"]][view or c["view"]][axis] += c["dx_px"]
    (tmp_path / "bad.json").write_text(json.dumps(kp))
    return c


def test_g11_3_the_canon_fixture_is_ambiguous_and_refused_naming_both_views(goldens, tmp_path):
    """canon defect: left and right are the only views fixing y, so a 40 px x-error in either is the same disagreement; the canon
    reference 'drops the corrupt view' only by a tie (the same error in the RIGHT view leaves it 85.9 mm off, '3 views used')."""
    exp = J(goldens, "C08_multiview/expected.json")
    for view in ("left", "right"):
        c = _corrupt(goldens, tmp_path, 0, view)
        with pytest.raises(JV.JointsError, match=r"lowerarm_l.*ambiguous.*left.*right"):
            JV.run(cameras="cams.json", keypoints="bad.json", root=tmp_path, rig=False, max_px=exp["robust_drop_px"])


def test_g11_3_an_identifiable_outlier_is_dropped_and_recorded(goldens, tmp_path):
    exp = J(goldens, "C08_multiview/expected.json")
    c = _corrupt(goldens, tmp_path, 1)                                         # the left view's height: four views fix z
    out = JV.run(cameras="cams.json", keypoints="bad.json", root=tmp_path, rig=False, max_px=exp["robust_drop_px"])
    row = out["joints"][c["joint"]]
    assert c["view"] not in row["views_used"] and len(row["views_used"]) == 3 and row["residual_px"][c["view"]] > 39
    assert np.abs(np.array(row["pos_m"]) - exp["joints_m"][c["joint"]]).max() < 1e-9


def test_the_reversal_seam_drop_worst_reproduces_the_canon_reference_on_its_fixture(goldens, tmp_path, monkeypatch):
    exp = J(goldens, "C08_multiview/expected.json")
    """the tie is broken by floating-point noise: on the golden's own pixels the reference drops the corrupt left view, on the same
    points re-projected here it drops the right one - so the seam is pinned on the golden's pixels exactly."""
    monkeypatch.setattr(JV, "AMBIGUOUS", "drop_worst")
    inp = J(goldens, "C08_multiview/input.json")
    c = _corrupt(goldens, tmp_path, 0)
    kp = {"keypoints_px": inp["keypoints_px"]}
    kp["keypoints_px"][c["joint"]][c["view"]][0] += c["dx_px"]
    (tmp_path / "bad.json").write_text(json.dumps(kp))
    row = JV.run(cameras="cams.json", keypoints="bad.json", root=tmp_path, rig=False, max_px=exp["robust_drop_px"])["joints"][c["joint"]]
    assert c["view"] not in row["views_used"] and len(row["views_used"]) == 3 and np.abs(np.array(row["pos_m"]) - exp["joints_m"][c["joint"]]).max() < 1e-9


def _tube(radius, sides=64, z0=0.0, z1=1.0, arc=2 * np.pi, R=np.eye(3)):
    th = np.linspace(0, arc, sides + (0 if arc >= 2 * np.pi else 1), endpoint=arc < 2 * np.pi)
    ring = np.stack([radius * np.cos(th), radius * np.sin(th)], 1)
    n = len(ring)
    V = np.concatenate([np.c_[ring, np.full(n, z0)], np.c_[ring, np.full(n, z1)]]) @ R.T
    T = []
    for i in range(n if arc >= 2 * np.pi else n - 1):
        j = (i + 1) % n
        T += [(i, j, n + j), (i, n + j, n + i)]
    return V, np.array(T)


def test_b8_centring_moves_a_joint_toward_the_limb_centre_by_the_hits_mean(goldens):
    """canon 11 B.8: 16 rays in the plane across the bone, move to the hits' mean, 3 passes. The hits' mean HALVES an offset per pass
    (the canon's rule; measured here), so a 10 mm offset ends 1.25 mm from the axis - on a tilted limb as on an upright one."""
    c, s = np.cos(0.6), np.sin(0.6)
    for R in (np.eye(3), np.array([[1, 0, 0], [0, c, -s], [0, s, c]])):
        V, T = _tube(0.05, R=R)
        p = R @ np.array([0.010, 0.0, 0.5])
        q, hits, why = JV.centre_joint(V, T, p, R @ np.array([0, 0, 1.0]), reach=0.15)
        off = q - R @ np.array([0, 0, 0.5])
        assert why is None and hits == 16 and abs(np.linalg.norm(off) - 0.00125) < 1e-4 and abs(off @ (R @ np.array([0, 0, 1.0]))) < 1e-12


def test_b8_an_open_ring_or_a_wall_beyond_reach_is_not_centred_and_says_why():
    V, T = _tube(0.05, arc=np.pi)                                              # half a tube: 8 or 9 of 16 rays hit
    p = np.array([0.0, 0.01, 0.5])
    q, hits, why = JV.centre_joint(V, T, p, np.array([0, 0, 1.0]), reach=0.15)
    assert hits < 12 and "not closed" in why and np.array_equal(q, p)
    V, T = _tube(0.20)
    q, hits, why = JV.centre_joint(V, T, p, np.array([0, 0, 1.0]), reach=0.15)
    assert hits == 0 and "not closed" in why and np.array_equal(q, p)


def test_b8_reach_and_closure_follow_the_joint_kind():
    assert JV.reach_of("index_02_l") == (0.05, 10) and JV.reach_of("hand_l") == (0.08, 12) and JV.reach_of("foot_r") == (0.08, 12)
    assert JV.reach_of("lowerarm_l") == (0.15, 12)


def test_run_centres_each_joint_along_its_bone_and_records_it(goldens, tmp_path):
    truth = _inputs(goldens, tmp_path)
    a, b = np.array(truth["upperarm_l"]), np.array(truth["lowerarm_l"])
    d = (b - a) / np.linalg.norm(b - a)
    z = np.array([0, 0, 1.0])
    ax = np.cross(z, d)
    ang = np.arccos(np.clip(z @ d, -1, 1))
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]]) / np.linalg.norm(ax)
    R = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K                # z onto the upper arm's line
    V, T = _tube(0.045, z0=-0.05, z1=np.linalg.norm(b - a) + 0.05, R=R)
    V = V + a + R @ np.array([0.004, 0.0, 0.0])                                # the arm's axis 4 mm off the keypoint joint
    out = JV.run(cameras="cams.json", keypoints="kp.json", root=tmp_path, rig=False, mesh=(V, T))
    row = out["joints"]["upperarm_l"]
    assert row["centred"] is True and abs(row["centred_cm"] - 0.35) < 0.01           # 4 mm x (1 - 1/8)
    assert out["joints"]["head"]["centred"] is False and "not closed" in out["joints"]["head"]["centre_skip"]


def test_the_detector_is_a_model_slot_that_names_what_is_missing():
    with pytest.raises(JV.JointsError, match="detector"):
        JV.detect(mesh="x", detector="rtmw_wholebody")


TOOL = r"""
import bpy, bmesh, json, numpy as np
from pathlib import Path
from mixar.modules.lampway_tools import api
root = Path(ROOT); api.settings_set(project_root=str(root))
V, T = np.array(VV), np.array(TT)
me = bpy.data.meshes.new("arm"); me.from_pydata([tuple(v) for v in V], [], [tuple(int(i) for i in t) for t in T]); me.update()
ob = bpy.data.objects.new("arm", me); bpy.context.scene.collection.objects.link(ob)
raw = {"raw": api.joints_from_views(mesh="arm", cameras="cams.json", keypoints="kp.json", rig=False)}
n = api.normalize_mesh(input="arm", turn_deg=0, generator="lampway_tool", want_scale="real", scale_evidence={"method": "captain_length", "value": 1.8, "reference": "test"})
raw["norm"] = {k: n.get(k) for k in ("ok", "error")}
raw["run"] = api.joints_from_views(mesh="arm", cameras="cams.json", keypoints="kp.json", rig=False, out="out/joints.json")
raw["file"] = json.loads((root / "out/joints.json").read_text())
raw["nomesh"] = api.joints_from_views(cameras="cams.json", keypoints="kp.json", rig=False)
raw["det"] = api.joints_from_views(mesh="arm", detector="rtmw_wholebody")
raw["cal"] = api.joints_from_views(cameras="cams.json", keypoints="kp.json", known="known.json", out="cal.json")
raw["rig"] = api.joints_from_views(cameras="cams.json", keypoints="kp.json", calibration="cal.json")
print("RESULT", json.dumps(raw))
"""


def test_the_tool_behind_its_door_centres_on_a_canonical_mesh_and_refuses_a_raw_one(goldens, tmp_path):
    from blender_run import run_script
    proj = tmp_path / "proj"
    proj.mkdir()
    truth = _inputs(goldens, proj)
    (proj / "known.json").write_text(json.dumps({"joints_m": truth}))
    a, b = np.array(truth["upperarm_l"]), np.array(truth["lowerarm_l"])
    d = (b - a) / np.linalg.norm(b - a)
    z = np.array([0, 0, 1.0])
    ax = np.cross(z, d)
    ang = np.arccos(np.clip(z @ d, -1, 1))
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]]) / np.linalg.norm(ax)
    R = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K
    V, T = _tube(0.045, z0=-0.05, z1=np.linalg.norm(b - a) + 0.05, R=R)
    V = V + a + R @ np.array([0.004, 0.0, 0.0])
    floor = np.array([[-0.6, -0.1, 0.0], [0.6, 0.1, 0.0], [0.0, 0.0, 0.002]])             # puts the bbox bottom centre on the origin
    V, T = np.vstack([V, floor]), np.vstack([T, [[len(V), len(V) + 1, len(V) + 2]]])
    r = run_script(TOOL.replace("ROOT", repr(str(proj))).replace("VV", repr(V.tolist())).replace("TT", repr(T.tolist())), timeout=180)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["raw"]["ok"] is False and d["raw"]["error"].startswith("normalize first") and d["raw"]["help"][0] == "lampway_normalize_mesh input=arm"
    assert d["norm"]["ok"], d["norm"]
    row = d["run"]["joints"]["upperarm_l"]
    assert d["run"]["ok"] and row["centred"] is True and abs(row["centred_cm"] - 0.35) < 0.01 and d["file"]["joints"]["upperarm_l"] == row
    assert d["nomesh"]["ok"] and d["nomesh"]["joints"]["upperarm_l"]["centred"] is False and "no mesh" in d["nomesh"]["joints"]["upperarm_l"]["centre_skip"]
    assert d["det"]["ok"] is False and "11-H1" in d["det"]["error"]
    assert d["cal"]["ok"] and d["rig"]["ok"] and d["rig"]["calibrated"] is True
