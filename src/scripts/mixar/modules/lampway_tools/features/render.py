# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A clay render of ONE object from a cardinal view (orthographic, Workbench, transparent film), cropped to the subject's bounding
box: the conditioning image for the image slot and the framing convention every projection uses (the subject's height fills the
image height; the subject is centred horizontally)."""

import bpy
import numpy as np
from mathutils import Vector

from . import common as C

#: the direction from the subject TOWARD the camera, per view (Front = the camera at -Y)
TO_CAMERA = {"Front": (0.0, -1.0, 0.0), "Back": (0.0, 1.0, 0.0), "Left": (-1.0, 0.0, 0.0), "Right": (1.0, 0.0, 0.0)}


def bbox_world(ob):
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return Vector([min(c[i] for c in corners) for i in range(3)]), Vector([max(c[i] for c in corners) for i in range(3)])


def render_view(ob, view, size, out_path, shading=None):
    """``shading``: Workbench shading attributes that replace the clay's (e.g. a flat material colour pass); anti-aliasing is then off and the view
    transform Standard, so every pixel is an exact flat colour from the same camera as the clay render."""
    if view not in TO_CAMERA:
        raise C.FeatureError(f"unknown view {view!r}; the views are {', '.join(TO_CAMERA)}")
    lo, hi = bbox_world(ob)
    center = (lo + hi) / 2
    dim = hi - lo
    ext = max(dim.x, dim.y, dim.z) * 1.15
    sc = bpy.data.scenes.new("lw_view")
    cam_data = bpy.data.cameras.new("lw_view_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = ext
    cam = bpy.data.objects.new("lw_view_cam", cam_data)
    try:
        sc.collection.objects.link(ob)
        sc.collection.objects.link(cam)
        d = Vector(TO_CAMERA[view])
        cam.location = center + d * (ext * 2 + dim.length)
        target = bpy.data.objects.new("lw_view_target", None)
        target.location = center
        sc.collection.objects.link(target)
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
        sc.camera = cam
        r = sc.render
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x = r.resolution_y = int(size)
        r.resolution_percentage = 100
        r.film_transparent = True
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        sh = sc.display.shading
        sh.light, sh.color_type, sh.single_color = "FLAT", "SINGLE", (0.78, 0.78, 0.78)
        if shading:
            for k, v in shading.items():
                setattr(sh, k, v)
            sc.display.render_aa = "OFF"
            sc.view_settings.view_transform, sc.view_settings.look = "Standard", "None"
        r.filepath = out_path
        bpy.ops.render.render(write_still=True, scene=sc.name)
    finally:
        for o in (cam, bpy.data.objects.get("lw_view_target")):
            if o is not None:
                bpy.data.objects.remove(o)
        sc.collection.objects.unlink(ob) if ob.name in sc.collection.objects else None
        bpy.data.scenes.remove(sc)
        bpy.data.cameras.remove(cam_data)
    return crop_to_subject(out_path)


def crop_to_subject(path):
    """Crop the PNG at ``path`` to the bounding box of its opaque pixels (in place); returns (width, height)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)[..., 3] > 8
    ys, xs = np.nonzero(a)
    if len(ys):
        im = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    im.save(path)
    return im.size
