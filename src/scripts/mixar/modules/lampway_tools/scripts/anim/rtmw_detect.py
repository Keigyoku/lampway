# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# RTMW whole-body 2D keypoints (COCO-WholeBody, 133 points) per frame, for anim_multiview_fit's detect stage. Runs in the SCIENCE python (rtmlib and
# onnxruntime installed there); the ONNX weights are a file the user put on disk: this script never downloads anything. One character on a plain background
# per panel, so the whole frame is the person box (no person detector). The model input size defaults to 288 x 384 [UNVERIFIED against the user's file].
#   python rtmw_detect.py <out.json> <rtmw.onnx> <frame.png> [<frame.png> ...] [--input 288x384]
# Writes {"detector": "rtmw", "onnx_sha256", "frames": [{"file", "keypoints": [[u, v] x 133], "scores": [133]}]}; refusals print 'error: ...' and exit 3.
import hashlib
import json
import os
import sys


def main(argv):
    if len(argv) < 3:
        print("error: usage: rtmw_detect.py <out.json> <rtmw.onnx> <frame.png> [...] [--input WxH]"); return 2
    size = (288, 384)
    if "--input" in argv:
        i = argv.index("--input"); size = tuple(int(x) for x in argv[i + 1].lower().split("x")); argv = argv[:i] + argv[i + 2:]
    out, onnx, frames = argv[0], argv[1], argv[2:]
    if not os.path.isfile(onnx):
        print(f"error: the RTMW weights {onnx} were not found: put the .onnx file on disk (this tool never downloads it)"); return 3
    try:
        import numpy as np
        from PIL import Image
        from rtmlib import RTMPose
    except ImportError as exc:
        print(f"error: {exc.name} is not installed in this python: pip install rtmlib onnxruntime into the science python"); return 3
    model = RTMPose(onnx_model=onnx, model_input_size=size, backend="onnxruntime", device="cpu")
    rows = []
    for f in frames:
        img = np.asarray(Image.open(f).convert("RGB"))[:, :, ::-1].copy()
        h, w = img.shape[:2]
        kp, sc = model(img, bboxes=[[0, 0, w, h]])
        rows.append({"file": os.path.basename(f), "keypoints": np.asarray(kp)[0].tolist(), "scores": np.asarray(sc)[0].tolist()})
    with open(onnx, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(out, "w") as fh:
        json.dump({"detector": "rtmw", "onnx_sha256": digest, "input": list(size), "frames": rows}, fh)
    print(f"frames: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
