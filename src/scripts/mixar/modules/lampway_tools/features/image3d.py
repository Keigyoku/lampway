# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Image to 3D and multi-view. Proven code, no model: the VISUAL HULL (space carving of the silhouettes of the cardinal views),
a rounded EXTRUSION for the front+back paired-piece case, and a luminance RELIEF for one image. Silhouettes come from the alpha
channel, or from the difference to the corner colour when there is none. The mesh is the boundary of the carved voxels, smoothed
with Taubin (non-shrinking) filtering, and is judged by re-projecting it onto the views (IoU), watertightness and volume. The
generative slot (Tripo Smart Mesh from the four views, 100 credits) answers with action and price for approval.

View axes (camera looks at the origin, Z up): Front u=+X, Back u=-X, Right u=+Y, Left u=-Y."""

import math

import bmesh
import bpy
import numpy as np

from . import common as C

VIEWS = ("Front", "Back", "Left", "Right")
H_AXIS = {"Front": ("x", 1.0), "Back": ("x", -1.0), "Right": ("y", 1.0), "Left": ("y", -1.0)}


def load_silhouette(path) -> np.ndarray:
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)
    if (a[..., 3] < 250).any():
        mask = a[..., 3] > 127
    else:
        bg = a[0, 0, :3].astype(np.int32)
        mask = np.abs(a[..., :3].astype(np.int32) - bg).sum(axis=2) > 40
    ys, xs = np.nonzero(mask)
    if not len(ys):
        raise C.FeatureError(f"{path}: the silhouette is empty (no opaque pixels)")
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _sample(mask, s, h, z):
    """Is the point (horizontal coordinate h, height z), in metres, inside the cropped silhouette? (s = metres per pixel)"""
    hh, ww = mask.shape
    col = np.rint(ww / 2.0 + h / s - 0.5).astype(int)
    row = np.rint(hh - z / s - 0.5).astype(int)
    ok = (col >= 0) & (col < ww) & (row >= 0) & (row < hh)
    out = np.zeros(h.shape, dtype=bool)
    out[ok] = mask[row[ok], col[ok]]
    return out


def _mesh_from_voxels(occ, cell, origin):
    """Quads on the boundary of the occupied voxels -> (vertices, faces)."""
    verts, faces, index = [], [], {}

    def vid(p):
        if p not in index:
            index[p] = len(verts)
            verts.append(p)
        return index[p]
    padded = np.pad(occ, 1)
    for axis in range(3):
        for sign in (1, -1):
            shifted = np.roll(padded, -sign, axis=axis)
            exposed = padded & ~shifted
            for i, j, k in np.argwhere(exposed):
                c = np.array([i - 1, j - 1, k - 1])
                o = [axis, (axis + 1) % 3, (axis + 2) % 3]
                base = c.copy()
                if sign == 1:
                    base[axis] += 1
                quad = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    p = base.copy()
                    p[o[1]] += du
                    p[o[2]] += dv
                    quad.append(vid(tuple(int(x) for x in p)))
                faces.append(quad if sign == 1 else quad[::-1])
    v = np.asarray(verts, dtype=np.float64) * cell + origin
    return v, faces


def _taubin(verts, faces, iterations=8, lam=0.5, mu=-0.53):
    edges = {tuple(sorted((f[i], f[(i + 1) % len(f)]))) for f in faces for i in range(len(f))}
    e = np.array(sorted(edges))
    n = len(verts)
    deg = np.zeros(n)
    np.add.at(deg, e[:, 0], 1)
    np.add.at(deg, e[:, 1], 1)
    for _ in range(iterations):
        for k in (lam, mu):
            acc = np.zeros_like(verts)
            np.add.at(acc, e[:, 0], verts[e[:, 1]])
            np.add.at(acc, e[:, 1], verts[e[:, 0]])
            verts = verts + k * (acc / np.maximum(deg, 1)[:, None] - verts)
    return verts


def _to_object(name, verts, faces):
    for old in [o for o in bpy.data.objects if o.name == name]:
        bpy.data.objects.remove(old)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    volume = abs(bm.calc_volume(signed=True))
    boundary = sum(1 for ed in bm.edges if len(ed.link_faces) == 1)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    return ob, volume, boundary


def _distance_in(mask):
    """Chebyshev-style distance (in cells) of every inside cell to the outside, by repeated erosion."""
    d = np.zeros(mask.shape, dtype=np.int32)
    cur = mask.copy()
    k = 0
    while cur.any() and k < 400:
        k += 1
        d[cur] = k
        pad = np.pad(cur, 1)
        cur = cur & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return d


def image_to_3d(images, size=1.0, resolution=64, mode="hull", depth=None, profile="round", name="", engine="algorithmic",
                smooth=8):
    if engine != "algorithmic":
        return C.studio_slot("image_to_3d", engine)
    if mode not in ("hull", "extrude", "relief"):
        raise C.FeatureError(f"unknown mode {mode!r}; hull (silhouettes of two or more views) | extrude (front [+ back]) | relief (one image)")
    bad = [v for v in images if v not in VIEWS]
    if bad:
        raise C.FeatureError(f"unknown view(s) {bad}; the views are {', '.join(VIEWS)}")
    size, resolution = float(size), int(resolution)
    if not 8 <= resolution <= 160:
        raise C.FeatureError("resolution must be between 8 and 160")
    if mode == "relief":
        return _relief(images, size, resolution, float(depth if depth is not None else 0.2 * size), name or "lw_relief")
    sil = {v: load_silhouette(p) for v, p in images.items()}
    cell = size / resolution
    if mode == "hull":
        if len({H_AXIS[v][0] for v in sil}) < 2:
            raise C.FeatureError("a visual hull needs two views at right angles (e.g. Front + Left): the silhouettes of one axis give no depth")
        scale = {v: size / m.shape[0] for v, m in sil.items()}
        half = {"x": max([m.shape[1] * scale[v] / 2 for v, m in sil.items() if H_AXIS[v][0] == "x"], default=size / 4),
                "y": max([m.shape[1] * scale[v] / 2 for v, m in sil.items() if H_AXIS[v][0] == "y"], default=size / 4)}
    else:
        front = sil["Front"] if "Front" in sil else sil.get("Back")
        if front is None:
            raise C.FeatureError("extrude needs a Front (and optionally a Back) view")
        s0 = size / front.shape[0]
        half = {"x": front.shape[1] * s0 / 2}
        d = float(depth if depth is not None else 0.5 * front.shape[1] * s0)
        half["y"] = d / 2 + cell
        scale = {v: size / m.shape[0] for v, m in sil.items()}
    nx, ny, nz = [int(math.ceil(2 * half[a] / cell)) for a in ("x", "y")] + [resolution]
    xs = (np.arange(nx) + 0.5) * cell - nx * cell / 2
    ys = (np.arange(ny) + 0.5) * cell - ny * cell / 2
    zs = (np.arange(nz) + 0.5) * cell
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    occ = np.ones((nx, ny, nz), dtype=bool)
    grids = {}
    for v, m in sil.items():
        h = X if H_AXIS[v][0] == "x" else Y
        inside = _sample(m, scale[v], H_AXIS[v][1] * h, Z)
        grids[v] = inside
        occ &= inside
    if mode == "extrude":
        m2 = grids["Front"] if "Front" in grids else grids["Back"]
        mxz = m2[:, ny // 2, :]
        if "Front" in grids and "Back" in grids:
            mxz = mxz & grids["Back"][:, ny // 2, :]
        dist = _distance_in(mxz)
        cells_d = max(d / cell, 1.0)
        if profile == "round":
            r = max(cells_d / 2, 1.0)
            t = d * np.sqrt(np.clip(1 - (1 - np.minimum(dist / r, 1.0)) ** 2, 0, 1))
        elif profile == "slab":
            t = np.where(mxz, d, 0.0)
        else:
            raise C.FeatureError(f"unknown profile {profile!r}; round | slab")
        occ = mxz[:, None, :] & (np.abs(Y) < (t[:, None, :] / 2 + 1e-9))
        grids = {v: np.broadcast_to(mxz[:, None, :], occ.shape) for v in grids}
    if not occ.any():
        raise C.FeatureError("the silhouettes do not intersect: the hull is empty (check that the views show the same subject at the same height)")
    verts, faces = _mesh_from_voxels(occ, cell, np.array([-nx * cell / 2, -ny * cell / 2, 0.0]))
    if smooth:
        verts = _taubin(verts, faces, int(smooth))
    ob, volume, boundary = _to_object(name or f"lw_{mode}", verts, faces)
    iou = {}
    for v in sil:
        axis_h = 0 if H_AXIS[v][0] == "x" else 1
        proj = occ.any(axis=1 if axis_h == 0 else 0)
        sg = grids[v]
        sg2 = sg[:, 0, :] if axis_h == 0 else sg[0, :, :]
        if mode == "hull":
            sg2 = _sample(sil[v], scale[v], H_AXIS[v][1] * (xs if axis_h == 0 else ys)[:, None] * np.ones((1, nz)), zs[None, :] * np.ones((len(xs if axis_h == 0 else ys), 1)))
        union = (proj | sg2).sum()
        iou[v] = round(float((proj & sg2).sum() / union), 4) if union else 0.0
    return {"object": ob.name, "mode": mode, "report": {"faces": len(ob.data.polygons), "volume": round(float(volume), 6), "voxels": int(occ.sum()),
            "cell": round(cell, 5), "view_iou": iou, "watertight_boundary_edges": int(boundary),
            "dimensions": [round(float(x), 4) for x in ob.dimensions]}}


def _relief(images, size, resolution, depth, name):
    from PIL import Image
    path = images.get("Front") or next(iter(images.values()))
    im = Image.open(path).convert("L")
    aspect = im.width / im.height
    ny = resolution
    nx = max(2, int(round(resolution * aspect)))
    lum = np.asarray(im.resize((nx, ny), Image.LANCZOS), dtype=np.float64) / 255.0
    w = size * aspect
    xs = np.linspace(-w / 2, w / 2, nx)
    zs = np.linspace(size, 0.0, ny)
    verts = np.array([(xs[i], depth * lum[j, i], zs[j]) for j in range(ny) for i in range(nx)])
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    ob, _volume, boundary = _to_object(name, verts, faces)
    return {"object": ob.name, "mode": "relief", "report": {"faces": len(ob.data.polygons), "depth": depth, "open_boundary_edges": int(boundary),
            "dimensions": [round(float(x), 4) for x in ob.dimensions]}}
