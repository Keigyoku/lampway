# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Independent three-frame pixel reference, copied from procedural_library.py.

Original commit: 0da106ec0d0a2d75a740147f84a8f830b6d5e43a
Original blob: c2a5914d3c98991f95d223fc208002f156bce7ae
Only the public statistics reduction is omitted; return all real linear pixels.
"""
import json
from pathlib import Path
import bpy
from mixar.modules.lampway_tools.features.procedural_library import _build, canon_io
_BAKES = {}

def render_reference(pid: str, params: dict, size: int, out_png=None, tmp_dir=None):
    """Three 1-sample EEVEE renders of a top-down plane whose emission is the probe's Base Color, Metallic and Roughness outputs."""
    key = (pid, json.dumps(params, sort_keys=True), size)
    if key in _BAKES and out_png is None:
        return _BAKES[key]
    g, _ms = _build(pid, probe=True)
    import tempfile
    own = None if tmp_dir else tempfile.TemporaryDirectory(prefix="lw_probe_")      # a probe's EXRs are deleted one by one; its folder goes with the probe
    scratch = Path(tmp_dir) if tmp_dir else Path(own.name)
    scratch.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes.new("lw_probe")
    mat = bpy.data.materials.new("lw_probe_mat")
    me = bpy.data.meshes.new("lw_probe_plane")
    me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("lw_probe_plane", me)
    cam = bpy.data.objects.new("lw_probe_cam", bpy.data.cameras.new("lw_probe_cam"))
    try:
        sc.collection.objects.link(ob)
        sc.collection.objects.link(cam)
        cam.data.type, cam.data.ortho_scale = "ORTHO", 1.0
        cam.location = (0, 0, 2)
        sc.camera = cam
        me.materials.append(mat)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = g
        for k, v in (params or {}).items():
            if k in grp.inputs:
                grp.inputs[k].default_value = v
        em = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        sc.render.engine = "BLENDER_EEVEE"                        # an emission readout: EEVEE renders it exactly; never Cycles beside the user's live work
        sc.eevee.taa_render_samples = 1
        sc.render.resolution_x = sc.render.resolution_y = size
        sc.render.resolution_percentage = 100
        sc.view_settings.view_transform = "Standard"
        sc.world = bpy.data.worlds.new("lw_probe_world")
        sc.world.color = (0, 0, 0)
        sc.render.image_settings.file_format = "OPEN_EXR"
        sc.render.image_settings.color_depth = "32"
        sc.render.film_transparent = False
        res = {}
        import numpy as np
        for name in ("Base Color", "Metallic", "Roughness"):
            for l in list(nt.links):
                if l.to_node is em:
                    nt.links.remove(l)
            nt.links.new(grp.outputs[name], em.inputs["Color"])
            exr = scratch / f"probe_{name.replace(' ', '_')}.exr"
            sc.render.filepath = str(exr)
            bpy.ops.render.render(write_still=True, scene=sc.name)
            img = canon_io.load_image(str(exr))
            w, h = img.size
            res[name] = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, :3]
            bpy.data.images.remove(img)
            exr.unlink()
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.objects.remove(cam)
        bpy.data.scenes.remove(sc)
        bpy.data.materials.remove(mat)
        bpy.data.meshes.remove(me)
        g2 = bpy.data.node_groups.get("LWPP_" + pid)
        if g2 is not None:
            bpy.data.node_groups.remove(g2)
        if own is not None:
            own.cleanup()
    return res
