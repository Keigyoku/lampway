# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""render_condition_passes (specs/wiki/render_condition_passes.md): one camera, the conditioning images an image or video model needs: a flat id colour per
object (with its palette), depth (nearer brighter, fixed near/far), edges and clay. Light engines only. REAL binary, Workbench."""

import json

import numpy as np
from PIL import Image

from features_support import run

SCENE = '''
near = boxes("near_box", [((-0.6, -1.0, 0.5), (0.5, 0.5, 1.0))])
far = boxes("far_box", [((0.6, 1.5, 0.5), (0.5, 0.5, 1.0))])
'''


def _go(tmp_path, body):
    r = run(tmp_path, SCENE + body, timeout=600)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_id_pass_has_one_flat_colour_per_object(tmp_path):
    res = _go(tmp_path, '''
canon(*["near_box", "far_box"])
r = call("render_condition_passes", objects=["near_box", "far_box"], passes=["id"], size=256, out_dir="cond")
print("RESULT", json.dumps({"r": r, "colors": [list(o.color) for o in (near, far)]}))
''')
    r = res["r"]
    assert r["ok"] is True and set(r["files"]) == {"id"}, r
    pal = {p["object"]: tuple(p["rgb"]) for p in r["palette"]}
    assert set(pal) == {"near_box", "far_box"} and pal["near_box"] != pal["far_box"], "two objects never share a colour"
    a = np.asarray(Image.open(r["files"]["id"]).convert("RGBA"))
    opaque = a[a[..., 3] > 0][:, :3]
    seen = {tuple(int(c) for c in px) for px in opaque}
    assert seen == set(pal.values()), (seen, pal)
    assert res["colors"] == [[1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]], "the objects' own colours are restored"


def test_depth_is_monotonic_with_distance(tmp_path):
    res = _go(tmp_path, '''
canon(*["near_box", "far_box"])
r = call("render_condition_passes", objects=["near_box", "far_box"], passes=["id", "depth"], size=128, out_dir="cond")
print("RESULT", json.dumps(r))
''')
    ida = np.asarray(Image.open(res["files"]["id"]).convert("RGB")).astype(int)
    dep = np.asarray(Image.open(res["files"]["depth"]).convert("L")).astype(float)
    pal = {p["object"]: np.array(p["rgb"]) for p in res["palette"]}
    near = (np.abs(ida - pal["near_box"]).sum(axis=2) == 0)
    far = (np.abs(ida - pal["far_box"]).sum(axis=2) == 0)
    assert near.sum() > 50 and far.sum() > 50
    assert dep[near].mean() > dep[far].mean() + 10 and dep[~(near | far)].max() < dep[far].mean(), "nearer is brighter; the background is the darkest"
    assert res["depth"]["near_m"] < res["depth"]["far_m"]


def test_edge_and_clay_passes_and_a_named_camera(tmp_path):
    res = _go(tmp_path, '''
cd = bpy.data.cameras.new("shotcam"); cam = link(bpy.data.objects.new("shotcam", cd))
cam.location = (0, -8, 2); cam.rotation_euler = (math.radians(80), 0, 0)
canon(*["near_box", "far_box"])
r = call("render_condition_passes", objects=["near_box", "far_box"], camera="shotcam", passes=["clay", "edge"], size=128, out_dir="cond2")
print("RESULT", json.dumps({"r": r, "scenes": [s.name for s in bpy.data.scenes], "cams": sorted(o.name for o in bpy.data.objects if o.type == "CAMERA")}))
''')
    r = res["r"]
    assert r["ok"] is True and set(r["files"]) == {"clay", "edge"} and r["camera"] == "shotcam", r
    e = np.asarray(Image.open(r["files"]["edge"]).convert("L"))
    assert 0.005 < (e > 128).mean() < 0.2, "edges are thin lines, not the whole frame"
    assert len(res["scenes"]) == 1 and res["cams"] == ["shotcam"], "the throw-away scene and auto camera are removed"


def test_cycles_refused(tmp_path):
    res = _go(tmp_path, '''
canon(*["near_box"])
canon(*[])
canon(*["near_box"])
print("RESULT", json.dumps({"c": call("render_condition_passes", objects=["near_box"], engine="cycles", out_dir="c"),
                            "none": call("render_condition_passes", objects=[], out_dir="c"),
                            "bad": call("render_condition_passes", objects=["near_box"], passes=["normal"], out_dir="c")}))
''')
    assert res["c"]["ok"] is False and "Cycles is refused" in res["c"]["error"], res
    assert res["none"]["ok"] is False and res["bad"]["ok"] is False and "id" in res["bad"]["error"], res
