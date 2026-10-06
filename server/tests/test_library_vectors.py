"""Asset Vault vectors and the deterministic embedding spaces (asset_embed.md section 10, asset_similar.md section 10)."""
import hashlib
import itertools
import json
import math
import struct

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import spaces as SP
from lampway_server.library import vectors as V
from lampway_server.library.store import AssetLibrary, LibraryError


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def glb_from_mesh(verts, tris):
    verts = np.asarray(verts, "<f4")
    idx = np.asarray(tris, "<u4").reshape(-1)
    bin_ = verts.tobytes() + idx.tobytes()
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(verts), "type": "VEC3", "min": verts.min(0).tolist(), "max": verts.max(0).tolist()},
                         {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": verts.nbytes}, {"buffer": 0, "byteOffset": verts.nbytes, "byteLength": idx.nbytes}], "buffers": [{"byteLength": len(bin_)}]}
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def box(sx=1.0, sy=1.0, sz=1.0):
    v = [(x * sx, y * sy, z * sz) for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)]
    t = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    return v, t


def torus(R=1.0, r=0.35, n=24, m=12):
    v, t = [], []
    for i in range(n):
        for j in range(m):
            a, b = 2 * math.pi * i / n, 2 * math.pi * j / m
            v.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(n):
        for j in range(m):
            a, b, c, d = i * m + j, ((i + 1) % n) * m + j, ((i + 1) % n) * m + (j + 1) % m, i * m + (j + 1) % m
            t += [(a, b, c), (a, c, d)]
    return v, t


def sphere(n=16, m=24):
    v = [(0, 0, 1)]
    for i in range(1, n):
        p = math.pi * i / n
        v += [(math.sin(p) * math.cos(2 * math.pi * j / m), math.sin(p) * math.sin(2 * math.pi * j / m), math.cos(p)) for j in range(m)]
    v.append((0, 0, -1))
    t = [(0, 1 + j, 1 + (j + 1) % m) for j in range(m)]
    for i in range(n - 2):
        for j in range(m):
            a, b, c, d = 1 + i * m + j, 1 + i * m + (j + 1) % m, 1 + (i + 1) * m + (j + 1) % m, 1 + (i + 1) * m + j
            t += [(a, d, c), (a, c, b)]
    last = len(v) - 1
    t += [(last, 1 + (n - 2) * m + (j + 1) % m, 1 + (n - 2) * m + j) for j in range(m)]
    return v, t


def transform(mesh, scale=1.0, rot_deg=0.0):
    v, t = mesh
    a = math.radians(rot_deg)
    R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    return (np.asarray(v) @ R.T * scale).tolist(), t


# ---- vectors -------------------------------------------------------------------------------------------------------------------
def test_vectors_are_l2_normalised_float32_and_bit_identical_across_runs():
    a, b = V.pack([3.0, 4.0, 0.0]), V.pack([3.0, 4.0, 0.0])
    assert a == b and len(a) == 12 and np.allclose(np.frombuffer(a, "<f4"), [0.6, 0.8, 0.0])
    assert np.frombuffer(V.pack([0, 0, 0]), "<f4").tolist() == [0, 0, 0]          # a zero vector stays zero, never NaN


def test_numpy_topk_equals_sorted_bruteforce_with_id_tiebreak():
    rnd = np.random.default_rng(3)
    mat = rnd.normal(size=(2000, 16)).astype("float32")
    mat[5] = mat[4]                                          # a planted exact tie
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    ids = [f"i{n:05d}" for n in range(2000)]
    ids[4], ids[5] = ids[5], ids[4]                          # the tied rows sit in the opposite order to their ids
    idx = V.NumpyBrute(ids, mat)
    q = mat[4]
    for k in (1, 10, 50):
        got = idx.topk(q, k)
        sims = mat @ q
        want = sorted(zip(ids, sims), key=lambda t: (-round(float(t[1]), 6), t[0]))[:k]
        assert [g[0] for g in got] == [w[0] for w in want]
    assert [g[0] for g in idx.topk(q, 2)] == ["i00004", "i00005"]       # tie broken by id, not by row order


def test_a_model_change_is_a_new_space_and_spaces_never_mix(tmp_path):
    lib = make_lib(tmp_path)
    a = lib.put({"kind": "prompt", "name": "x", "source": {"kind": "t", "key": "1"}, "files": [{"role": "main", "bytes": b"x", "storage": "cas"}]})
    vid = lib.version_of(a["id"])
    lib.put_embedding(vid, "text_api:modelA", [1, 0, 0], model="modelA")
    lib.put_embedding(vid, "text_api:modelB", [0, 1, 0, 0], model="modelB")
    assert lib.embedding_spaces() == {"text_api:modelA": 1, "text_api:modelB": 1}
    ids, mat = lib.load_space("text_api:modelA")
    assert mat.shape == (1, 3) and ids == [a["id"]]
    with pytest.raises(LibraryError, match="expects 3"):
        lib.put_embedding(vid, "text_api:modelA", [1, 0, 0, 0, 0], model="modelA")


# ---- deterministic spaces ---------------------------------------------------------------------------------------------------------
def test_image_hist_and_dhash_are_deterministic_and_normalised(tmp_path):
    p = tmp_path / "a.png"
    rnd = np.random.default_rng(1)
    Image.fromarray(rnd.integers(0, 255, (40, 50, 3), dtype="uint8")).save(p)
    h1, h2 = SP.image_hist(p), SP.image_hist(p)
    assert h1.shape == (64,) and np.array_equal(h1, h2) and abs(np.linalg.norm(h1) - 1) < 1e-6
    d = SP.image_dhash(p)
    assert d.shape == (64,) and set(np.unique(d)) <= {0.0, 1.0}
    assert SP.hamming(SP.image_dhash(p), d) == 0


def test_a_resized_copy_is_a_near_duplicate_by_dhash(tmp_path):
    rnd = np.random.default_rng(2)
    base = Image.fromarray(rnd.integers(0, 255, (64, 64, 3), dtype="uint8")).resize((256, 256))
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    base.save(a)
    base.resize((100, 100)).save(b)
    Image.fromarray(rnd.integers(0, 255, (256, 256, 3), dtype="uint8")).save(c)
    assert SP.hamming(SP.image_dhash(a), SP.image_dhash(b)) <= 4 < SP.hamming(SP.image_dhash(a), SP.image_dhash(c))


def test_glb_triangles_reads_the_bin_chunk():
    v, t = box(2, 1, 1)
    tris = SP.glb_triangles(glb_from_mesh(v, t))
    assert tris.shape == (12, 3, 3) and np.isclose(abs(tris[:, :, 0]).max(), 1.0)


def test_d2_is_scale_invariant_rotation_invariant_and_tells_shapes_apart():
    key = hashlib.sha256(b"fixed").hexdigest()
    cube, torus_, sph = box(), torus(), sphere()
    d = lambda m1, m2: SP.shape_distance(SP.shape_d2(SP.glb_triangles(glb_from_mesh(*m1)), key), SP.shape_d2(SP.glb_triangles(glb_from_mesh(*m2)), key))
    assert d(torus_, transform(torus_, 3.0)) < 0.02
    assert d(torus_, transform(torus_, 1.0, 37.0)) < 0.05
    assert d(box(), box(2, 1, 1)) > 0.02 and d(box(), box(1, 1, 1)) == 0
    assert d(cube, torus_) > 0.25
    assert d(sph, box(2, 1, 1)) > 0.1


def test_the_descriptor_is_reproducible_from_the_content_key():
    tris = SP.glb_triangles(glb_from_mesh(*torus()))
    a, b = SP.shape_d2(tris, "ab" * 32), SP.shape_d2(tris, "ab" * 32)
    c = SP.shape_d2(tris, "cd" * 32)
    assert np.array_equal(a, b) and not np.array_equal(a, c) and a.shape == (128,)


def test_dhash_space_matches_the_ingest_hex_hash(tmp_path):
    from lampway_server.library import ingest as I
    p = tmp_path / "a.png"
    rnd = np.random.default_rng(9)
    Image.fromarray(rnd.integers(0, 255, (40, 50, 3), dtype="uint8")).save(p)
    bits = "".join(str(int(x)) for x in SP.image_dhash(p))
    assert f"{int(bits, 2):016x}" == I.extract_image(p)["stats"]["dhash"]


def test_a_different_seed_barely_moves_the_descriptor():
    tris = SP.glb_triangles(glb_from_mesh(*torus()))
    assert SP.shape_distance(SP.shape_d2(tris, "ab" * 32), SP.shape_d2(tris, "cd" * 32)) < 0.06


def test_a_flat_image_has_an_all_zero_dhash(tmp_path):
    p = tmp_path / "flat.png"
    Image.new("RGB", (30, 30), (90, 90, 90)).save(p)
    assert SP.image_dhash(p).sum() == 0


def test_surface_points_are_area_weighted_not_per_triangle():
    big = [((-1, -1, 0), (1, -1, 0), (1, 1, 0)), ((-1, -1, 0), (1, 1, 0), (-1, 1, 0))]
    speck = [((10 + 0.001 * i, 10, 10), (10.001 + 0.001 * i, 10, 10), (10 + 0.001 * i, 10.001, 10)) for i in range(200)]
    key = "ab" * 32
    plain = SP.shape_d2(np.array(big, "float32"), key)
    with_speck = SP.shape_d2(np.array(big + speck, "float32"), key)
    assert SP.shape_distance(plain, with_speck) < 0.1        # 200 specks hold ~1e-5 of the area: they must barely count
