"""Which embedding model for which Vault job (specs/asset_library/asset_embed_models.md section 10), under the captain's D6: the bundled local models are the
DEFAULT and send nothing; an OpenRouter model is an opt-in upgrade through egress consent, ZDR + data_collection deny, and never a ``:free`` model for private
content. Every request here goes to a fake transport."""
import itertools
import json
import re
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from lampway_server.library import embed as E
from lampway_server.library import embed_models as M
from lampway_server.library.store import AssetLibrary, LibraryError
from tests.test_library_embed import KEY

CATALOGUE = ["nvidia/llama-nemotron-embed-vl-1b-v2:free", "nvidia/nemotron-3-embed-1b:free", "voyageai/voyage-multimodal-3.5", "google/gemini-embedding-2",
             "baai/bge-m3", "qwen/qwen3-embedding-8b", "openai/text-embedding-3-small"]


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def transport(log, models=CATALOGUE, zdr=("voyageai/voyage-multimodal-3.5", "baai/bge-m3"), remaining=None, dim=3):
    def handler(req: httpx.Request):
        log.append(req)
        p = req.url.path
        if p.endswith("/embeddings/models"):
            return httpx.Response(200, json={"data": [{"id": m, "pricing": {"prompt": "0.00000001"}} for m in models]})
        if p.endswith("/endpoints/zdr"):
            return httpx.Response(200, json={"data": [{"model_id": m} for m in zdr]})
        if p.endswith("/key"):
            return httpx.Response(200, json={"data": {"free_model_daily_requests": {"used": 45, "limit": 50, "remaining": remaining}}})
        if p.endswith("/embeddings"):
            body = json.loads(req.content)
            return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0] * dim} for i, _ in enumerate(body["input"])], "usage": {"prompt_tokens": 5}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def reg(tmp_path, log, clock=None, **kw):
    lib = make_lib(tmp_path)
    return lib, M.Registry(lib, E.OpenRouterEmbed(KEY, transport=transport(log, **kw)), clock=clock or Clock())


# 1 -------------------------------------------------------------------------------------------------------------------------------
def test_catalogue_cache_refetches_after_24h_and_prices_are_never_hardcoded(tmp_path):
    log, clock = [], Clock()
    lib, r = reg(tmp_path, log, clock=clock)
    first = r.list()
    assert [m["id"] for m in first["models"]] == CATALOGUE and first["fetched_at"] == clock.t
    n = len(log)
    r.list()
    assert len(log) == n                                                        # cached
    clock.t += 24 * 3600 + 1
    r.list()
    assert len(log) > n                                                         # a day old: refetched
    src = Path(M.__file__).read_text()
    assert not re.search(r"\b\d+(\.\d+)?e-\d+\b|\b0\.0000\d+", src), "a price literal in the registry"


# 2 -------------------------------------------------------------------------------------------------------------------------------
def test_the_default_is_the_bundled_local_model_and_sends_nothing(tmp_path):
    log = []
    lib, r = reg(tmp_path, log)
    for sens in ("public", "private"):
        rec = r.recommend("text_to_image", sens)
        assert rec["picks"]["default"] == {"model": "local:clip-vit-b-32", "space": "image_local:clip-vit-b-32", "uploads": False, "free": True}
        assert rec["picks"]["deterministic_baseline"] == "image_dhash+image_hist"
    assert r.recommend("text_doc", "private")["picks"]["default"]["model"] == "local:bge-small-en-v1.5"


def test_recommend_private_never_returns_a_free_model(tmp_path):
    lib, r = reg(tmp_path, [], zdr=("nvidia/llama-nemotron-embed-vl-1b-v2:free", "nvidia/nemotron-3-embed-1b:free", "voyageai/voyage-multimodal-3.5", "baai/bge-m3"))   # even ZDR-listed
    for job in M.JOBS:
        up = r.recommend(job, "private")["picks"]["upgrade"]
        assert up is None or (not up["model"].endswith(":free") and up["zdr"] is True and up["routing"] == {"zdr": True, "data_collection": "deny"}), (job, up)
    assert r.recommend("text_to_image", "private")["picks"]["upgrade"]["model"] == "voyageai/voyage-multimodal-3.5"


def test_recommend_public_prefers_free_joint_model_for_text_to_image(tmp_path):
    lib, r = reg(tmp_path, [])
    up = r.recommend("text_to_image", "public")["picks"]["upgrade"]
    assert up["model"] == "nvidia/llama-nemotron-embed-vl-1b-v2:free" and up["free"] is True and up["uploads"] is True and up["opt_in"] == "egress_consent:openrouter"


def test_a_private_job_with_no_zdr_model_listed_stays_local(tmp_path):
    lib, r = reg(tmp_path, [], zdr=())
    rec = r.recommend("text_to_image", "private")
    assert rec["picks"]["upgrade"] is None and any("no ZDR" in c for c in rec["caveats"])


# 3 -------------------------------------------------------------------------------------------------------------------------------
def test_free_run_is_sized_to_remaining_daily_requests(tmp_path):
    log = []
    lib = make_lib(tmp_path)
    for i in range(7 * E.BATCH):
        lib.put({"kind": "prompt", "name": f"p{i}", "source": {"kind": "t", "key": str(i)}, "license": "CC0-1.0", "files": [{"role": "main", "bytes": f"p{i}".encode(), "storage": "cas"}]})
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=transport(log, remaining=5)))
    plan = svc.plan("text_api", model="nvidia/nemotron-3-embed-1b:free")
    out = svc.run(plan["plan_id"], by="captain")
    assert sum(1 for q in log if q.url.path.endswith("/embeddings")) == 5
    assert out["partial"] is True and out["done"] == 5 * E.BATCH and "next UTC day" in out["note"]


# 4 -------------------------------------------------------------------------------------------------------------------------------
def test_dimension_mismatch_is_not_stored(tmp_path):
    log = []
    lib = make_lib(tmp_path)
    for i in range(2):
        lib.put({"kind": "prompt", "name": f"p{i}", "source": {"kind": "t", "key": str(i)}, "license": "CC0-1.0", "files": [{"role": "main", "bytes": f"q{i}".encode(), "storage": "cas"}]})
    vid = lib.version_of("id00001")
    lib.put_embedding(vid, "text_api:baai/bge-m3", [1.0, 0.0, 0.0, 0.0])           # the space already holds 4-d vectors
    svc = E.Embed(lib, openrouter=E.OpenRouterEmbed(KEY, transport=transport(log, dim=3)))
    out = svc.run(svc.plan("text_api", model="baai/bge-m3", missing_only=False)["plan_id"], by="captain")
    assert out["done"] == 0 and len(out["failed"]) == 2
    assert all("different dimension than the space expects (3 vs 4): not stored" in f["why"] for f in out["failed"])
    assert lib.embedding_spaces()["text_api:baai/bge-m3"] == 1


# 5 -------------------------------------------------------------------------------------------------------------------------------
def test_agent_cannot_set_default(tmp_path):
    lib, r = reg(tmp_path, [])
    with pytest.raises(LibraryError, match="the default model is the captain's choice \\(it decides what is uploaded and spent\\)"):
        r.set_default("text_doc", "public", "baai/bge-m3", by="agent")
    r.set_default("text_doc", "public", "baai/bge-m3", by="captain")
    assert r.recommend("text_doc", "public")["picks"]["default"]["model"] == "baai/bge-m3"
    assert tuple(lib._reader().execute("select decider,answer from decision where question='embed_default:text_doc:public'").fetchone()) == ("captain", "baai/bge-m3")
    with pytest.raises(LibraryError, match="free models may retain"):
        r.set_default("text_doc", "private", "nvidia/nemotron-3-embed-1b:free", by="captain")


def test_probe_is_capped_and_an_agents_probe_is_a_dry_run(tmp_path):
    log = []
    lib, r = reg(tmp_path, log)
    with pytest.raises(LibraryError, match="probe is for measuring: max 64"):
        r.probe("baai/bge-m3", n_probe=65, by="captain")
    sent = lambda: sum(1 for q in log if q.url.path.endswith("/embeddings"))          # noqa: E731  (content requests; the catalogue read is metadata)
    dry = r.probe("baai/bge-m3", n_probe=4, by="agent")
    assert dry["dry_run"] is True and sent() == 0
    live = r.probe("baai/bge-m3", n_probe=4, by="captain", texts=["a", "b", "c", "d"])
    assert sent() == 1 and live["request_shape_ok"] is True and live["dim"] == 3 and live["usage_tokens"] == 5 and live["latency_ms"] >= 0
    with pytest.raises(LibraryError, match="model not listed by OpenRouter today: nope/model: run list"):
        r.probe("nope/model", n_probe=1, by="captain")                          # (the same words as embed.py's check, with the model named)


def test_bakeoff_scores_recall_at_5_and_mrr_per_searcher():
    probes = [{"text": "red", "expect": "a"}, {"text": "blue", "expect": "b"}, {"text": "green", "expect": "c"}]
    perfect = lambda t, k: {"red": ["a", "x"], "blue": ["b"], "green": ["c"]}[t]          # noqa: E731
    second = lambda t, k: {"red": ["x", "a"], "blue": ["y", "b"], "green": ["z", "q", "w", "v", "u", "c"]}[t]   # noqa: E731
    table = M.bakeoff(probes, {"perfect": perfect, "second": second})
    assert table["perfect"]["recall_at_5"] == 1.0 and table["perfect"]["mrr"] == 1.0
    assert table["second"]["recall_at_5"] == pytest.approx(2 / 3) and table["second"]["mrr"] == pytest.approx((0.5 + 0.5 + 0) / 3)


def test_the_tool_surface_and_its_refusals(tmp_path):
    lib, r = reg(tmp_path, [])
    assert r.handle({"action": "recommend", "job": "image_look", "sensitivity": "private"})["ok"] is True
    bad = r.handle({"action": "recommend", "job": "telepathy"})
    assert bad["ok"] is False and bad["help"]
    assert r.handle({"action": "set_default", "job": "text_doc", "sensitivity": "public", "model": "baai/bge-m3"}, by="agent")["ok"] is False


def test_a_free_model_slipped_into_a_private_candidate_list_is_still_refused(tmp_path, monkeypatch):
    """The candidate lists hold no free model for private content today; the router refuses one anyway, so an edit to the list cannot leak private content."""
    monkeypatch.setitem(M.CANDIDATES["text_to_image"], "private", ["nvidia/llama-nemotron-embed-vl-1b-v2:free", "voyageai/voyage-multimodal-3.5"])
    lib, r = reg(tmp_path, [], zdr=("nvidia/llama-nemotron-embed-vl-1b-v2:free", "voyageai/voyage-multimodal-3.5"))
    assert r.recommend("text_to_image", "private")["picks"]["upgrade"]["model"] == "voyageai/voyage-multimodal-3.5"
