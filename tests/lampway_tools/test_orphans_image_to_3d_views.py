# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_to_3d additions (specs/mixar_docs/image_to_3d.md, wiki/image_to_3d.md): a turnaround SHEET is cut into labelled panels before anything is built (a sheet
fed as one image fuses the panels), paired pieces take front + back only, and the multi-view Studio slots (Tripo Smart Mesh, Meshy, Hi3D) answer as plans with
their arguments, after a plate check that keeps a bad plate from costing credits. REAL binary."""

import json

import numpy as np
from PIL import Image

from features_support import run


def _panel(w=300, h=600, kind="front"):
    a = np.zeros((h, w, 4), np.uint8)
    if kind in ("front", "back"):
        a[60:540, 70:230] = (170, 140, 80, 255)                  # a broad silhouette
    else:
        a[60:540, 115:185] = (170, 140, 80, 255)                 # a narrow side
    return a


def _sheet(tmp_path, gap=40):
    panels = [_panel(kind=k) for k in ("front", "left", "back", "right")]
    h = panels[0].shape[0]
    W = sum(p.shape[1] for p in panels) + gap * 3
    sheet = np.zeros((h, W, 4), np.uint8)
    x = 0
    for p in panels:
        sheet[:, x:x + p.shape[1]] = p
        x += p.shape[1] + gap
    Image.fromarray(sheet, "RGBA").save(tmp_path / "sheet.png")
    for k in ("front", "back", "left"):
        big = Image.fromarray(_panel(kind=k), "RGBA").resize((1024, 2048))
        big.save(tmp_path / f"{k}.png")
    bad = np.zeros((2048, 1024, 4), np.uint8); bad[0:2048, 200:800] = (170, 140, 80, 255)   # touches the top and bottom borders
    Image.fromarray(bad, "RGBA").save(tmp_path / "bad_front.png")


def _go(tmp_path, body):
    _sheet(tmp_path)
    r = run(tmp_path, body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_detect_views_splits_a_four_panel_alpha_sheet_into_labelled_views_and_builds_one_hull(tmp_path):
    res = _go(tmp_path, '''
fused = call("image_to_3d", images={"Front": "sheet.png"}, mode="extrude")
r = call("image_to_3d", detect_views="sheet.png", views=["Front", "Left", "Back", "Right"], mode="hull", resolution=32, name="helm")
print("RESULT", json.dumps({"fused": fused, "r": r, "objects": sorted(o.name for o in bpy.data.objects)}))
''')
    assert res["fused"]["ok"] is False and "detect_views" in res["fused"]["error"], res["fused"]
    r = res["r"]
    assert r["ok"] is True and sorted(r["views_used"]) == ["Back", "Front", "Left", "Right"] and r["detected"]["panels"] == 4, r
    assert r["report"]["view_iou"]["Front"] > 0.8 and res["objects"].count("helm") == 1, r


def test_detect_views_needs_the_panel_order(tmp_path):
    res = _go(tmp_path, '''
print("RESULT", json.dumps(call("image_to_3d", detect_views="sheet.png", mode="hull")))
''')
    assert res["ok"] is False and "the side a panel shows is not guessed" in res["error"], res


def test_paired_refuses_side_views(tmp_path):
    res = _go(tmp_path, '''
print("RESULT", json.dumps(call("image_to_3d", images={"Front": "front.png", "Left": "left.png"}, paired=True)))
''')
    assert res["ok"] is False and "front and back only" in res["error"], res


def test_studio_slots_plan_with_their_arguments_and_a_bad_plate_blocks_the_spend(tmp_path):
    res = _go(tmp_path, '''
out = {"tripo": call("image_to_3d", images={"Front": "front.png", "Back": "back.png"}, paired=True, engine="studio:tripo"),
       "meshy": call("image_to_3d", images={"Front": "front.png", "Back": "back.png"}, engine="studio:meshy"),
       "hi3d": call("image_to_3d", images={"Front": "front.png", "Back": "back.png"}, engine="studio:hi3d"),
       "bad": call("image_to_3d", images={"Front": "bad_front.png", "Back": "back.png"}, paired=True, engine="studio:tripo"),
       "objects": [o.name for o in bpy.data.objects]}
print("RESULT", json.dumps(out))
''')
    t = res["tripo"]
    assert t["needs_approval"] is True and t["studio_action"] == "tripo.mesh" and t["plan_args"]["paired"] is True, t
    assert t["plan_args"]["front"].endswith("front.png") and t["plan_args"]["back"].endswith("back.png") and "left" not in t["plan_args"], t
    assert res["meshy"]["studio_action"] == "meshy.multi_image_to_3d" and len(res["meshy"]["plan_args"]["images"]) == 2, res["meshy"]
    assert res["hi3d"]["studio_action"] == "hi3d.image_to_3d" and res["hi3d"]["plan_args"]["images"][0].endswith("front.png"), res["hi3d"]
    assert res["bad"]["ok"] is False and "fix the plate first" in res["bad"]["error"] and "bad_front.png" in res["bad"]["error"], res["bad"]
    assert res["objects"] == [], "a plan builds nothing"
