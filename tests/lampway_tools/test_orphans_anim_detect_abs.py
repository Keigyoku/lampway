# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_multiview_fit's two missing pieces (specs/generation/anim_multiview_fit.md, STATUS O26): the RTMW whole-body 2D detector (COCO-WholeBody keypoints mapped
to the fit's 15 joints, confidence kept, temporally smoothed; the model runs in the science python with weights the user put on disk, never downloaded here)
and the two-view SKINNED-silhouette analysis-by-synthesis: the character's own rig is posed, its skinned mesh rasterised through the recorded front and side
cameras, and the bone rotations moved until both silhouettes match. The control: the front view alone cannot tell a leg swung forward from one swung back."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import anim_mv as MV  # noqa: E402
from mixar.modules.lampway_tools.pipeline import rtmw as RT  # noqa: E402

from features_support import run  # noqa: E402


def test_coco_wholebody_keypoints_map_to_the_fit_joints_with_their_confidence():
    kp = np.zeros((133, 2)); sc = np.ones(133)
    named = {5: (90, 100), 6: (110, 100), 7: (80, 140), 8: (120, 140), 9: (75, 180), 10: (125, 180), 11: (95, 200), 12: (105, 200),
             13: (94, 260), 14: (106, 260), 15: (93, 320), 16: (107, 320), 0: (100, 60)}
    for i, p in named.items():
        kp[i] = p
    sc[13] = 0.2
    j, c = RT.to_joints(kp, sc)
    assert j.shape == (len(MV.JOINTS), 2) and c.shape == (len(MV.JOINTS),)
    assert tuple(j[MV.IDX["pelvis"]]) == (100, 200) and tuple(j[MV.IDX["spine"]]) == (100, 100) and tuple(j[MV.IDX["head"]]) == (100, 60)
    assert tuple(j[MV.IDX["calf_l"]]) == (94, 260) and c[MV.IDX["calf_l"]] == pytest.approx(0.2) and tuple(j[MV.IDX["hand_r"]]) == (125, 180)


def test_temporal_smoothing_weights_by_confidence_and_keeps_the_ends():
    k = np.zeros((5, len(MV.JOINTS), 2)); k[:, :, 0] = [[0], [10], [100], [30], [40]]
    c = np.ones((5, len(MV.JOINTS))); c[2] = 0.01                                   # one unreliable outlier frame
    s = RT.smooth(k, c, window=3)
    assert s[0, 0, 0] == pytest.approx((0 * 1 + 10 * 1) / 2) and abs(s[2, 0, 0] - 20) < 2.0, s[:, 0, 0]


def test_the_detector_writes_the_fit_input_from_a_backend_and_refuses_without_the_weights(tmp_path):
    frames = [tmp_path / f"{i:04d}.png" for i in range(3)]
    for f in frames:
        f.write_bytes(b"png")

    def backend(paths):
        out = []
        for _ in paths:
            kp = np.tile(np.array([[100.0, 200.0]]), (133, 1)); out.append((kp, np.full(133, 0.9)))
        return out
    res = RT.detect([str(f) for f in frames], str(tmp_path / "front.json"), backend=backend)
    data = json.loads((tmp_path / "front.json").read_text())
    assert res["frames"] == 3 and len(data["keypoints"]) == 3 and len(data["keypoints"][0]) == len(MV.JOINTS) and data["detector"] == "rtmw"
    with pytest.raises(RT.DetectorUnavailable, match="weights"):
        RT.rtmw_backend(onnx="")
    with pytest.raises(RT.DetectorUnavailable, match="not found"):
        RT.rtmw_backend(onnx=str(tmp_path / "missing.onnx"))


RIG = '''
from mixar.modules.lampway_tools.pipeline import anim_ref as AR
from mixar.modules.lampway_tools.features import anim_abs as ABS
humanoid("body")
r = call("auto_rig", object="body")
arm, mesh = bpy.data.objects[r["armature"]], bpy.data.objects[r["mesh"]]
cams = {v: AR.camera_record(v, [0, 0, 0.9], 1.8, (120, 200)) for v in ("front", "side")}
def masks():
    return ABS.silhouettes(arm, mesh, cams)
pb = arm.pose.bones["thigh_l"]; pb.rotation_mode = "XYZ"
'''


def test_two_view_skinned_refine_recovers_a_leg_swing_and_one_view_cannot_tell_its_sign(tmp_path):
    r = run(tmp_path, RIG + '''
pb.rotation_euler = (math.radians(25), 0, 0); bpy.context.view_layer.update()
target = masks()
fwd_front = masks()["front"]
pb.rotation_euler = (math.radians(-25), 0, 0); bpy.context.view_layer.update()
back_front = masks()["front"]; back_side = masks()["side"]
pb.rotation_euler = (0, 0, 0); bpy.context.view_layer.update()
res = ABS.refine_frame(arm, mesh, cams, target, bones=["thigh_l"], step_deg=8.0, rounds=5)
got = math.degrees(arm.pose.bones["thigh_l"].rotation_euler.x)
iou = lambda a, b: float((a & b).sum() / max((a | b).sum(), 1))
print("RESULT", json.dumps({"got": got, "res": {k: v for k, v in res.items() if k != "rotations"},
                            "front_same": iou(fwd_front, back_front), "side_same": iou(target["side"], back_side)}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert abs(o["got"] - 25.0) <= 5.0, o
    assert o["res"]["iou_after"]["front"] > 0.95 and o["res"]["iou_after"]["side"] > 0.95 and o["res"]["cost_after"] < o["res"]["cost_before"], o
    assert o["front_same"] > 0.97 and o["side_same"] < 0.9, "the front silhouette of +25 and -25 is the same: only the side view tells them apart"


def test_the_refine_stage_answers_through_api(tmp_path):
    r = run(tmp_path, RIG + '''
from PIL import Image
pb.rotation_euler = (math.radians(20), 0, 0); bpy.context.view_layer.update()
t = masks()
for v in ("front", "side"):
    os.makedirs(os.path.join(root, "m_" + v), exist_ok=True)
    Image.fromarray((t[v] * 255).astype(np.uint8)).save(os.path.join(root, "m_" + v, "0000.png"))
json.dump({"cameras": cams}, open(os.path.join(root, "cameras.json"), "w"))
pb.rotation_euler = (0, 0, 0); bpy.context.view_layer.update()
res = call("anim_multiview_fit", stage="refine", armature=arm.name, mesh=mesh.name, masks={"front": "m_front", "side": "m_side"}, cameras="cameras.json",
           bones=["thigh_l"], out="anim/refine.json")
print("RESULT", json.dumps(res))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["ok"] is True and o["frames"] == 1 and o["receipt"][0]["iou_after"]["side"] > 0.95 and Path(o["out"]).exists(), o


def test_the_rtmw_script_refuses_without_rtmlib_or_without_the_weights(tmp_path):
    import importlib.util
    import subprocess
    script = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts/anim/rtmw_detect.py"
    (tmp_path / "w.onnx").write_bytes(b"onnx")
    (tmp_path / "f.png").write_bytes(b"png")
    nofile = subprocess.run([sys.executable, str(script), str(tmp_path / "o.json"), str(tmp_path / "none.onnx"), str(tmp_path / "f.png")], capture_output=True, text=True)
    assert nofile.returncode == 3 and "never downloads" in nofile.stdout, nofile.stdout
    if importlib.util.find_spec("rtmlib") is None:
        nolib = subprocess.run([sys.executable, str(script), str(tmp_path / "o.json"), str(tmp_path / "w.onnx"), str(tmp_path / "f.png")], capture_output=True, text=True)
        assert nolib.returncode == 3 and "pip install rtmlib onnxruntime" in nolib.stdout, nolib.stdout
