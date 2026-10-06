# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scene_from_image (specs/mixar_docs/scene_from_image.md) in the real binary: one reference image to separate, editable objects placed as the image arranges them.
The deterministic pipeline segments the image (segment_image), extrudes each part (image_to_3d) and places it from its mask under a documented assumed camera;
a Studio engine is a priced plan for the whole scene that creates nothing until the user confirms."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402


def discs(path):
    a = np.full((240, 480, 3), 255, np.uint8)
    yy, xx = np.mgrid[0:240, 0:480]
    for cx, cy, r, col in ((80, 170, 45, (200, 30, 30)), (240, 120, 35, (30, 160, 40)), (400, 150, 55, (30, 50, 200))):
        a[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = col
    Image.fromarray(a, "RGB").save(path)


def test_three_discs_become_three_objects_left_to_right_in_one_collection(tmp_path):
    discs(tmp_path / "concept.png")
    d = one(go(tmp_path, '''
res = call("scene_from_image", image="concept.png", name="yard", scene_width_m=12.0)
objs = [bpy.data.objects[o["name"]] for o in res.get("objects", [])]
print("RESULT", json.dumps({"res": res, "x": [o.location.x for o in objs], "dims": [list(o.dimensions) for o in objs],
                            "coll": sorted(o.name for o in bpy.data.collections["yard_scene"].objects) if "yard_scene" in bpy.data.collections else None}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert len(res["objects"]) == 3 and res["scene_collection"] == "yard_scene" and d["coll"] == sorted(o["name"] for o in res["objects"])
    assert d["x"] == sorted(d["x"]) and d["x"][0] < -2 and d["x"][2] > 2                     # left to right, as in the image
    heights = [dd[2] for dd in d["dims"]]
    for h, px in zip(heights, (91, 71, 111)):                                                 # each disc's pixel height at 12 m / 480 px
        assert abs(h - px * 12.0 / 480) < 0.1 * px * 12.0 / 480, (h, px)
    assert all(abs(o["pose"]["location"][2]) < 1e-6 for o in res["objects"])                # standing on the ground plane
    assert "assumed camera" in res["placement"]


def test_a_studio_plan_prices_every_object_and_creates_nothing(tmp_path):
    discs(tmp_path / "concept.png")
    d = one(go(tmp_path, '''
n0 = len(bpy.data.objects)
plan = call("scene_from_image", image="concept.png", name="yard", engine="studio:tripo")
print("RESULT", json.dumps({"plan": plan, "created": len(bpy.data.objects) - n0}))
'''))
    plan = d["plan"]
    assert plan["ok"] is False and plan["needs_approval"] is True and plan["objects"] == 3
    assert plan["total_credits"] == 3 * plan["credits_each"] == 300 and d["created"] == 0


def test_too_many_objects_and_an_unknown_engine_are_refused(tmp_path):
    discs(tmp_path / "concept.png")
    d = one(go(tmp_path, '''
many = call("scene_from_image", image="concept.png", max_objects=20)
two = call("scene_from_image", image="concept.png", max_objects=2)
model = call("scene_from_image", image="concept.png", engine="model:sam3d")
print("RESULT", json.dumps({"many": many, "two": two, "model": model}))
'''))
    assert d["many"]["ok"] is False and "1..16" in d["many"]["error"]
    assert d["two"]["ok"] is False and "3 objects" in d["two"]["error"] and "max_objects" in d["two"]["error"]
    assert d["model"]["ok"] is False and "never local" in d["model"]["error"]
