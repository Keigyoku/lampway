# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gaussian splat import. Proven code: the 3D Gaussian Splatting PLY layout decoded exactly as the format defines it (binary
little endian; x y z; f_dc_0..2 = the degree-0 spherical-harmonic colour, rgb = 0.5 + C0 * f_dc; opacity is a logit, sigmoid
applied; scale_0..2 are log-scales, exp applied), into ONE point object (no faces: a splat is not a mesh) with the attributes
``splat_color``, ``splat_opacity``, ``splat_radius`` and ``splat_scale`` and a geometry-nodes view (Mesh to Points with the
radius from the attribute, an emission material from the colour). Generating a splat from an image or text needs a world model
and is not wired."""

import bpy
import numpy as np

from . import common as C

C0 = 0.28209479177387814
_PLY = {"float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8", "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
        "ushort": "<u2", "uint16": "<u2", "short": "<i2", "int16": "<i2", "uint": "<u4", "uint32": "<u4", "int": "<i4", "int32": "<i4"}
REQUIRED = ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2")


def read_ply(path):
    with open(path, "rb") as fh:
        head = bytearray()
        while not head.endswith(b"end_header\n"):
            chunk = fh.read(1)
            if not chunk or len(head) > 65536:
                raise C.FeatureError(f"{path}: no PLY header")
            head += chunk
        lines = head.decode("ascii", "replace").splitlines()
        if lines[0].strip() != "ply":
            raise C.FeatureError(f"{path}: not a PLY file")
        fmt = next((ln for ln in lines if ln.startswith("format")), "")
        if "binary_little_endian" not in fmt:
            raise C.FeatureError(f"{path}: only binary_little_endian PLY is read (this one says {fmt.strip()!r})")
        count, props, in_vertex = 0, [], False
        for ln in lines:
            parts = ln.split()
            if parts[:1] == ["element"]:
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    count = int(parts[2])
            elif parts[:1] == ["property"] and in_vertex:
                if parts[1] == "list" or parts[1] not in _PLY:
                    raise C.FeatureError(f"{path}: unsupported vertex property {ln!r}")
                props.append((parts[2], _PLY[parts[1]]))
        missing = [p for p in REQUIRED if p not in {n for n, _t in props}]
        if missing:
            raise C.FeatureError(f"{path}: not a 3D Gaussian Splatting PLY; missing {', '.join(missing)} (expected x y z f_dc_0 f_dc_1 f_dc_2 opacity scale_0..2)")
        raw = np.frombuffer(fh.read(), dtype=np.dtype(props))
        if len(raw) < count:
            raise C.FeatureError(f"{path}: truncated: {len(raw)} of {count} vertices")
        return raw[:count]


def _view_group():
    name = "LW_SplatPoints"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    g = bpy.data.node_groups.new(name, "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n_in, n_out = g.nodes.new("NodeGroupInput"), g.nodes.new("NodeGroupOutput")
    pts = g.nodes.new("GeometryNodeMeshToPoints")
    pts.mode = "VERTICES"
    rad = g.nodes.new("GeometryNodeInputNamedAttribute")
    rad.data_type = "FLOAT"
    rad.inputs["Name"].default_value = "splat_radius"
    mat = g.nodes.new("GeometryNodeSetMaterial")
    mat.inputs["Material"].default_value = _material()
    g.links.new(n_in.outputs[0], pts.inputs["Mesh"])
    g.links.new(rad.outputs["Attribute"], pts.inputs["Radius"])
    g.links.new(pts.outputs["Points"], mat.inputs["Geometry"])
    g.links.new(mat.outputs["Geometry"], n_out.inputs[0])
    return g


def _material():
    name = "LW_SplatMat"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        t.nodes.remove(n)
    out, emit, attr = t.nodes.new("ShaderNodeOutputMaterial"), t.nodes.new("ShaderNodeEmission"), t.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "splat_color"
    attr.attribute_type = "GEOMETRY"
    t.links.new(attr.outputs["Color"], emit.inputs["Color"])
    t.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return m


def splat_import(path, max_points=200000, name="lw_splat"):
    raw = read_ply(path)
    total = len(raw)
    keep = np.arange(total)
    max_points = int(max_points)
    if max_points and total > max_points:
        keep = np.sort(np.random.default_rng(0).choice(total, size=max_points, replace=False))
    sel = raw[keep]
    n = len(sel)
    co = np.stack([sel["x"], sel["y"], sel["z"]], axis=1).astype(np.float32)
    rgb = np.clip(0.5 + C0 * np.stack([sel["f_dc_0"], sel["f_dc_1"], sel["f_dc_2"]], axis=1), 0.0, 1.0).astype(np.float32)
    opacity = (1.0 / (1.0 + np.exp(-sel["opacity"].astype(np.float64)))).astype(np.float32)
    scales = np.exp(np.stack([sel["scale_0"], sel["scale_1"], sel["scale_2"]], axis=1).astype(np.float64)).astype(np.float32)
    for old in [o for o in bpy.data.objects if o.name == name]:
        bpy.data.objects.remove(old)
    me = bpy.data.meshes.new(name)
    me.vertices.add(n)
    me.vertices.foreach_set("co", co.reshape(-1))
    me.update()
    rgba = np.concatenate([rgb, opacity[:, None]], axis=1)
    me.attributes.new("splat_color", "FLOAT_COLOR", "POINT").data.foreach_set("color", rgba.reshape(-1))
    me.attributes.new("splat_opacity", "FLOAT", "POINT").data.foreach_set("value", opacity)
    me.attributes.new("splat_radius", "FLOAT", "POINT").data.foreach_set("value", scales.mean(axis=1))
    me.attributes.new("splat_scale", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", scales.reshape(-1))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("LW_Splat", "NODES")
    mod.node_group = _view_group()
    bpy.context.view_layer.update()
    lo, hi = co.min(axis=0), co.max(axis=0)
    return {"object": ob.name, "splats": n, "source_splats": total, "bounds": [[round(float(a), 4) for a in lo], [round(float(a), 4) for a in hi]],
            "note": "a splat is a separate object: it has no faces and is not converted to a mesh"}
