# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Image to 3D and multi-view (Mixar docs: "reconstruct a mesh from a visual reference ... a turnaround shows one subject from
several angles"). Proven code: the visual hull (space carving of silhouettes from the cardinal views) with surface smoothing,
a rounded extrusion for the front+back paired-piece case, and a luminance relief for one image. The result is judged by
re-projecting the mesh onto the views and reading the IoU, not by looking at it. The generative slot (Tripo Smart Mesh, 100
credits) answers with action and price for approval."""

from features_support import run

MAKE = '''
from PIL import Image, ImageDraw
def disc(path, w=160, h=200, rx=60, ry=90, alpha=True):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([w / 2 - rx, h / 2 - ry, w / 2 + rx, h / 2 + ry], fill=(200, 120, 40, 255))
    im.save(path)
    return path
'''


def test_the_visual_hull_of_front_and_side_discs_is_an_ellipsoid_that_reprojects_onto_both_views(tmp_path):
    r = run(tmp_path, MAKE + '''
os.makedirs(root + "/views", exist_ok=True)
f = disc(root + "/views/Front.png", rx=60, ry=90)          # width 120, height 180
l = disc(root + "/views/Left.png", rx=40, ry=90)           # depth 80
res = call("image_to_3d", images={"Front": "views/Front.png", "Left": "views/Left.png"}, size=1.8, resolution=64, mode="hull")
ob = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "dims": [round(x, 3) for x in ob.dimensions] if ob else None, "faces": len(ob.data.polygons) if ob else 0}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["mode"] == "hull" and res["object"] == "lw_hull"
    dx, dy, dz = out["dims"]
    assert abs(dz - 1.8) < 0.08 and abs(dx - 1.2) < 0.1 and abs(dy - 0.8) < 0.1, out["dims"]
    iou = res["report"]["view_iou"]
    assert set(iou) == {"Front", "Left"} and min(iou.values()) > 0.9, iou
    assert res["report"]["watertight_boundary_edges"] == 0 and out["faces"] > 500
    # The hull of two orthogonal elliptic silhouettes is the intersection of two elliptic cylinders, not an ellipsoid: its
    # cross-section at height z is a rectangle 2a*2b*(1 - z^2/c^2), so V = 16abc/3 (a=0.6, b=0.4, c=0.9).
    expected = 16 / 3 * 0.6 * 0.4 * 0.9
    assert abs(res["report"]["volume"] - expected) / expected < 0.06, (res["report"]["volume"], expected)


def test_front_and_back_only_rounds_the_silhouette_into_a_pillow_of_the_requested_depth(tmp_path):
    r = run(tmp_path, MAKE + '''
os.makedirs(root + "/views", exist_ok=True)
disc(root + "/views/Front.png"); disc(root + "/views/Back.png")
res = call("image_to_3d", images={"Front": "views/Front.png", "Back": "views/Back.png"}, size=1.0, resolution=48, mode="extrude", depth=0.3, profile="round")
slab = call("image_to_3d", images={"Front": "views/Front.png", "Back": "views/Back.png"}, size=1.0, resolution=48, mode="extrude", depth=0.3, profile="slab", name="lw_slab")
d = lambda n: [round(x, 3) for x in bpy.data.objects[n].dimensions]
print("RESULT", json.dumps({"res": res, "slab": slab, "d": d(res["object"]), "ds": d(slab["object"])}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and abs(out["d"][1] - 0.3) < 0.04 and abs(out["d"][2] - 1.0) < 0.05
    assert out["res"]["report"]["view_iou"]["Front"] > 0.85
    assert out["res"]["report"]["volume"] < out["slab"]["report"]["volume"], "the rounded profile holds less volume than the slab"


def test_relief_displaces_a_grid_by_the_image_luminance(tmp_path):
    r = run(tmp_path, '''
from PIL import Image
import numpy as np
os.makedirs(root + "/views", exist_ok=True)
a = np.zeros((64, 64), np.uint8); a[:, 32:] = 255                 # left half dark, right half bright
Image.fromarray(a).convert("RGB").save(root + "/views/relief.png")
res = call("image_to_3d", images={"Front": "views/relief.png"}, size=1.0, resolution=32, mode="relief", depth=0.2)
ob = bpy.data.objects[res["object"]]
zs = [v.co.y for v in ob.data.vertices]
left = np.mean([v.co.y for v in ob.data.vertices if v.co.x < -0.2]); right = np.mean([v.co.y for v in ob.data.vertices if v.co.x > 0.2])
print("RESULT", json.dumps({"res": res, "left": float(left), "right": float(right), "span": float(max(zs) - min(zs))}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["right"] - out["left"] > 0.15 and abs(out["span"] - 0.2) < 0.03


def test_studio_slot_refusals_and_bad_input(tmp_path):
    r = run(tmp_path, MAKE + '''
os.makedirs(root + "/views", exist_ok=True)
disc(root + "/views/Front.png")
print("RESULT", json.dumps({"studio": call("image_to_3d", images={"Front": "views/Front.png"}, engine="studio:tripo", plate_check=False),
    "one_view_hull": call("image_to_3d", images={"Front": "views/Front.png"}, mode="hull"),
    "missing": call("image_to_3d", images={"Front": "views/nope.png", "Left": "views/nope.png"}, mode="hull"),
    "outside": call("image_to_3d", images={"Front": "/etc/hostname"}, mode="relief"),
    "bad_view": call("image_to_3d", images={"Top": "views/Front.png"}, mode="relief")}))
''')
    out = r.results[0]
    assert out["studio"]["needs_approval"] is True and "100 credits" in out["studio"]["price"]
    assert out["one_view_hull"]["ok"] is False and "two views" in out["one_view_hull"]["error"]
    assert out["missing"]["ok"] is False
    assert out["outside"]["ok"] is False and "outside the project root" in out["outside"]["error"]
    assert out["bad_view"]["ok"] is False and "Top" in out["bad_view"]["error"]
