# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Load a rebuild into the live scene beside the previous one.

Ported from the shelf's meshqa/load_live.py (SPIKE 2026-10-04): import the patched UV mesh, put it in the live frame
(turned about Z to the -Y front, lifted ``lift`` metres to stand on the floor), copy the textured material from the
template with its mask and height images pointed at the rebuild's directory, hide the previous version(s).
Everything that can be refused is refused BEFORE the import, so a bad call leaves the scene as it was.
"""

import math
import os

import bpy
from mathutils import Matrix

_IMAGE_MARKERS = ("mask_", "detail_height")


def _is_rebuild_image(node) -> bool:
    return node.type == "TEX_IMAGE" and node.image is not None and any(m in node.image.name for m in _IMAGE_MARKERS)


def load_rebuild(fbx, masks_dir, name, template_mat, hide=(), lift=0.0, turn=-90.0) -> dict:
    template = bpy.data.materials.get(template_mat)
    if template is None:
        raise LookupError(f"no template material {template_mat!r}; the scene has: {sorted(m.name for m in bpy.data.materials)}")
    wanted = sorted({os.path.basename(bpy.path.abspath(n.image.filepath))
                     for n in template.node_tree.nodes if _is_rebuild_image(n) and n.image.filepath})
    missing = [w for w in wanted if not os.path.exists(os.path.join(masks_dir, w))]
    if missing:
        raise FileNotFoundError(f"{', '.join(missing)} not found in {masks_dir}")
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=fbx)
    new = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before and bpy.data.objects[n].type == "MESH"]
    if not new:
        raise ValueError(f"{fbx} holds no mesh")
    ob = new[0]
    ob.name = name
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.transform(Matrix.Translation((0, 0, lift)) @ Matrix.Rotation(math.radians(turn), 4, "Z"))
    ob.data.update()
    m = template.copy()
    m.name = "textured_" + name
    for node in m.node_tree.nodes:
        if _is_rebuild_image(node):
            fn = os.path.basename(bpy.path.abspath(node.image.filepath))
            im = bpy.data.images.load(os.path.join(masks_dir, fn), check_existing=False)
            im.colorspace_settings.name = "Non-Color"
            node.image = im
    ob.data.materials.clear()
    ob.data.materials.append(m)
    hidden = []
    for h in hide:
        o = bpy.data.objects.get(h)
        if o:
            o.hide_set(True)
            o.hide_render = True
            hidden.append(h)
    ob.select_set(False)
    return {"name": ob.name, "polys": len(ob.data.polygons), "material": m.name, "hidden": hidden}
