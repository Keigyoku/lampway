# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scene_from_image: one reference image to separate, editable objects placed as the image arranges them (specs/mixar_docs/scene_from_image.md).

The deterministic pipeline composes the tools that exist: segment_image (the given masks, or the image's parts by colour or alpha), image_to_3d's
extrusion per part (each part's own silhouette, a rounded slab), and a placement under an ASSUMED camera, a documented approximation [UNVERIFIED
accuracy]: a straight-on view of a ground plane, the image ``scene_width_m`` wide; a part's horizontal centre gives x, its bottom edge gives the depth
(lower in the image = nearer, over ``scene_depth_m``), its pixel height gives its height, and it stands on z = 0. Objects go into ``<name>_scene``.

A Studio engine (SAM 3D-class reconstruction is hardware-heavy: never local) is a plan for the whole scene, N objects x the action's price, one
confirm for the total; nothing is created by this call."""

import os

import bpy
import numpy as np
from mathutils import Vector

from . import common as C
from . import image3d as _i3d

MAX_OBJECTS = 16


def _studio_plan(n, engine):
    studio = engine.split(":", 1)[1]
    action, price = C.STUDIO_ACTIONS.get(("image_to_3d", studio), (None, None))
    if action is None:
        raise C.FeatureError(f"no studio:{studio} driver for reconstruction; studio:tripo is the one that exists")
    each = int(str(price).split()[0])
    return {"ok": False, "needs_approval": True, "studio": studio, "studio_action": C.STUDIO_ACTION_IDS.get(("image_to_3d", studio)), "objects": n,
            "credits_each": each, "total_credits": each * n,
            "error": f"{n} objects x {each} credits = {each * n} credits: nothing was created; the user confirms the whole plan once in the Client",
            "how": "show the total; on the user's confirm each part goes to the Studio and lands in the scene from there"}


def scene_from_image(root, image, masks=None, max_objects=8, name="lw_scene", engine="pipeline", scene_width_m=10.0, scene_depth_m=10.0, resolve=None):
    if not 1 <= int(max_objects) <= MAX_OBJECTS:
        raise C.FeatureError(f"max_objects is 1..{MAX_OBJECTS}")
    if engine.startswith("model:"):
        raise C.FeatureError("a reconstruction model is hardware-heavy: never local; use engine=pipeline, or studio:tripo (a priced plan)")
    if engine != "pipeline" and not engine.startswith("studio:"):
        raise C.FeatureError("engine is pipeline | studio:<name>")
    img = resolve(image)
    if not os.path.isfile(img):
        raise C.FeatureError(f"{image} is not a file")
    from PIL import Image
    W, H = Image.open(img).size
    from ..pipeline import segment_image as SI
    if masks:
        mask_paths = [resolve(m) for m in masks]
        boxes = []
        for m in mask_paths:
            _i3d.load_silhouette(m)                                     # refuses an empty mask
            ys, xs = np.nonzero(np.asarray(Image.open(m).convert("L")) > 127)
            boxes.append([int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1])
    else:
        out = os.path.join(root, "scenes", name, "masks")
        method = "alpha_components" if Image.open(img).mode in ("RGBA", "LA") else "color_regions"
        seg = SI.segment(img, out, method, min_pixels=max(200, W * H // 2000))
        mask_paths = [m["path"] for m in seg["masks"]]
        boxes = [m["bbox"] for m in seg["masks"]]
    n = len(mask_paths)
    if n == 0:
        raise C.FeatureError("no parts found in the image: pass masks (lampway_segment_image makes them)")
    if n > int(max_objects):
        raise C.FeatureError(f"the image holds {n} objects, more than max_objects {max_objects}: raise max_objects (up to {MAX_OBJECTS}) or pass fewer masks")
    if engine.startswith("studio:"):
        return _studio_plan(n, engine)
    if bpy.data.collections.get(f"{name}_scene") is not None:
        raise C.FeatureError(f"a scene named {name}_scene exists: pick another name")
    coll = bpy.data.collections.new(f"{name}_scene")
    bpy.context.scene.collection.children.link(coll)
    px_m = float(scene_width_m) / W
    order = sorted(range(n), key=lambda k: (boxes[k][0] + boxes[k][2]) / 2)
    objs = []
    for rank, k in enumerate(order):
        x0, y0, x1, y1 = boxes[k]
        height = (y1 - y0) * px_m
        res = _i3d.image_to_3d({"Front": mask_paths[k]}, size=height, resolution=48, mode="extrude", name=f"{name}_obj_{rank:02d}")
        ob = bpy.data.objects[res["object"]]
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        loc = Vector((((x0 + x1) / 2 - W / 2) * px_m, (1.0 - y1 / H) * float(scene_depth_m), 0.0))
        ob.location = loc
        objs.append({"name": ob.name, "mask": os.path.relpath(mask_paths[k], root), "bbox_px": boxes[k],
                     "pose": {"location": [round(v, 5) for v in loc], "rotation": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}})
    bpy.context.view_layer.update()
    return {"objects": objs, "scene_collection": coll.name, "image_size": [W, H],
            "placement": f"assumed camera: straight on, the image {scene_width_m} m wide over a {scene_depth_m} m deep ground plane; lower in the image is "
                         "nearer [UNVERIFIED accuracy]"}
