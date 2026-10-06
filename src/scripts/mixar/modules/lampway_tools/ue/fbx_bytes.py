# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A minimal reader of binary FBX, for receipts and read-backs (specs/ue_parity/contracts/ue_export.md §6).

Two exports of the same scene differ only in ``FBXHeaderExtension/CreationTimeStamp`` (3 bytes, SCR/fbx_determinism_probe.json),
so ``content_sha256`` hashes the file with that element's Year..Millisecond fields zeroed: the same content, the same hash.
``facts`` reads what the read-back checks: each geometry's layer elements (tangents, binormals, smoothing), its polygon sizes
and triangle list, and each animation curve's key count. Pure Python (struct, zlib): it runs anywhere."""

import hashlib
import struct
import zlib

MAGIC = b"Kaydara FBX Binary  \x00"
_SCALAR = {"Y": ("<h", 2), "C": ("<?", 1), "I": ("<i", 4), "F": ("<f", 4), "D": ("<d", 8), "L": ("<q", 8)}
_ARRAY = {"f": ("f", 4), "d": ("d", 8), "l": ("q", 8), "i": ("i", 4), "b": ("?", 1)}


class FBXError(ValueError):
    pass


def _node(data, off, wide):
    if wide:
        end, nprops, plen = struct.unpack_from("<QQQ", data, off)
        off += 24
    else:
        end, nprops, plen = struct.unpack_from("<III", data, off)
        off += 12
    nlen = data[off]
    off += 1
    if end == 0:
        return None, off
    name = data[off:off + nlen].decode("ascii", "replace")
    off += nlen
    props, p = [], off
    for _ in range(nprops):
        t = chr(data[p])
        p += 1
        if t in _SCALAR:
            fmt, size = _SCALAR[t]
            props.append({"type": t, "value": struct.unpack_from(fmt, data, p)[0], "offset": p, "size": size})
            p += size
        elif t in _ARRAY:
            n, enc, clen = struct.unpack_from("<III", data, p)
            p += 12
            raw = data[p:p + clen]
            p += clen
            if enc == 1:
                raw = zlib.decompress(raw)
            code, size = _ARRAY[t]
            props.append({"type": t, "value": list(struct.unpack(f"<{n}{code}", raw[:n * size]))})
        elif t in "SR":
            (n,) = struct.unpack_from("<I", data, p)
            p += 4
            props.append({"type": t, "value": bytes(data[p:p + n])})
            p += n
        else:
            raise FBXError(f"unknown FBX property type {t!r} at byte {p - 1}")
    off += plen
    children = []
    while off < end:
        child, off = _node(data, off, wide)
        if child is None:
            break
        children.append(child)
    return {"name": name, "props": props, "children": children}, end


def parse(data: bytes):
    """(version, top-level nodes) of a binary FBX."""
    if not data.startswith(MAGIC):
        raise FBXError("not a binary FBX (the magic is missing)")
    (version,) = struct.unpack_from("<I", data, 23)
    wide = version >= 7500
    nodes, off = [], 27
    while off < len(data):
        node, off = _node(data, off, wide)
        if node is None:
            break
        nodes.append(node)
    return version, nodes


def _child(node, name):
    return next((c for c in node["children"] if c["name"] == name), None)


def _top(nodes, name):
    return next((n for n in nodes if n["name"] == name), None)


def content_sha256(data: bytes) -> str:
    """sha256 of the file with FBXHeaderExtension/CreationTimeStamp's Year..Millisecond zeroed (its Version kept)."""
    _, nodes = parse(data)
    buf = bytearray(data)
    hdr = _top(nodes, "FBXHeaderExtension")
    stamp = _child(hdr, "CreationTimeStamp") if hdr else None
    if stamp is None:
        raise FBXError("the FBX has no FBXHeaderExtension/CreationTimeStamp: not a file this receipt knows how to normalise")
    for c in stamp["children"]:
        if c["name"] == "Version":
            continue
        for pr in c["props"]:
            if "offset" in pr:
                buf[pr["offset"]:pr["offset"] + pr["size"]] = b"\0" * pr["size"]
    return hashlib.sha256(bytes(buf)).hexdigest()


def triangles(pvi):
    """The vertex-index list of a PolygonVertexIndex array (a polygon ends at a negative entry, stored as -(index + 1)), and
    whether every polygon is a triangle."""
    out, sizes, n = [], [], 0
    for v in pvi:
        n += 1
        out.append(v if v >= 0 else -v - 1)
        if v < 0:
            sizes.append(n)
            n = 0
    return out, bool(sizes) and all(s == 3 for s in sizes) and n == 0


def triangles_sha256(indices) -> str:
    return hashlib.sha256(struct.pack(f"<{len(indices)}i", *indices)).hexdigest()


def facts(data: bytes) -> dict:
    """What a read-back checks: per geometry its layer elements and triangles; the animation curves' key counts."""
    version, nodes = parse(data)
    objs = _top(nodes, "Objects") or {"children": []}
    geoms = []
    for g in (c for c in objs["children"] if c["name"] == "Geometry"):
        pvi = _child(g, "PolygonVertexIndex")
        tris, all_tri = triangles(pvi["props"][0]["value"]) if pvi else ([], False)
        geoms.append({"layers": sorted({c["name"] for c in g["children"] if c["name"].startswith("LayerElement")}),
                      "all_triangles": all_tri, "triangles_sha256": triangles_sha256(tris) if tris else None, "polygons": len(tris) // 3})
    keys = [len(_child(c, "KeyTime")["props"][0]["value"]) for c in objs["children"] if c["name"] == "AnimationCurve" and _child(c, "KeyTime")]
    return {"fbx_version": version, "geometries": geoms, "curve_key_counts": keys}
