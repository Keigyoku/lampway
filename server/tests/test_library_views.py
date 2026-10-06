"""The Vault's inspection views, server side (specs/asset_library/asset_ui_views.md sections 6 and 10): the lineage layout (deterministic, layered, no overlap, depth and node
limits), its PNG and the hit test that maps a click back to an asset, the image difference with SSIM, and the per-asset list of derived view products the editor presents."""
import itertools
import json

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import views as V
from lampway_server.library.store import AssetLibrary


@pytest.fixture
def lib(tmp_path):
    ids, clock = itertools.count(99999, -1), itertools.count(1000)          # ids DEScend while time ascends: an order by id is not an order by creation
    lb = AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))
    yield lb
    lb.close()


def put(lib, name, kind="mesh", files=()):
    return lib.put({"kind": kind, "name": name, "source": {"kind": "t", "key": name}, "files": list(files)})["id"]


def boots_chain(lib):
    """Plates -> Tripo mesh -> Smart UV clone -> patched mesh, plus a sibling variant (the Boots1 lineage shape)."""
    plate_f, plate_b = put(lib, "plate front", "image"), put(lib, "plate back", "image")
    mesh = put(lib, "boots1 tripo")
    uv = put(lib, "boots1 smart uv")
    patched = put(lib, "boots1 patched")
    variant = put(lib, "boots1 seed 2")
    for p in (plate_f, plate_b):
        lib.relate(mesh, "generated_from", p, by="rule")
    lib.relate(uv, "derived_from", mesh, by="rule")
    lib.relate(patched, "derived_from", uv, by="rule")
    lib.relate(variant, "variant_of", mesh, by="rule")
    return {"plate_f": plate_f, "plate_b": plate_b, "mesh": mesh, "uv": uv, "patched": patched, "variant": variant}


def test_lineage_layout_is_deterministic_and_acyclic(lib):
    ids = boots_chain(lib)
    extra = [put(lib, f"plate view {i}", "image") for i in range(5)]           # a wide layer: an order left to chance shows here
    for p in extra:
        lib.relate(ids["mesh"], "generated_from", p, by="rule")
    ids.update({f"extra{i}": p for i, p in enumerate(extra)})
    a = V.lineage_layout(lib, ids["patched"], depth=6)
    b = V.lineage_layout(lib, ids["patched"], depth=6)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    nodes = {n["id"]: n for n in a["nodes"]}
    assert set(nodes) == set(ids.values())
    layer = {i: n["layer"] for i, n in nodes.items()}
    assert layer[ids["plate_f"]] < layer[ids["mesh"]] < layer[ids["uv"]] < layer[ids["patched"]], "parents sit in earlier layers"
    plates = [ids["plate_f"], ids["plate_b"], *extra]
    assert [nodes[p]["y"] for p in plates] == sorted(nodes[p]["y"] for p in plates), "inside a layer the older asset comes first (created_at, then id): the order is not the set's"
    rects = [(n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]) for n in a["nodes"]]
    for r1, r2 in itertools.combinations(rects, 2):
        assert r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1], "no two nodes overlap"
    assert {(e["src"], e["dst"], e["type"]) for e in a["edges"]} >= {(ids["uv"], ids["mesh"], "derived_from"), (ids["mesh"], ids["plate_f"], "generated_from")}
    assert all(e["colour"] for e in a["edges"])


def test_the_depth_and_node_limits_collapse_what_is_beyond(lib):
    ids = boots_chain(lib)
    near = V.lineage_layout(lib, ids["patched"], depth=1)
    assert {n["id"] for n in near["nodes"]} == {ids["patched"], ids["uv"]} and near["collapsed"] >= 1
    few = V.lineage_layout(lib, ids["patched"], depth=6, max_nodes=3)
    assert len(few["nodes"]) == 3 and few["collapsed"] == 3


def test_lineage_png_hit_test_matches_node_rects(lib, tmp_path):
    ids = boots_chain(lib)
    lay = V.lineage_layout(lib, ids["patched"], depth=6)
    png = tmp_path / "lineage.png"
    V.render_lineage(lay, png)
    im = Image.open(png)
    assert im.size == (lay["width"], lay["height"])
    for n in lay["nodes"]:
        cx, cy = n["x"] + n["w"] // 2, n["y"] + n["h"] // 2
        assert V.hit_test(lay, cx, cy) == n["id"]
        assert im.getpixel((n["x"] + 2, n["y"] + 2)) != im.getpixel((0, 0)), "a node is drawn where its rect says"
    assert V.hit_test(lay, -5, -5) is None


def textured(w=96, h=96, seed=3):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (h // 4, w // 4, 3), dtype=np.uint8)
    return np.kron(base, np.ones((4, 4, 1), dtype=np.uint8))


def test_image_diff_of_identical_images_is_zero_and_of_a_shifted_image_is_not(tmp_path):
    a = textured()
    pa, pb, pc = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    Image.fromarray(a).save(pa)
    Image.fromarray(a).save(pb)
    Image.fromarray(np.roll(a, 1, axis=1)).save(pc)
    same = V.image_diff(pa, pb, tmp_path / "d1.png")
    assert same["ssim"] == pytest.approx(1.0) and same["mean_abs"] == 0
    shifted = V.image_diff(pa, pc, tmp_path / "d2.png")
    assert shifted["ssim"] < 0.99 and shifted["mean_abs"] > 0
    assert Image.open(tmp_path / "d2.png").size == (96, 96)


def test_the_view_products_of_an_asset_by_role(lib, tmp_path):
    frames = []
    for i in range(3):
        p = tmp_path / f"turn_{i:03d}.jpg"
        Image.new("RGB", (8, 8), (i * 40, 0, 0)).save(p)
        frames.append({"role": f"turntable:{i}", "ord": i, "path": str(p)})
    ball = tmp_path / "ball_256.jpg"
    Image.new("RGB", (8, 8), (9, 9, 9)).save(ball)
    aid = put(lib, "greaves", files=[*frames, {"role": "ball", "path": str(ball)}])
    out = V.view_products(lib, aid)
    assert out["turntable"] == [f["path"] for f in frames] and out["ball"] == str(ball)
    assert out["overlay"] is None and out["sheet"] is None and out["proxy"] == []
