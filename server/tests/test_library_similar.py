"""Asset Vault similarity (asset_similar.md section 10): shape, look and name axes, deterministic."""
import itertools

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import embed as E
from lampway_server.library import similar as SM
from lampway_server.library.store import AssetLibrary, LibraryError
from tests.test_library_vectors import box, glb_from_mesh, sphere, torus, transform


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def mesh(lib, tmp_path, name, m, desc=""):
    p = tmp_path / f"{name}.glb"
    p.write_bytes(glb_from_mesh(*m))
    return lib.put({"kind": "mesh", "name": name, "description": desc, "source": {"kind": "t", "key": name}, "files": [{"role": "main", "path": str(p), "storage": "external"}]})["id"]


def image(lib, tmp_path, name, base):
    p = tmp_path / f"{name}.png"
    rnd = np.random.default_rng(sum(map(ord, name)))
    Image.fromarray(np.clip(rnd.normal(base, 25, (48, 48, 3)), 0, 255).astype("uint8")).save(p)
    return lib.put({"kind": "image", "name": name, "source": {"kind": "t", "key": name}, "files": [{"role": "main", "path": str(p), "storage": "external"}]})["id"]


@pytest.fixture
def shapes(tmp_path):
    lib = make_lib(tmp_path)
    ids = {"torus": mesh(lib, tmp_path, "torus_a", torus()), "torus3": mesh(lib, tmp_path, "torus_big", transform(torus(), 3.0)), "torus_rot": mesh(lib, tmp_path, "torus_rot", transform(torus(), 1.0, 37)),
           "cube": mesh(lib, tmp_path, "cube", box()), "slab": mesh(lib, tmp_path, "slab", box(3, 3, 0.2)), "ball": mesh(lib, tmp_path, "ball", sphere())}
    svc = E.Embed(lib)
    svc.run(svc.plan("shape_d2")["plan_id"], by="agent")
    return lib, ids


def test_shape_neighbours_of_a_torus_are_the_other_tori_first(shapes):
    lib, ids = shapes
    got = SM.similar(lib, {"asset_ids": [ids["torus"]]}, axes=["shape"], k=5)
    names = [it["name"] for it in got["items"]]
    assert set(names[:2]) == {"torus_big", "torus_rot"} and ids["torus"] not in [it["id"] for it in got["items"]]
    assert got["items"][0]["axes"]["shape"] > 0.95 and got["items"][-1]["axes"]["shape"] < got["items"][0]["axes"]["shape"]
    assert got["probe"]["kind"] == "mesh" and got["probe"]["coherence"] == 1.0


def test_exclude_self_false_returns_the_probe_first(shapes):
    lib, ids = shapes
    got = SM.similar(lib, {"asset_ids": [ids["cube"]]}, axes=["shape"], k=3, exclude_self=False)
    assert got["items"][0]["id"] == ids["cube"] and got["items"][0]["score"] == 1.0


def test_a_mixed_selection_has_a_lower_coherence_than_a_matched_one(shapes):
    lib, ids = shapes
    tight = SM.similar(lib, {"asset_ids": [ids["torus"], ids["torus3"]]}, axes=["shape"])["probe"]["coherence"]
    loose = SM.similar(lib, {"asset_ids": [ids["torus"], ids["cube"]]}, axes=["shape"])["probe"]["coherence"]
    assert tight > 0.97 and loose < tight - 0.05


def test_the_descriptor_is_computed_on_demand_for_a_probe_that_has_none(tmp_path):
    lib = make_lib(tmp_path)
    a, b = mesh(lib, tmp_path, "t1", torus()), mesh(lib, tmp_path, "t2", transform(torus(), 2.0))
    svc = E.Embed(lib)
    svc.ensure(b, "shape_d2")
    got = SM.similar(lib, {"asset_ids": [a]}, axes=["shape"])
    assert [it["id"] for it in got["items"]] == [b] and "shape_d2" in lib.embedding_spaces()


def test_look_finds_the_same_colour_family_and_name_uses_the_text_index(tmp_path):
    lib = make_lib(tmp_path)
    gold1, gold2 = image(lib, tmp_path, "gold_plate_a", (210, 170, 40)), image(lib, tmp_path, "gold_plate_b", (205, 165, 45))
    image(lib, tmp_path, "blue_plate", (30, 40, 200))
    svc = E.Embed(lib)
    for sp in ("image_hist", "image_dhash"):
        svc.run(svc.plan(sp)["plan_id"], by="agent")
    got = SM.similar(lib, {"asset_ids": [gold1]}, axes=["look"], k=2)
    assert got["items"][0]["id"] == gold2 and got["items"][0]["axes"]["look"] > got["items"][1]["axes"]["look"]
    by_name = SM.similar(lib, {"text": "blue plate"}, axes=["name"], k=1)
    assert by_name["items"][0]["name"] == "blue_plate" and by_name["probe"]["kind"] == "text"


def test_weights_renormalise_over_the_axes_that_exist_for_both(shapes):
    lib, ids = shapes
    only_shape = SM.similar(lib, {"asset_ids": [ids["torus"]]}, axes=["shape"], k=1)["items"][0]
    mixed = SM.similar(lib, {"asset_ids": [ids["torus"]]}, axes=["shape", "look", "name"], weights={"shape": 0.5, "look": 0.3, "name": 0.2}, k=1)["items"][0]
    assert mixed["id"] == only_shape["id"] and abs(mixed["score"] - mixed["axes"]["shape"]) < 0.25       # no look vectors exist: the look weight is not a penalty
    assert mixed["axes"]["look"] is None


def test_an_image_file_probe_is_not_ingested(tmp_path):
    lib = make_lib(tmp_path)
    a = image(lib, tmp_path, "gold_a", (210, 170, 40))
    svc = E.Embed(lib)
    svc.run(svc.plan("image_hist")["plan_id"], by="agent")
    probe = tmp_path / "probe.png"
    Image.new("RGB", (48, 48), (212, 168, 42)).save(probe)
    before = lib.status()["assets"]["total"]
    got = SM.similar(lib, {"image_path": str(probe)}, axes=["look"], k=1)
    assert got["items"][0]["id"] == a and lib.status()["assets"]["total"] == before and got["probe"]["kind"] == "image"


def test_refusals_and_the_best_three_when_nothing_clears_min_score(shapes):
    lib, ids = shapes
    with pytest.raises(LibraryError, match="selection is empty"):
        SM.similar(lib, {}, axes=["shape"])
    img = image(lib, lib.root.parent, "z", (1, 2, 3))
    with pytest.raises(LibraryError, match="shape applies to meshes only"):
        SM.similar(lib, {"asset_ids": [img]}, axes=["shape"])
    got = SM.similar(lib, {"asset_ids": [ids["cube"]]}, axes=["shape"], min_score=0.9999999, k=2)
    assert "lower min_score" in got["note"] and len(got["items"]) == 3


def test_the_look_axis_degrades_to_the_spaces_a_candidate_has(tmp_path):
    """Found by lane vault-ui: with only image_hist indexed, the look axis answered nothing (the probe's on-demand dhash made the intersection the probe alone).
    A candidate is scored on the look spaces it HAS; a missing space is never a veto."""
    lib = make_lib(tmp_path)
    red, red2, blue = image(lib, tmp_path, "red", (200, 30, 30)), image(lib, tmp_path, "red2", (190, 40, 35)), image(lib, tmp_path, "blue", (30, 40, 200))
    svc = E.Embed(lib)
    svc.run(svc.plan("image_hist")["plan_id"], by="agent")                      # dhash never indexed
    res = SM.similar(lib, {"asset_ids": [red]}, axes=["look"])
    got = [it["id"] for it in res["items"]]
    assert got[:2] == [red2, blue] and res["items"][0]["axes"]["look"] > res["items"][1]["axes"]["look"]
