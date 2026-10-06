"""lampway_asset_search (agent tool, specs/mixar_docs/asset_search.md): search the enrolled library by text and/or a reference image and DECIDE: place (a confident single match), ask (several plausible ones: a
thumbnail picker) or none. Nothing lands in the scene. The embedding model is a slot behind the same result shape."""
import asyncio
import io
import json

import pytest
from PIL import Image

from lampway_server.agent import asset_tools as AT
from lampway_server.assetsearch import AssetIndex

ASSETS = [
    {"name": "BronzeHelmet", "library": "Armor", "blend_file": "helmets/greek.blend", "type": "OBJECT", "image_name": "img_helmet"},
    {"name": "BronzeHelmetCrested", "library": "Armor", "blend_file": "helmets/crest.blend", "type": "OBJECT", "image_name": "img_crest"},
    {"name": "oak_table_large", "library": "Furniture", "blend_file": "tables.blend", "type": "OBJECT", "image_name": "img_table"},
    {"name": "RedDragonStatue", "library": "Props", "blend_file": "statues/dragon.blend", "type": "COLLECTION", "image_name": "img_dragon"},
]
COLORS = {"img_helmet": (200, 130, 40), "img_crest": (205, 128, 42), "img_table": (110, 70, 30), "img_dragon": (200, 20, 20)}


def jpeg(rgb):
    b = io.BytesIO()
    Image.new("RGB", (32, 32), rgb).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def index(tmp_path):
    ix = AssetIndex(tmp_path / "state")
    ix.train("full", ASSETS, [], {k: jpeg(v) for k, v in COLORS.items()})
    return ix


def call(index, tmp_path, **args):
    out, err = asyncio.run(AT.call(index, tmp_path, "lampway_asset_search", args))
    return (json.loads(out) if not err else out), err


def test_a_confident_single_match_is_place_and_an_ambiguous_one_is_ask(index, tmp_path):
    res, err = call(index, tmp_path, query="dragon statue")
    assert not err and res["decision"] == "place" and res["results"][0]["name"] == "RedDragonStatue" and res["results"][0]["identity"] == "RedDragonStatue|Props|statues/dragon.blend"
    res, err = call(index, tmp_path, query="bronze helmet", threshold=0.3)
    assert not err and res["decision"] == "ask" and {r["name"] for r in res["results"][:2]} == {"BronzeHelmet", "BronzeHelmetCrested"}
    assert set(res["results"][0]) >= {"identity", "name", "library", "score", "thumbnail_path", "kind"}


def test_the_threshold_changes_the_decision_and_no_match_is_none(index, tmp_path):
    lo, _ = call(index, tmp_path, query="dragon statue", threshold=0.1)
    hi, _ = call(index, tmp_path, query="dragon statue", threshold=0.99)
    miss, _ = call(index, tmp_path, query="spaceship cockpit", only_library=True)
    assert lo["decision"] == "place" and hi["decision"] == "ask" and miss["decision"] == "none" and miss["results"] == []
    assert "no generation" in miss["note"] or "never" in miss["note"]


def test_libraries_filter_top_k_and_refusals(index, tmp_path):
    res, _ = call(index, tmp_path, query="bronze helmet", libraries=["Furniture"])
    assert res["results"] == [] and res["decision"] == "none"
    one, _ = call(index, tmp_path, query="helmet", top_k=1)
    assert len(one["results"]) == 1
    out, err = call(index, tmp_path)
    assert err and "give a text query or a reference image" in out
    out, err = call(index, tmp_path, query="x", top_k=99)
    assert err and "top_k is 1..50" in out


def test_a_reference_image_inside_the_project_matches_by_colour_and_one_outside_is_refused(index, tmp_path):
    (tmp_path / "ref.jpg").write_bytes(jpeg((198, 22, 22)))
    res, err = call(index, tmp_path, image="ref.jpg")
    assert not err and res["results"][0]["name"] == "RedDragonStatue"
    out, err = call(index, tmp_path, image="/etc/hostname")
    assert err and "outside the project root" in out


def test_an_untrained_index_says_so(tmp_path):
    out, err = call(AssetIndex(tmp_path / "empty"), tmp_path, query="chair")
    assert err and "no trained model: train the asset library first" in out


def test_the_embedding_slot_swaps_without_changing_the_result_shape(tmp_path):
    def embed(data):                                   # a stand-in embedding: mean colour as a 3-vector
        im = Image.open(io.BytesIO(data)).convert("RGB").resize((4, 4))
        px = list(im.getdata())
        return [sum(p[i] for p in px) / (16 * 255) for i in range(3)]
    ix = AssetIndex(tmp_path / "s2", embedder=embed)
    ix.train("full", ASSETS, [], {k: jpeg(v) for k, v in COLORS.items()})
    (tmp_path / "ref.jpg").write_bytes(jpeg((198, 22, 22)))
    res, err = call(ix, tmp_path, image="ref.jpg")
    assert not err and res["results"][0]["name"] == "RedDragonStatue" and set(res["results"][0]) >= {"identity", "name", "library", "score", "thumbnail_path", "kind"}
