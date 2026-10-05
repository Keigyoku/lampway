"""Semantic asset search (docs "Connect and search your assets", "Reuse assets with the Agent"): the seven endpoints the client's
asset-search module calls, on proven code first. Text: BM25 over the asset's name, library, type and file name (camel case and
separators split). Image: an RGB colour histogram of the preview, compared by histogram intersection. The hybrid score is a
weighted sum. An embedding model is the SLOT (not wired): the index is where its vectors would live. Pairing, as the client
sends it: metadata rows carry ``image_name``; the preview file is ``<image_name>.jpg``; an asset's identity is
``name|library|blend_file``."""

import io
import json

import pytest
from PIL import Image

ASSETS = [
    {"name": "BronzeHelmet", "library": "Armor", "blend_file": "helmets/greek.blend", "type": "OBJECT", "image_name": "img_helmet"},
    {"name": "oak_table_large", "library": "Furniture", "blend_file": "tables.blend", "type": "OBJECT", "image_name": "img_table"},
    {"name": "RedDragonStatue", "library": "Props", "blend_file": "statues/dragon.blend", "type": "COLLECTION", "image_name": "img_dragon"},
]
COLORS = {"img_helmet": (200, 130, 40), "img_table": (110, 70, 30), "img_dragon": (200, 20, 20)}


def jpeg(rgb, size=(32, 32)):
    b = io.BytesIO()
    Image.new("RGB", size, rgb).save(b, "JPEG")
    return b.getvalue()


def ident(a):
    return f"{a['name']}|{a['library']}|{a['blend_file']}"


def train(fake, assets, mode="full", removed=(), checksum=None):
    files = [("images", (f"{a['image_name']}.jpg", jpeg(COLORS[a["image_name"]]), "image/jpeg")) for a in assets if a["image_name"] in COLORS]
    data = {"mode": mode, "removed_assets": json.dumps(list(removed)), "metadata": json.dumps(assets)}
    if checksum:
        data["metadata_checksum"] = checksum
    return fake.post("/api/v1/asset-search/train", data=data, files=files or None)


@pytest.fixture
def signed(fake):
    fake.login()
    return fake


def test_an_untrained_server_says_so_and_search_is_a_404_the_client_understands(signed):
    s = signed.get("/api/v1/asset-search/status").json()["data"]
    assert s == {"has_embeddings": False, "stored_asset_count": 0}
    r = signed.post("/api/v1/asset-search/search", data={"prompt": "helmet"})
    assert r.status_code == 404 and "trained" in r.json()["detail"]
    p = signed.post("/api/v1/asset-search/train/prepare", data={"metadata": json.dumps(ASSETS)}).json()["data"]
    assert p["action"] == "full_train" and p["asset_count"] == 3 and p["unchanged_count"] == 0 and p["metadata_checksum"]


def test_training_stores_the_assets_and_prepare_then_diffs_the_library_against_the_index(signed):
    r = train(signed, ASSETS)
    assert r.status_code == 200 and r.json()["data"]["images_embedded"] == 3
    assert signed.get("/api/v1/asset-search/status").json()["data"] == {"has_embeddings": True, "stored_asset_count": 3}
    same = signed.post("/api/v1/asset-search/train/prepare", data={"metadata": json.dumps(ASSETS)}).json()["data"]
    assert same["action"] == "skip" and same["new_assets"] == [] and same["unchanged_count"] == 3
    extra = {"name": "SilverShield", "library": "Armor", "blend_file": "shields.blend", "type": "OBJECT", "image_name": "img_shield"}
    diff = signed.post("/api/v1/asset-search/train/prepare", data={"metadata": json.dumps(ASSETS[:2] + [extra])}).json()["data"]
    assert diff["action"] == "incremental" and diff["new_assets"] == [ident(extra)] and diff["removed_assets"] == [ident(ASSETS[2])]
    assert diff["unchanged_count"] == 2
    st = signed.post("/api/v1/asset-search/status", data={"metadata": json.dumps(ASSETS[:2] + [extra])}).json()["data"]
    assert st["needs_retraining"] is True and "1 new" in st["message"] and "1 removed" in st["message"]
    ok = signed.post("/api/v1/asset-search/status", data={"metadata": json.dumps(ASSETS)}).json()["data"]
    assert ok["needs_retraining"] is False


def test_incremental_training_adds_and_removes_without_losing_the_rest(signed):
    train(signed, ASSETS[:2])
    extra = ASSETS[2]
    r = train(signed, [extra], mode="incremental", removed=[ident(ASSETS[0])])
    assert r.json()["data"] == {"images_embedded": 1, "removed": 1}
    assert signed.get("/api/v1/asset-search/status").json()["data"]["stored_asset_count"] == 2
    hits = signed.post("/api/v1/asset-search/search", data={"prompt": "helmet"}).json()["data"]["results"]
    assert all(h["metadata"]["name"] != "BronzeHelmet" for h in hits)
    full = train(signed, ASSETS[:1], mode="full")
    assert full.status_code == 200 and signed.get("/api/v1/asset-search/status").json()["data"]["stored_asset_count"] == 1, "a full train replaces"


def test_text_search_ranks_by_the_assets_own_words_and_returns_the_clients_shape(signed):
    train(signed, ASSETS)
    res = signed.post("/api/v1/asset-search/search", data={"prompt": "greek bronze helmet"}).json()["data"]["results"]
    assert res[0]["model_name"] == "BronzeHelmet" and res[0]["metadata"] == {"name": "BronzeHelmet", "library": "Armor", "blend_file": "helmets/greek.blend", "type": "OBJECT"}
    assert 0 < res[0]["similarity_score"] <= 1 and all(res[i]["similarity_score"] >= res[i + 1]["similarity_score"] for i in range(len(res) - 1))
    table = signed.post("/api/v1/asset-search/search", data={"prompt": "a large oak table"}).json()["data"]["results"]
    assert table[0]["metadata"]["name"] == "oak_table_large"
    dragon = signed.post("/api/v1/asset-search/search", data={"prompt": "dragon statue", "top_k": "1"}).json()["data"]["results"]
    assert len(dragon) == 1 and dragon[0]["metadata"]["name"] == "RedDragonStatue"
    assert signed.post("/api/v1/asset-search/search", data={"prompt": "zzzzqq"}).json()["data"]["results"] == []


def test_image_search_ranks_by_colour_and_the_hybrid_score_uses_both(signed):
    train(signed, ASSETS)
    red = ("image", ("search_query.jpg", jpeg((205, 25, 25)), "image/jpeg"))
    by_image = signed.post("/api/v1/asset-search/search", data={"prompt": ""}, files=[red]).json()["data"]["results"]
    assert by_image[0]["metadata"]["name"] == "RedDragonStatue"
    brown = ("image", ("search_query.jpg", jpeg((108, 68, 28)), "image/jpeg"))
    hybrid = signed.post("/api/v1/asset-search/search", data={"prompt": "helmet"}, files=[brown]).json()["data"]["results"]
    names = [h["metadata"]["name"] for h in hybrid]
    assert "BronzeHelmet" in names and "oak_table_large" in names
    text_only = signed.post("/api/v1/asset-search/search", data={"prompt": "helmet"}).json()["data"]["results"][0]["similarity_score"]
    assert hybrid[0]["similarity_score"] != text_only, "the image changed the scoring"


def test_batch_search_answers_one_ranked_list_per_prompt(signed):
    train(signed, ASSETS)
    r = signed.post("/api/v1/asset-search/search-batch", data={"prompts": json.dumps(["bronze helmet", "oak table", "red dragon"])})
    res = r.json()["data"]["results"]
    assert set(res) == {"bronze helmet", "oak table", "red dragon"}
    assert res["bronze helmet"][0]["model_name"] == "BronzeHelmet" and res["oak table"][0]["model_name"] == "oak_table_large"
    assert signed.post("/api/v1/asset-search/search-batch", data={"prompts": "not json"}).status_code == 422


def test_deleting_the_embeddings_empties_the_index_and_the_index_survives_a_restart(signed, settings, provider):
    train(signed, ASSETS)
    from starlette.testclient import TestClient
    from lampway_server.app import create_app
    from tests.fake_client import FakeMixarClient
    with TestClient(create_app(settings, provider=provider), base_url="http://127.0.0.1:8787") as http2:
        again = FakeMixarClient(http2, password=settings.user_password)
        again.login()
        assert again.get("/api/v1/asset-search/status").json()["data"]["stored_asset_count"] == 3, "read back from the state directory"
        assert again.delete("/api/v1/asset-search/embeddings").json()["data"] == {"deleted": True}
        assert again.get("/api/v1/asset-search/status").json()["data"] == {"has_embeddings": False, "stored_asset_count": 0}
        assert again.delete("/api/v1/asset-search/embeddings").json()["data"] == {"deleted": False}


def test_a_bearer_is_required_and_bad_input_is_refused_not_crashed(http, signed):
    for method, path in (("get", "/api/v1/asset-search/status"), ("post", "/api/v1/asset-search/search"), ("delete", "/api/v1/asset-search/embeddings")):
        assert getattr(http, method)(path).status_code == 401
    assert signed.post("/api/v1/asset-search/train/prepare", data={"metadata": "{}"}).status_code == 422
    assert signed.post("/api/v1/asset-search/train", data={"mode": "weird", "metadata": "[]"}).status_code == 422
    bad = signed.post("/api/v1/asset-search/train", data={"mode": "full", "metadata": json.dumps(ASSETS[:1])},
                      files=[("images", ("img_helmet.jpg", b"not an image", "image/jpeg"))])
    assert bad.status_code == 200 and bad.json()["data"]["images_embedded"] == 0, "a corrupt preview is skipped, the asset is still text-searchable"
