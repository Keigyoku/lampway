# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Statistics read from a GLB file alone, no Blender and no pixel decoding (specs/mrmak/05-model-compare.md section 6.1), and the polygon outline of an n-gon-encoded triangle list.

glTF packs roughness (G) and metalness (B) into ONE image, so there is one ``orm_packed`` flag. Counts from a compressed primitive are accessor counts, labelled ``counts_from: accessor``.
The GLB container is parsed with the stdlib only (magic, version, chunk table)."""

import base64
import hashlib
import json
import struct
from pathlib import Path


class GlbError(ValueError):
    pass


def _chunks(data: bytes):
    if len(data) < 12 or data[:4] != b"glTF":
        raise GlbError("not a glTF binary (no 'glTF' magic): export GLB, or give a .glb file")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise GlbError(f"glTF version {version} is not supported (2 only)")
    if total > len(data):
        raise GlbError(f"truncated glTF binary: the header says {total} bytes, the file has {len(data)}")
    out, off = [], 12
    while off + 8 <= total:
        n, kind = struct.unpack_from("<I4s", data, off)
        if off + 8 + n > len(data):
            raise GlbError("truncated glTF binary: a chunk runs past the end of the file")
        out.append((kind, data[off + 8: off + 8 + n]))
        off += 8 + n
    return out


def _image_size(b: bytes):
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24:
        return struct.unpack(">II", b[16:24])
    if b[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            marker = b[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", b[i + 5: i + 9])
                return w, h
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + struct.unpack(">H", b[i + 2: i + 4])[0]
    return None, None


def read_stats(path: str) -> dict:
    p = Path(path)
    data = p.read_bytes()
    chunks = _chunks(data)
    js = next((c for k, c in chunks if k == b"JSON"), None)
    if js is None:
        raise GlbError("the glTF binary has no JSON chunk")
    j = json.loads(js.decode("utf-8"))
    binchunk = next((c for k, c in chunks if k.rstrip(b"\x00") == b"BIN"), b"")
    used = set(j.get("extensionsUsed", []))
    compressed = "draco" if "KHR_draco_mesh_compression" in used else "meshopt" if used & {"EXT_meshopt_compression", "KHR_meshopt_compression"} else "none"
    acc, views = j.get("accessors", []), j.get("bufferViews", [])
    pos_acc, tris, prims, uv_sets = set(), 0, 0, 0
    lo, hi = None, None
    for m in j.get("meshes", []):
        for pr in m.get("primitives", []):
            prims += 1
            attrs = pr.get("attributes", {})
            if "POSITION" in attrs:
                pos_acc.add(attrs["POSITION"])
            uv_sets = max(uv_sets, sum(1 for k in attrs if k.startswith("TEXCOORD_")))
            mode = pr.get("mode", 4)
            if mode != 4:
                continue
            if "indices" in pr:
                tris += acc[pr["indices"]]["count"] // 3
            elif "POSITION" in attrs:
                tris += acc[attrs["POSITION"]]["count"] // 3
    verts = sum(acc[i]["count"] for i in pos_acc)
    for i in pos_acc:
        a = acc[i]
        if "min" in a and "max" in a:
            lo = a["min"] if lo is None else [min(x, y) for x, y in zip(lo, a["min"])]
            hi = a["max"] if hi is None else [max(x, y) for x, y in zip(hi, a["max"])]
    roles = {}
    mats = j.get("materials", [])
    textures = j.get("textures", [])
    channels = {"base": False, "normal": False, "orm_packed": False, "occlusion": False, "emissive": False}
    for mat in mats:
        pbr = mat.get("pbrMetallicRoughness", {})
        for slot, key, role, src in (("base", "baseColorTexture", "base", pbr), ("orm_packed", "metallicRoughnessTexture", "orm", pbr), ("normal", "normalTexture", "normal", mat),
                                     ("occlusion", "occlusionTexture", "occlusion", mat), ("emissive", "emissiveTexture", "emissive", mat)):
            ref = src.get(key)
            if ref is not None:
                channels[slot] = True
                src_img = textures[ref["index"]].get("source") if ref["index"] < len(textures) else None
                if src_img is not None:
                    roles.setdefault(src_img, role)
    images = []
    for n, im in enumerate(j.get("images", [])):
        w = h = None
        raw = None
        if "bufferView" in im and im["bufferView"] < len(views):
            v = views[im["bufferView"]]
            raw = binchunk[v.get("byteOffset", 0): v.get("byteOffset", 0) + v["byteLength"]]
        elif str(im.get("uri", "")).startswith("data:"):
            raw = base64.b64decode(im["uri"].split(",", 1)[1])
        if raw:
            w, h = _image_size(raw)
        images.append({"index": n, "width": w, "height": h, "role": roles.get(n, "unknown")})
    warnings = []
    if compressed == "meshopt":
        warnings.append("this file needs the meshopt decoder: stats are shown, the 3D view is not")
    if compressed == "draco":
        warnings.append("Draco-compressed geometry: counts are accessor counts")
    sizes = [max(i["width"] or 0, i["height"] or 0) for i in images]
    return {"file": p.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "generator": (j.get("asset") or {}).get("generator"), "extensions_used": sorted(used),
            "ngon_encoding": "FB_ngon_encoding" in used, "compressed": compressed, "meshes": len(j.get("meshes", [])), "primitives": prims, "triangles": tris, "vertices": verts,
            "counts_from": "accessor" if compressed != "none" else "index", "materials": len(mats), "images": images, "largest_texture_px": max(sizes) if sizes else 0, "channels": channels,
            "bbox_m": [round(b - a, 6) for a, b in zip(lo, hi)] if lo is not None else None, "unit_scale_note": "glTF is metres", "uv_sets": uv_sets, "warnings": warnings}


def polygon_outline(triangles) -> list:
    """Edges of the polygons an n-gon-encoded triangle list stands for: consecutive triangles that share the same FIRST index form one polygon; an edge used once inside a group is
    outline, an edge used twice is an internal diagonal. A list that is not n-gon encoded must not be passed here (never merge on a hunch)."""
    groups, cur = [], []
    for t in triangles:
        if cur and cur[0][0] != t[0]:
            groups.append(cur)
            cur = []
        cur.append(t)
    if cur:
        groups.append(cur)
    edges = []
    for g in groups:
        count = {}
        order = []
        for a, b, c in g:
            for e in ((a, b), (b, c), (c, a)):
                k = tuple(sorted(e))
                if k not in count:
                    order.append(e)
                count[k] = count.get(k, 0) + 1
        edges += [e for e in order if count[tuple(sorted(e))] == 1]
    return edges
