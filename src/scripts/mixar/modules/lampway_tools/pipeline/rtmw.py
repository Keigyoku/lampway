# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The RTMW whole-body 2D detector for anim_multiview_fit's detect stage (specs/generation/anim_multiview_fit.md step 2; memory multiview-2d-joints).

RTMW gives COCO-WholeBody keypoints (133; the first 17 are COCO body: 0 nose, 5/6 shoulders, 7/8 elbows, 9/10 wrists, 11/12 hips, 13/14 knees, 15/16
ankles, left before right, the PERSON's sides). They map to the fit's 15 joints (anim_mv.JOINTS): pelvis = mid hips, spine = mid shoulders, head = nose,
each limb joint its own point; a joint's confidence is its point's score (a midpoint takes the lower). A centred, confidence-weighted moving average smooths
each panel over time. The model itself runs in the science python (scripts/anim/rtmw_detect.py, rtmlib + onnxruntime) from an ONNX file the user put on
disk: nothing is downloaded. Pure numpy here; the backend is injected."""

import json
import os

import numpy as np

from .anim_mv import IDX, JOINTS

COCO = {"head": 0, "upperarm_l": 5, "upperarm_r": 6, "lowerarm_l": 7, "lowerarm_r": 8, "hand_l": 9, "hand_r": 10, "thigh_l": 11, "thigh_r": 12,
        "calf_l": 13, "calf_r": 14, "foot_l": 15, "foot_r": 16}
MID = {"pelvis": (11, 12), "spine": (5, 6)}


class DetectorUnavailable(RuntimeError):
    pass


def to_joints(keypoints, scores):
    kp, sc = np.asarray(keypoints, float), np.asarray(scores, float)
    j, c = np.zeros((len(JOINTS), 2)), np.zeros(len(JOINTS))
    for name, i in COCO.items():
        j[IDX[name]], c[IDX[name]] = kp[i], sc[i]
    for name, (a, b) in MID.items():
        j[IDX[name]], c[IDX[name]] = (kp[a] + kp[b]) / 2, min(sc[a], sc[b])
    return j, c


def smooth(k, c, window=3):
    """Centred moving average over ``window`` frames, each frame weighted by its joint's confidence; the ends use what they have."""
    k, c = np.asarray(k, float), np.asarray(c, float)
    if window <= 1:
        return k.copy()
    h = window // 2
    out = np.empty_like(k)
    for t in range(len(k)):
        a, b = max(0, t - h), min(len(k), t + h + 1)
        w = c[a:b][..., None]
        out[t] = (k[a:b] * w).sum(0) / np.maximum(w.sum(0), 1e-9)
    return out


def detect(frames, out, backend, window=3):
    raw = backend(list(frames))
    js, cs = zip(*(to_joints(kp, sc) for kp, sc in raw)) if raw else ((), ())
    k = smooth(np.array(js), np.array(cs), window) if js else np.zeros((0, len(JOINTS), 2))
    data = {"detector": "rtmw", "joints": JOINTS, "keypoints": k.round(3).tolist(), "conf": np.array(cs).round(4).tolist(), "frames": [os.path.basename(f) for f in frames],
            "smoothing": f"confidence-weighted centred moving average, window {window}"}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as fh:
        json.dump(data, fh)
    return {"frames": len(frames), "out": out, "mean_conf": round(float(np.mean(cs)), 4) if cs else None}


def rtmw_backend(onnx, run_tool=None, input_size="288x384", work=""):
    """A backend that runs scripts/anim/rtmw_detect.py through the runner (science python) on ``onnx``; refused without the weights on disk."""
    if not onnx:
        raise DetectorUnavailable("the RTMW weights are a file the user puts on disk (onnx=<path to the RTMW .onnx>): this tool never downloads them")
    if not os.path.isfile(onnx):
        raise DetectorUnavailable(f"the RTMW weights {onnx} were not found")

    def run(paths):
        raw = os.path.join(work or os.path.dirname(paths[0]), "rtmw_raw.json")
        res = run_tool("rtmw_detect", [raw, onnx, *paths, "--input", input_size])
        if res.rc != 0:
            raise DetectorUnavailable(res.stdout.strip().splitlines()[-1] if res.stdout.strip() else f"rtmw_detect exited {res.rc}")
        with open(raw) as fh:
            rows = json.load(fh)["frames"]
        return [(np.array(r["keypoints"]), np.array(r["scores"])) for r in rows]
    return run
