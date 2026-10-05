# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The animation tools through api.* in the real binary: wiring, the project-root jail, and Blender's own image loader for the masks."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
import test_wave4_anim_gates as G  # noqa: E402
import test_wave4_multiview as M  # noqa: E402
from blender_run import run_script  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_io as IO  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_ref as AR  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def _prepare(tmp):
    from PIL import Image
    J = G._walk(24 * 2 + 1)
    front, side = M._panels(M._walk())
    (tmp / "front.json").write_text(json.dumps({"keypoints": front.tolist()}))
    (tmp / "side.json").write_text(json.dumps({"keypoints": side.tolist()}))
    (tmp / "fit.json").write_text(json.dumps({"joints_m": J.tolist(), "fps": G.FPS}))
    cams = {"cameras": {v: AR.camera_record(v, [0, 0, 1.0], 2.0, (180, 320)) for v in ("front", "side")}}
    (tmp / "cameras.json").write_text(json.dumps(cams))
    for v in ("front", "side"):
        d = tmp / f"mask_{v}"
        d.mkdir()
        for i, j in enumerate(J[:3]):
            Image.fromarray((IO.capsule_masks_cam(j, cams["cameras"])[v] * 255).astype(np.uint8)).save(d / f"{i:04d}.png")
    q = G._take()
    (tmp / "take.json").write_text(json.dumps({"quats": q.tolist(), "bones": ["a", "b", "c"], "root_y_m": [G.SPEED / G.FPS * t for t in range(len(q))], "fps": G.FPS, "planted_foot_speed_mps": G.SPEED}))


def test_every_animation_tool_answers_through_api_with_the_project_root_as_its_jail(tmp_path):
    _prepare(tmp_path)
    r = run_script(PRE + f'''
api.settings_set(project_root={str(tmp_path)!r})
out = {{}}
out["fit"] = api.anim_multiview_fit("front.json", "side.json", calibration={{"px_per_m": 400.0}}, out="fit_out.json")
out["detect"] = api.anim_multiview_fit("front.json", "side.json", stage="detect")
out["check"] = api.anim_check("fit.json", masks={{"front": "mask_front", "side": "mask_side"}}, cameras="cameras.json", out="check.json")
out["nomask"] = api.anim_check("fit.json", masks={{"front": "mask_front"}}, cameras="cameras.json")
out["loop"] = api.anim_loop_export("take.json", reference_bones=["a", "b", "c"], out="loop")
out["manny"] = api.anim_loop_export("take.json", skeleton="SK_Manny")
out["clip"] = api.anim_clip("ref_front.png", "front", "walk")
out["clip16"] = api.anim_clip("ref_front.png", "front", "walk", aspect_ratio="16:9")
out["track"] = api.anim_track("sam3d_body", True, "c.mp4", "m", "cameras.json")
out["gvhmr"] = api.anim_track("gvhmr", True, "c.mp4", "m", "cameras.json")
out["plan"] = api.anim_from_video("Warrior", "walk")
out["jail"] = api.anim_multiview_fit("/etc/hostname", "side.json", calibration={{"px_per_m": 400.0}})
res(out)
''', timeout=600)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["fit"]["ok"] and d["fit"]["views"] == 2 and (tmp_path / "fit_out.json").exists()
    assert d["detect"]["ok"] is False and d["detect"]["state"] == "needs_approval"
    assert d["check"]["ok"] and {"G-OUT-front", "G-LEGS"} <= {g["id"] for g in d["check"]["gates"]} and (tmp_path / "check.json").exists()
    assert d["nomask"]["ok"] is False and "no side-view mask" in d["nomask"]["error"]
    assert d["loop"]["ok"] is True and d["loop"]["export"]["state"] == "not_run"
    assert d["manny"]["ok"] is False and "Manny animations stay on Manny-based rigs" in d["manny"]["error"]
    assert d["clip"]["ok"] and d["clip"]["spend"] is False and d["clip16"]["ok"] is False and "16:9 halves" in d["clip16"]["error"]
    assert d["track"]["state"] == "needs_decision" and d["gvhmr"]["ok"] is False and "research and non-profit" in d["gvhmr"]["error"]
    assert d["plan"]["ok"] and d["plan"]["spend_card"]["credits"] == 45.0
    assert d["jail"]["ok"] is False
