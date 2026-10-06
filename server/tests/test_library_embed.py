"""Asset Vault embedding service (asset_embed.md section 10): deterministic spaces need no click and no network; an uploading space is planned, never sent, until the user confirms."""
import itertools
import json

import httpx
import numpy as np
import pytest
from PIL import Image

from lampway_server.library import embed as E
from lampway_server.library.store import AssetLibrary, LibraryError
from tests.test_library_vectors import box, glb_from_mesh, torus

KEY = "sk-or-v1-" + "ef56" * 16


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def add_image(lib, tmp_path, name, color, license=None, key=None):
    p = tmp_path / f"{name}.png"
    rnd = np.random.default_rng(abs(hash(name)) % 1000)
    arr = np.clip(rnd.normal(color, 40, (32, 32, 3)), 0, 255).astype("uint8")
    Image.fromarray(arr).save(p)
    return lib.put({"kind": "image", "name": name, "source": {"kind": "t", "key": key or name}, "license": license, "description": f"a {name} plate",
                    "files": [{"role": "main", "path": str(p), "storage": "external"}]})["id"]


def add_mesh(lib, tmp_path, name, mesh):
    p = tmp_path / f"{name}.glb"
    p.write_bytes(glb_from_mesh(*mesh))
    return lib.put({"kind": "mesh", "name": name, "source": {"kind": "t", "key": name}, "files": [{"role": "main", "path": str(p), "storage": "external"}]})["id"]


def or_transport(requests, models=("baai/bge-m3", "qwen/qwen3-embedding-8b", "x/free-emb:free"), zdr=("baai/bge-m3",), embed_status=200, timeout_on_embed=False):
    def handler(req: httpx.Request):
        requests.append(req)
        if req.url.path.endswith("/embeddings/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        if req.url.path.endswith("/endpoints/zdr"):
            return httpx.Response(200, json={"data": [{"model_id": m} for m in zdr]})
        if req.url.path.endswith("/embeddings"):
            if timeout_on_embed:
                raise httpx.ReadTimeout("slow", request=req)
            body = json.loads(req.content)
            return httpx.Response(embed_status, json={"data": [{"index": i, "embedding": [float(i + 1), 1.0, 0.5]} for i, _ in enumerate(body["input"])], "usage": {"prompt_tokens": 7, "cost": 0.00001}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_deterministic_spaces_run_without_a_click_and_send_nothing(tmp_path, monkeypatch):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "gold", (200, 160, 40))
    add_mesh(lib, tmp_path, "tor", torus())
    sent = []
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: sent.append(1))
    svc = E.Embed(lib)
    for space in ("image_hist", "image_dhash", "shape_d2"):
        out = svc.run(svc.plan(space)["plan_id"], by="agent")
        assert out["done"] == 1 and out["failed"] == [] and out["bytes_uploaded"] == 0
    assert sent == [] and set(lib.embedding_spaces()) == {"image_hist", "image_dhash", "shape_d2"}


def test_a_space_only_embeds_the_kinds_it_understands(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "gold", (200, 160, 40))
    add_mesh(lib, tmp_path, "tor", torus())
    svc = E.Embed(lib)
    assert svc.plan("shape_d2")["planned"] == 1 and svc.plan("image_hist")["planned"] == 1


def test_missing_only_skips_what_is_embedded_and_a_changed_version_is_reembedded(tmp_path):
    lib = make_lib(tmp_path)
    a = add_image(lib, tmp_path, "gold", (200, 160, 40))
    svc = E.Embed(lib)
    svc.run(svc.plan("image_hist")["plan_id"], by="agent")
    assert svc.plan("image_hist")["planned"] == 0
    Image.new("RGB", (8, 8), (1, 2, 3)).save(tmp_path / "gold.png")
    lib.put({"kind": "image", "name": "gold", "source": {"kind": "t", "key": "gold"}, "files": [{"role": "main", "path": str(tmp_path / "gold.png"), "storage": "external"}]})
    assert svc.plan("image_hist")["planned"] == 1 and a


def test_plan_sends_no_content_it_only_reads_the_live_catalogue(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    reqs = []
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport(reqs)))
    p = svc.plan("text_api", model="baai/bge-m3")
    assert p["uploads"] is True and p["planned"] == 1 and p["estimate_usd"] >= 0 and p["bytes_uploaded"] == 0
    assert [r.method for r in reqs] == ["GET"] and {r.url.path.rsplit("/", 1)[-1] for r in reqs} == {"models"}       # the live list, no content


def test_an_agent_cannot_run_an_uploading_space(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    reqs = []
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport(reqs)))
    p = svc.plan("text_api", model="baai/bge-m3")
    with pytest.raises(LibraryError, match=r"uploads text to openrouter: ask the user to confirm in the Vault panel \(plan id " + p["plan_id"] + r"\)"):
        svc.run(p["plan_id"], by="agent")
    assert not [r for r in reqs if r.method == "POST"] and lib.embedding_spaces() == {}


def test_a_confirmed_run_sends_text_only_with_zdr_routing_for_private_content(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "secret", (10, 10, 10))                       # no licence: private
    reqs = []
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport(reqs)))
    out = svc.run(svc.plan("text_api", model="baai/bge-m3")["plan_id"], by="captain")
    assert out["done"] == 1
    post = [r for r in reqs if r.method == "POST"]
    body = json.loads(post[0].content)
    assert body["provider"] == {"zdr": True, "data_collection": "deny"} and body["model"] == "baai/bge-m3" and "secret" in body["input"][0]
    assert "text_api:baai/bge-m3" in lib.embedding_spaces() and KEY not in json.dumps(out)


def test_private_content_is_refused_on_a_free_model_and_on_a_non_zdr_model(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "secret", (10, 10, 10))
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport([])))
    with pytest.raises(LibraryError, match="free models may retain"):
        svc.plan("text_api", model="x/free-emb:free")
    with pytest.raises(LibraryError, match="no ZDR endpoint"):
        svc.plan("text_api", model="qwen/qwen3-embedding-8b")


def test_public_content_may_use_a_free_model_and_a_model_missing_from_the_live_list_is_refused(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport([])))
    assert svc.plan("text_api", model="x/free-emb:free")["planned"] == 1
    with pytest.raises(LibraryError, match="not listed by OpenRouter today"):
        svc.plan("text_api", model="nobody/nothing")


def test_a_model_change_is_a_new_space(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport([])))
    svc.run(svc.plan("text_api", model="baai/bge-m3")["plan_id"], by="captain")
    svc.run(svc.plan("text_api", model="qwen/qwen3-embedding-8b")["plan_id"], by="captain")
    assert set(lib.embedding_spaces()) == {"text_api:baai/bge-m3", "text_api:qwen/qwen3-embedding-8b"}


def test_a_provider_timeout_is_not_resubmitted(tmp_path):
    lib = make_lib(tmp_path)
    add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    reqs = []
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport(reqs, timeout_on_embed=True)))
    out = svc.run(svc.plan("text_api", model="baai/bge-m3")["plan_id"], by="captain")
    assert out["done"] == 0 and out["failed"][0]["why"].startswith("submission_unknown")
    assert len([r for r in reqs if r.method == "POST"]) == 1 and lib.embedding_spaces() == {}


def test_a_dimension_change_is_refused_not_stored(tmp_path):
    lib = make_lib(tmp_path)
    a = add_image(lib, tmp_path, "pub", (10, 10, 10), license="CC0-1.0")
    b = add_image(lib, tmp_path, "pub2", (20, 10, 10), license="CC0-1.0")
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=or_transport([])))
    svc.run(svc.plan("text_api", model="baai/bge-m3")["plan_id"], by="captain")
    lib.put_embedding(lib.version_of(a), "text_api:baai/bge-m3", [1, 0, 0], model="baai/bge-m3")
    with pytest.raises(LibraryError, match="expects 3"):
        lib.put_embedding(lib.version_of(b), "text_api:baai/bge-m3", [1, 0, 0, 0], model="baai/bge-m3")


def test_an_unknown_space_is_refused(tmp_path):
    with pytest.raises(LibraryError, match="unknown space"):
        E.Embed(make_lib(tmp_path)).plan("nope")


def test_a_plan_id_must_exist(tmp_path):
    with pytest.raises(LibraryError, match="no plan"):
        E.Embed(make_lib(tmp_path)).run("plan-zzz", by="captain")
