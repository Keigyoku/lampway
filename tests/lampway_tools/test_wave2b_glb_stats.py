# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""model_compare statistics (specs/mrmak/05-model-compare.md): read a GLB without Blender (counts, textures, which channels were baked), polygon groups from consecutive triangles."""

import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import glb_stats as GS  # noqa: E402


def png(w, h):
    raw = b"".join(b"\x00" + b"\x80" * (w * 3) for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def glb(tris=1, textures=(), channels=(), ext=(), generator="Fixture 1.0", compress=None, triangle_only_indices=True):
    """A minimal GLB: one mesh of ``tris`` triangles (a strip), images for ``textures`` [(w, h)], material channel slots ``channels`` among base/normal/orm/occlusion/emissive."""
    verts = [(i * 0.5, 0.0, 0.0) for i in range(tris + 2)]
    pos = b"".join(struct.pack("<3f", *v) for v in verts)
    idx = b"".join(struct.pack("<3H", i, i + 1, i + 2) for i in range(tris))
    blob = bytearray()
    views, accessors, images, textures_j = [], [], [], []
    def add(data):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(data)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
        return len(views) - 1
    accessors.append({"bufferView": add(pos), "componentType": 5126, "count": len(verts), "type": "VEC3", "min": [0, 0, 0], "max": [len(verts) * 0.5, 0, 0]})
    accessors.append({"bufferView": add(idx), "componentType": 5123, "count": tris * 3, "type": "SCALAR"})
    for (w, h) in textures:
        images.append({"bufferView": add(png(w, h)), "mimeType": "image/png"})
        textures_j.append({"source": len(images) - 1})
    mat = {"pbrMetallicRoughness": {}}
    slot = {"base": ("pbrMetallicRoughness", "baseColorTexture"), "orm": ("pbrMetallicRoughness", "metallicRoughnessTexture"), "normal": (None, "normalTexture"),
            "occlusion": (None, "occlusionTexture"), "emissive": (None, "emissiveTexture")}
    for k, name in enumerate(channels):
        parent, key = slot[name]
        (mat["pbrMetallicRoughness"] if parent else mat)[key] = {"index": k}
    prim = {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
    j = {"asset": {"version": "2.0", "generator": generator}, "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accessors,
         "meshes": [{"primitives": [prim]}], "materials": [mat], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    if images:
        j["images"], j["textures"] = images, textures_j
    if ext:
        j["extensionsUsed"] = list(ext)
    if compress == "draco":
        j["extensionsUsed"] = list(j.get("extensionsUsed", [])) + ["KHR_draco_mesh_compression"]
        prim["extensions"] = {"KHR_draco_mesh_compression": {"bufferView": 0, "attributes": {"POSITION": 0}}}
    if compress == "meshopt":
        j["extensionsUsed"] = list(j.get("extensionsUsed", [])) + ["EXT_meshopt_compression"]
    js = json.dumps(j).encode()
    js += b" " * (-len(js) % 4)
    b = bytes(blob) + b"\x00" * (-len(blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(b)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(b), b"BIN\x00") + b


def test_the_counts_the_generator_the_textures_and_the_baked_channels_come_from_the_file_alone(tmp_path):
    p = tmp_path / "a.glb"
    p.write_bytes(glb(tris=3, textures=[(8, 4), (16, 16), (2, 2)], channels=("base", "orm", "occlusion"), generator="Tripo 3.0"))
    s = GS.read_stats(str(p))
    assert s["triangles"] == 3 and s["vertices"] == 5 and s["meshes"] == 1 and s["generator"] == "Tripo 3.0" and s["counts_from"] == "index" and s["compressed"] == "none"
    assert [(i["width"], i["height"]) for i in s["images"]] == [(8, 4), (16, 16), (2, 2)] and s["largest_texture_px"] == 16
    assert s["channels"] == {"base": True, "normal": False, "orm_packed": True, "occlusion": True, "emissive": False} and len(s["sha256"]) == 64 and s["bytes"] == p.stat().st_size
    roles = {i["index"]: i["role"] for i in s["images"]}
    assert roles == {0: "base", 1: "orm", 2: "occlusion"}


def test_channel_flags_flip_with_the_file_the_falsifier(tmp_path):
    p = tmp_path / "b.glb"
    p.write_bytes(glb(textures=[(4, 4)], channels=("base",)))
    assert GS.read_stats(str(p))["channels"]["normal"] is False
    p.write_bytes(glb(textures=[(4, 4), (4, 4)], channels=("base", "normal")))
    assert GS.read_stats(str(p))["channels"]["normal"] is True
    p.write_bytes(glb(textures=[(4, 4)], channels=("orm",)))
    assert GS.read_stats(str(p))["channels"]["orm_packed"] is True and GS.read_stats(str(p))["channels"]["base"] is False


def test_ngon_encoding_and_compression_are_read_from_the_extensions(tmp_path):
    p = tmp_path / "c.glb"
    p.write_bytes(glb(ext=("FB_ngon_encoding",)))
    assert GS.read_stats(str(p))["ngon_encoding"] is True
    p.write_bytes(glb(compress="draco"))
    s = GS.read_stats(str(p))
    assert s["compressed"] == "draco" and s["counts_from"] == "accessor"
    p.write_bytes(glb(compress="meshopt"))
    assert GS.read_stats(str(p))["compressed"] == "meshopt" and any("meshopt" in w for w in GS.read_stats(str(p))["warnings"])


def test_not_a_glb_and_a_truncated_one_are_refused_with_the_reason(tmp_path):
    p = tmp_path / "x.glb"
    p.write_bytes(b"not a glb at all")
    with pytest.raises(GS.GlbError, match="not a glTF binary"):
        GS.read_stats(str(p))
    good = glb()
    p.write_bytes(good[:40])
    with pytest.raises(GS.GlbError, match="truncated"):
        GS.read_stats(str(p))


def test_polygon_groups_two_triangles_sharing_the_first_index_make_one_quad_with_no_diagonal():
    quad = GS.polygon_outline([(0, 1, 2), (0, 2, 3)])
    assert sorted(map(sorted, quad)) == [[0, 1], [0, 3], [1, 2], [2, 3]]
    apart = GS.polygon_outline([(0, 1, 2), (1, 3, 2)])
    assert len(apart) == 6                                                        # different first indices: two separate triangles, six edges
    fan = GS.polygon_outline([(0, 1, 2), (0, 2, 3), (0, 3, 4)])
    assert sorted(map(sorted, fan)) == [[0, 1], [0, 4], [1, 2], [2, 3], [3, 4]]  # a pentagon: five outline edges, the diagonals are internal
