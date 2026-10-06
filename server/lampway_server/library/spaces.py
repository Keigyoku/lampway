"""The deterministic embedding spaces (no network, no model): ``image_hist``, ``image_dhash`` and the ``shape_d2`` shape descriptor.

Everything here is a pure function of the file's bytes (and, for shapes, of the version's content key as the RNG seed), so a descriptor is reproducible.
Scale is deliberately removed from shape (a helmet and its 2x variant match); ``dim_*`` stays a filterable stat."""
from __future__ import annotations

import io
import json
import struct

import numpy as np

D2_BINS, A3_BINS, D1_BINS = 64, 32, 32
N_POINTS, N_PAIRS, N_TRIPLES = 20000, 200000, 50000
_COMPONENT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}


def _rgb32(path):
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB").resize((32, 32)), dtype=np.int64)


def image_hist(path) -> np.ndarray:
    """4x4x4 RGB histogram of a 32x32 thumbnail, L2-normalised: colour only, kept for parity with the legacy asset search."""
    a = _rgb32(path) // 64
    idx = a[:, :, 0] * 16 + a[:, :, 1] * 4 + a[:, :, 2]
    h = np.bincount(idx.reshape(-1), minlength=64).astype("float64")
    return (h / np.linalg.norm(h)).astype("float32")


def image_dhash(path) -> np.ndarray:
    """64-bit difference hash as 64 floats (0/1), bit order identical to the ingest's hex ``dhash`` (MSB first, row-major)."""
    from PIL import Image
    with Image.open(path) as im:
        g = np.asarray(im.convert("L").resize((9, 8)), dtype=np.int64)
    return (g[:, :-1] > g[:, 1:]).astype("float32").reshape(-1)


def hamming(a, b) -> int:
    return int(np.count_nonzero((np.asarray(a) > 0) != (np.asarray(b) > 0)))


def glb_triangles(src) -> np.ndarray:
    """(T, 3, 3) float32 triangles from a GLB's BIN chunk (triangle-list primitives; node transforms are not applied)."""
    fh = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else open(src, "rb")
    with fh:
        head = fh.read(12)
        if head[:4] != b"glTF":
            raise ValueError("not a GLB")
        doc, binary = None, b""
        while True:
            ch = fh.read(8)
            if len(ch) < 8:
                break
            n, t = struct.unpack("<II", ch)
            body = fh.read(n)
            if t == 0x4E4F534A:
                doc = json.loads(body)
            elif t == 0x004E4942:
                binary = body
    out = []

    def read(acc_i):
        acc = doc["accessors"][acc_i]
        view = doc["bufferViews"][acc["bufferView"]]
        comp = np.dtype(_COMPONENT[acc["componentType"]])
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
        off = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or comp.itemsize * ncomp
        if stride == comp.itemsize * ncomp:
            return np.frombuffer(binary, comp, acc["count"] * ncomp, off).reshape(acc["count"], ncomp)
        raw = np.frombuffer(binary, np.uint8, offset=off, count=stride * (acc["count"] - 1) + comp.itemsize * ncomp)
        return np.stack([np.frombuffer(raw[i * stride:i * stride + comp.itemsize * ncomp].tobytes(), comp) for i in range(acc["count"])])

    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                continue
            pos = read(prim["attributes"]["POSITION"]).astype("float32")
            idx = read(prim["indices"]).reshape(-1).astype("int64") if "indices" in prim else np.arange(len(pos))
            idx = idx[: len(idx) // 3 * 3].reshape(-1, 3)
            out.append(pos[idx])
    if not out:
        raise ValueError("no triangle primitives")
    return np.concatenate(out)


def _hist(x, bins, hi):
    h = np.bincount(np.minimum((x / hi * bins).astype(int), bins - 1), minlength=bins).astype("float64")
    return h / h.sum()


def shape_d2(tris: np.ndarray, content_key: str) -> np.ndarray:
    """D2 (distances between random surface point pairs, divided by their mean), A3 (angles at the middle point of random triples) and D1 (distance from the centroid,
    divided by its mean): 64 + 32 + 32 = 128 floats, each block L1-normalised. Area-weighted points; the RNG is seeded from the first 8 bytes of ``content_key``."""
    rng = np.random.Generator(np.random.PCG64(int.from_bytes(bytes.fromhex(content_key)[:8], "big")))
    t = tris.astype("float64")
    cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    area = np.linalg.norm(cross, axis=1) / 2
    if not area.sum() > 0:
        raise ValueError("mesh has no surface area")
    cdf = np.cumsum(area) / area.sum()
    pick = np.minimum(np.searchsorted(cdf, rng.random(N_POINTS)), len(t) - 1)
    r1, r2 = np.sqrt(rng.random(N_POINTS)), rng.random(N_POINTS)
    p = (1 - r1)[:, None] * t[pick, 0] + (r1 * (1 - r2))[:, None] * t[pick, 1] + (r1 * r2)[:, None] * t[pick, 2]
    i, j = rng.integers(0, N_POINTS, N_PAIRS), rng.integers(0, N_POINTS, N_PAIRS)
    d2 = np.linalg.norm(p[i] - p[j], axis=1)
    d2 = d2 / d2.mean()
    a, b, c = (rng.integers(0, N_POINTS, N_TRIPLES) for _ in range(3))
    u, w = p[a] - p[b], p[c] - p[b]
    den = np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1)
    ok = den > 1e-12
    ang = np.arccos(np.clip((u[ok] * w[ok]).sum(1) / den[ok], -1, 1))
    d1 = np.linalg.norm(p - p.mean(0), axis=1)
    d1 = d1 / d1.mean()
    return np.concatenate([_hist(d2, D2_BINS, 3.0), _hist(ang, A3_BINS, np.pi), _hist(d1, D1_BINS, 3.0)]).astype("float32")


def shape_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean L1 distance of the three L1-normalised blocks: 0 (same) to 2 (disjoint). Similarity is 1 - d/2."""
    cuts = (0, D2_BINS, D2_BINS + A3_BINS, D2_BINS + A3_BINS + D1_BINS)
    return float(np.mean([np.abs(a[s:e] - b[s:e]).sum() for s, e in zip(cuts, cuts[1:])]))
