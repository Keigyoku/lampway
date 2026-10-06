# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""multi_piece_material (specs/wiki/multi_piece_material.md): one material language across separate pieces through ONE shared texturing pass.

merge     copies of the pieces joined in world space into ``<first>_proxy``: every face keeps its piece (int face attribute ``lw_piece``) and its ORIGINAL
          UV (layer ``lw_orig``), and gets a shared, non-overlapping atlas (layer ``lw_shared``, smart project). The proxy's geometry and both UV layers are
          hashed: texture the proxy (any texturing tool, on ``lw_shared``), never edit it. The texel density each piece gets in the shared atlas is compared
          with its own layout at ``individual_res``.
transfer  the painted atlas goes back to each piece's ORIGINAL UVs: every texel of a piece's own layout is located in its triangle (barycentric) and the same
          point is read from the shared atlas; the result is ``<piece>_mpm`` (a copy) with ``<piece>_mpm_shared`` as its base colour. Refused when the
          proxy changed after merge. The proxy is removed after a transfer unless keep_proxy.
Pieces whose world bounds overlap are refused (the proxy would fuse them)."""

import hashlib
import json
import os

import bpy
import numpy as np

from . import common as C
from . import workflows as W

PROP = "lw_proxy"


def _bounds(ob):
    from mathutils import Vector
    pts = np.array([list(ob.matrix_world @ Vector(c)) for c in ob.bound_box])
    return pts.min(axis=0), pts.max(axis=0)


def _uv_area(tris):
    return np.abs((tris[:, 1, 0] - tris[:, 0, 0]) * (tris[:, 2, 1] - tris[:, 0, 1]) - (tris[:, 2, 0] - tris[:, 0, 0]) * (tris[:, 1, 1] - tris[:, 0, 1])).sum() / 2


def _tri_arrays(me, faces, layer):
    uv = me.uv_layers[layer].data
    co = [v.co for v in me.vertices]
    tu, t3 = [], []
    for f in faces:
        li = list(me.polygons[f].loop_indices)
        vi = list(me.polygons[f].vertices)
        for k in range(1, len(li) - 1):
            tu.append([uv[li[0]].uv[:], uv[li[k]].uv[:], uv[li[k + 1]].uv[:]])
            t3.append([co[vi[0]][:], co[vi[k]][:], co[vi[k + 1]][:]])
    return np.array(tu, dtype=np.float64).reshape(-1, 3, 2), np.array(t3, dtype=np.float64).reshape(-1, 3, 3)


def _hash(me) -> str:
    h = hashlib.sha256()
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    h.update(co.tobytes())
    for name in ("lw_orig", "lw_shared"):
        uv = np.empty(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers[name].data.foreach_get("uv", uv)
        h.update(uv.tobytes())
    return h.hexdigest()


def merge(pieces, atlas_res=4096, individual_res=None, density_floor_ratio=0.7, name=""):
    obs = [C.need_object(n) for n in (pieces or [])]
    if not 2 <= len(obs) <= 8:
        raise C.FeatureError("pieces names 2..8 mesh objects")
    for o in obs:
        if not o.data.uv_layers or o.data.uv_layers.active is None:
            raise C.FeatureError(f"{o.name} has no UV layer: unwrap it first (lampway_uv_unwrap); its own layout is where the shared texture returns")
    if int(atlas_res) not in (128, 256, 512, 1024, 2048, 4096):
        raise C.FeatureError("atlas_res is 2048 | 4096 (or a smaller power of two for a draft)")
    floor = float(density_floor_ratio)
    if not 0.3 <= floor <= 1.0:
        raise C.FeatureError("density_floor_ratio is 0.3..1")
    bb = [_bounds(o) for o in obs]
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            if np.all(bb[i][0] <= bb[j][1]) and np.all(bb[j][0] <= bb[i][1]):
                raise C.FeatureError(f"pieces overlap; move them apart for the proxy only ({obs[i].name} and {obs[j].name})")
    verts, faces, uvs, piece = [], [], [], []
    for k, o in enumerate(obs):
        me, mw, base = o.data, o.matrix_world, len(verts)
        verts += [tuple(mw @ v.co) for v in me.vertices]
        uvl = me.uv_layers.active.data
        for p in me.polygons:
            faces.append(tuple(base + v for v in p.vertices))
            uvs += [tuple(uvl[li].uv) for li in p.loop_indices]
            piece.append(k)
    pname = name or obs[0].name + "_proxy"
    me = bpy.data.meshes.new(pname)
    me.from_pydata(verts, [], faces)
    orig = me.uv_layers.new(name="lw_orig")
    orig.data.foreach_set("uv", np.array(uvs, dtype=np.float32).ravel())
    shared = me.uv_layers.new(name="lw_shared")
    me.uv_layers.active = shared
    a = me.attributes.new("lw_piece", "INT", "FACE")
    a.data.foreach_set("value", np.array(piece, dtype=np.int32))
    me.update()
    prox = bpy.data.objects.new(pname, me)
    bpy.context.scene.collection.objects.link(prox)
    C.activate(prox)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=2.0 / int(atlas_res) * 4, correct_aspect=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    me.uv_layers.active = me.uv_layers["lw_shared"]
    ind = int(individual_res or atlas_res)
    density = []
    for k, o in enumerate(obs):
        fs = [i for i, p in enumerate(piece) if p == k]
        tu_o, t3 = _tri_arrays(me, fs, "lw_orig")
        tu_s, _ = _tri_arrays(me, fs, "lw_shared")
        a3 = np.linalg.norm(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]), axis=1).sum() / 2
        di = float(np.sqrt(_uv_area(tu_o) / a3)) * ind if a3 > 0 else 0.0
        ds = float(np.sqrt(_uv_area(tu_s) / a3)) * int(atlas_res) if a3 > 0 else 0.0
        ratio = ds / di if di > 0 else 0.0
        density.append({"object": o.name, "texel_density_individual": round(di, 3), "texel_density_shared": round(ds, 3), "ratio": round(ratio, 4), "pass": ratio >= floor})
    prox[PROP] = json.dumps({"pieces": [o.name for o in obs], "atlas_res": int(atlas_res), "hash": _hash(me)})
    return {"proxy": prox.name, "pieces": [o.name for o in obs], "atlas_res": int(atlas_res), "uv_layer": "lw_shared", "density": density,
            "density_floor_ratio": floor, "density_floor_status": "UNVERIFIED",
            "how": f"texture {prox.name} on its lw_shared UVs (do not edit its geometry or UVs), then multi_piece_material action=transfer with the atlas"}


def _raster_transfer(tu_o, tu_s, atlas, res):
    H, W = atlas.shape[:2]
    out = np.zeros((res, res, 4), np.uint8)
    for to, ts in zip(tu_o, tu_s):
        p = to * res
        x0, y0 = np.floor(p.min(axis=0)).astype(int).clip(0, res - 1)
        x1, y1 = np.ceil(p.max(axis=0)).astype(int).clip(0, res - 1)
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
        if abs(d) < 1e-12:
            continue
        l0 = ((p[1, 1] - p[2, 1]) * (gx - p[2, 0]) + (p[2, 0] - p[1, 0]) * (gy - p[2, 1])) / d
        l1 = ((p[2, 1] - p[0, 1]) * (gx - p[2, 0]) + (p[0, 0] - p[2, 0]) * (gy - p[2, 1])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9)
        if not m.any():
            continue
        su = l0 * ts[0, 0] + l1 * ts[1, 0] + l2 * ts[2, 0]
        sv = l0 * ts[0, 1] + l1 * ts[1, 1] + l2 * ts[2, 1]
        ax = np.clip((su * W).astype(int), 0, W - 1)
        ay = np.clip(((1 - sv) * H).astype(int), 0, H - 1)
        yy, xx = np.nonzero(m)
        ty = (res - 1) - (yy + y0)                               # image rows run top down; UV v runs up
        out[ty, xx + x0, :3] = atlas[ay[m], ax[m], :3]
        out[ty, xx + x0, 3] = 255
    return out


def transfer(proxy, atlas, out_dir, res=None, keep_proxy=False):
    from PIL import Image
    prox = C.need_object(proxy)
    rec = json.loads(prox.get(PROP) or "{}")
    if not rec:
        raise C.FeatureError(f"{prox.name} is not a multi_piece_material proxy: run action=merge first")
    if _hash(prox.data) != rec["hash"]:
        raise C.FeatureError("the proxy changed after merge; re-merge (its geometry and UVs must stay as merged for the texture to find its way back)")
    if not os.path.exists(atlas):
        raise FileNotFoundError(f"atlas {atlas} not found")
    img = np.asarray(Image.open(atlas).convert("RGBA"))
    res = int(res or rec["atlas_res"])
    os.makedirs(out_dir, exist_ok=True)
    me = prox.data
    piece = np.empty(len(me.polygons), dtype=np.int64)
    me.attributes["lw_piece"].data.foreach_get("value", piece)
    rows = []
    for k, name in enumerate(rec["pieces"]):
        src = C.need_object(name)
        fs = np.nonzero(piece == k)[0].tolist()
        tu_o, _ = _tri_arrays(me, fs, "lw_orig")
        tu_s, _ = _tri_arrays(me, fs, "lw_shared")
        tex = _raster_transfer(tu_o, tu_s, img, res)
        path = os.path.join(out_dir, f"{name}_mpm_shared.png")
        Image.fromarray(tex, "RGBA").save(path)
        new = C.duplicate(src, "_mpm")
        mat = bpy.data.materials.new(f"{name}_mpm_shared")
        mat.use_nodes = True
        t = mat.node_tree
        node = t.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(path, check_existing=False)
        t.links.new(node.outputs["Color"], next(n for n in t.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"])
        new.data.materials.clear()
        new.data.materials.append(mat)
        rows.append({"source": name, "object": new.name, "texture": path, "material": mat.name, "covered_texels": int((tex[..., 3] > 0).sum())})
    if not keep_proxy:
        pm = prox.data
        bpy.data.objects.remove(prox)
        bpy.data.meshes.remove(pm)
    return {"per_piece": rows, "atlas": atlas, "res": res, "proxy_kept": bool(keep_proxy),
            "note": "check inside/outside, the wearer's left/right, strap paths and trim joins on each piece before accepting (the wiki's acceptance checks)"}


def run(action, root, pieces=None, atlas_res=4096, individual_res=None, density_floor_ratio=0.7, proxy="", atlas="", out_dir="mpm", res=None, keep_proxy=False, name=""):
    if action == "merge":
        return merge(pieces, atlas_res, individual_res, density_floor_ratio, name)
    if action == "transfer":
        return transfer(proxy, atlas, out_dir, res, keep_proxy)
    raise C.FeatureError("action is merge | transfer")
