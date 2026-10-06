"""Which embedding model for which Vault job (specs/asset_library/asset_embed_models.md), under the captain's D6: the open-weights models bundled with the client
are the DEFAULT for every job and send nothing. An OpenRouter model is an UPGRADE the user opts into (the ``openrouter`` egress route): for private content only a
model on OpenRouter's live ZDR list, sent with ``zdr: true, data_collection: deny``, and never a ``:free`` model; for public content a free model may be offered.

The catalogue is OpenRouter's, read live and cached for a day in ``<library>/embed_models.json``; prices are read from it, never written here. The candidate lists
below are an order of preference by fit to the job (from the contract's table), not a price list: a candidate not in today's catalogue is skipped. The bake-off
harness scores recall@5 and MRR for any set of searchers; a live bake-off is the captain's click (it uploads and may spend)."""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

from .embed import PRIVATE_ROUTING, OpenRouterEmbed
from .store import AssetLibrary, LibraryError

JOBS = ("text_doc", "text_query", "image_look", "text_to_image", "video_keyframes", "mesh_views", "prompt_template")
TTL_S = 24 * 3600
_CLIP = {"model": "local:clip-vit-b-32", "space": "image_local:clip-vit-b-32", "uploads": False, "free": True}
_BGE = {"model": "local:bge-small-en-v1.5", "space": "text_local:bge-small-en-v1.5", "uploads": False, "free": True}
LOCAL = {"text_doc": _BGE, "prompt_template": _BGE, "text_query": _CLIP, "text_to_image": _CLIP, "image_look": _CLIP,
         "video_keyframes": {"model": "deterministic:video_kf_hist", "space": "video_kf_hist", "uploads": False, "free": True},
         "mesh_views": {"model": "deterministic:shape_d2", "space": "shape_d2", "uploads": False, "free": True}}
BASELINE = {"text_doc": "fts5", "prompt_template": "fts5", "text_query": "fts5", "text_to_image": "image_dhash+image_hist", "image_look": "image_dhash+image_hist",
            "video_keyframes": "video_kf_hist", "mesh_views": "shape_d2"}
_VL_FREE, _VOYAGE, _GEMINI = "nvidia/llama-nemotron-embed-vl-1b-v2:free", "voyageai/voyage-multimodal-3.5", "google/gemini-embedding-2"
CANDIDATES = {
    "text_to_image": {"public": [_VL_FREE, _VOYAGE, _GEMINI], "private": [_VOYAGE, _GEMINI]},
    "text_query": {"public": [_VL_FREE, _VOYAGE, _GEMINI], "private": [_VOYAGE, _GEMINI]},
    "image_look": {"public": [_VL_FREE, _VOYAGE], "private": [_VOYAGE]},
    "video_keyframes": {"public": [_VL_FREE], "private": []},                   # native video embedding only after a probe proves video input works
    "text_doc": {"public": ["nvidia/nemotron-3-embed-1b:free", _VL_FREE], "private": ["baai/bge-m3", "qwen/qwen3-embedding-8b"]},
    "mesh_views": {"public": [_VL_FREE], "private": []},                        # private shapes stay deterministic
    "prompt_template": {"public": ["nvidia/nemotron-3-embed-1b:free"], "private": ["qwen/qwen3-embedding-8b", "baai/bge-m3"]},
}
CAPTAIN = ("captain", "user")
MAX_PROBE = 64


class Registry:
    def __init__(self, lib: AssetLibrary, openrouter: Optional[OpenRouterEmbed] = None, clock: Callable[[], float] = time.time):
        self.lib, self.or_, self.clock = lib, openrouter, clock
        self.cache = lib.root / "embed_models.json"
        self.defaults = lib.root / "embed_defaults.json"

    # -- catalogue ------------------------------------------------------------------------------------------------------------
    def list(self, refresh: bool = False) -> dict:
        if self.cache.exists() and not refresh:
            doc = json.loads(self.cache.read_text())
            if self.clock() - doc["fetched_at"] <= TTL_S:
                return doc
        if not self.or_:
            raise LibraryError("no OpenRouter key: set it in Models and settings (the bundled local models need none)")
        doc = {"fetched_at": self.clock(), "models": self.or_.models(), "zdr": self.or_.zdr_ids()}
        self.cache.write_text(json.dumps(doc, sort_keys=True))
        return doc

    def _defaults(self) -> dict:
        return json.loads(self.defaults.read_text()) if self.defaults.exists() else {}

    # -- recommend --------------------------------------------------------------------------------------------------------------
    def recommend(self, job: str, sensitivity: str = "private") -> dict:
        if job not in JOBS:
            raise LibraryError(f"unknown job {job!r}; jobs: {list(JOBS)}")
        if sensitivity not in ("public", "private"):
            raise LibraryError("sensitivity: public|private")
        chosen = self._defaults().get(f"{job}:{sensitivity}")
        default = dict(LOCAL[job]) if not chosen or chosen.startswith(("local:", "deterministic:")) else {"model": chosen, "space": f"text_api:{chosen}", "uploads": True,
                                                                                                          "free": chosen.endswith(":free")}
        reasons = ["the bundled open-weights model runs on this machine and sends nothing (D6)"] if not chosen else [f"the captain's default for {job} / {sensitivity}"]
        caveats, upgrade, fetched = [], None, None
        try:
            cat = self.list()
            fetched = cat["fetched_at"]
        except LibraryError as e:
            cat = None
            caveats.append(str(e))
        if cat:
            live, zdr = {m["id"]: m for m in cat["models"]}, set(cat["zdr"])
            for m in CANDIDATES[job][sensitivity]:
                if m not in live:
                    continue
                if sensitivity == "private" and (m.endswith(":free") or m not in zdr):
                    continue
                upgrade = {"model": m, "free": m.endswith(":free"), "uploads": True, "zdr": m in zdr, "opt_in": "egress_consent:openrouter",
                           "routing": dict(PRIVATE_ROUTING) if sensitivity == "private" else {}, "pricing": live[m]["pricing"]}
                break
            if upgrade is None and sensitivity == "private" and CANDIDATES[job]["private"]:
                caveats.append("no ZDR-listed model for this job on OpenRouter today: stay local (nothing private is sent without ZDR)")
            if upgrade and upgrade["free"]:
                caveats.append("a :free model may retain what it receives: offered for public content only")
        return {"ok": True, "job": job, "sensitivity": sensitivity, "catalogue_fetched_at": fetched,
                "picks": {"default": default, "upgrade": upgrade, "deterministic_baseline": BASELINE[job]}, "reasons": reasons, "caveats": caveats}

    # -- the captain's choice ---------------------------------------------------------------------------------------------------
    def set_default(self, job: str, sensitivity: str, model: str, by: str) -> dict:
        if by not in CAPTAIN:
            raise LibraryError("the default model is the captain's choice (it decides what is uploaded and spent)")
        if job not in JOBS or sensitivity not in ("public", "private"):
            raise LibraryError(f"job: {list(JOBS)}; sensitivity: public|private")
        if sensitivity == "private" and model.endswith(":free"):
            raise LibraryError("this source is private: free models may retain what they receive; pick the deterministic spaces or a paid model")
        if not model.startswith(("local:", "deterministic:")):
            cat = self.list()
            if model not in {m["id"] for m in cat["models"]}:
                raise LibraryError(f"model not listed by OpenRouter today: {model}: run list")
            if sensitivity == "private" and model not in set(cat["zdr"]):
                raise LibraryError(f"this source is private and {model} has no ZDR endpoint on OpenRouter's live list: pick one that does, or stay local")
        d = self._defaults()
        d[f"{job}:{sensitivity}"] = model
        self.defaults.write_text(json.dumps(d, sort_keys=True, indent=1))
        self.lib.decide(f"embed_default:{job}:{sensitivity}", model, "captain", how="set_default", options=CANDIDATES[job][sensitivity])
        return {"ok": True, "job": job, "sensitivity": sensitivity, "default": model}

    # -- measuring ---------------------------------------------------------------------------------------------------------------
    def probe(self, model: str, n_probe: int = 8, by: str = "agent", texts=None) -> dict:
        if int(n_probe) > MAX_PROBE:
            raise LibraryError(f"probe is for measuring: max {MAX_PROBE}")
        if model not in {m["id"] for m in self.list()["models"]}:
            raise LibraryError(f"model not listed by OpenRouter today: {model}: run list")
        sample = list(texts or [f"public probe text {i}" for i in range(int(n_probe))])[:int(n_probe)]
        if by not in CAPTAIN:
            return {"ok": True, "dry_run": True, "model": model, "would_send": len(sample), "content_class": "public",
                    "note": "a probe sends public probe text to OpenRouter: the user runs it (it shows in the egress log)"}
        t0 = time.perf_counter()
        res = self.or_.embed_texts(model, sample, "public")
        ms = (time.perf_counter() - t0) * 1000
        vecs = res["vectors"]
        dims = {len(v) for v in vecs}
        return {"ok": True, "dry_run": False, "model": model, "request_shape_ok": len(vecs) == len(sample) and len(dims) == 1, "dim": dims.pop() if len(dims) == 1 else None,
                "usage_tokens": res.get("usage_tokens"), "usd_measured": res.get("cost_usd"), "latency_ms": round(ms, 1),
                "free_remaining": self.or_.free_remaining() if model.endswith(":free") else None}

    def handle(self, req: dict, by: str = "agent") -> dict:
        """The tool surface (``lampway_asset_embed_models``): list|recommend|probe|set_default -> ``{ok, ...}`` or ``{ok: false, error, help}``."""
        a = req.get("action") or "recommend"
        try:
            if a == "list":
                return {"ok": True, **self.list()}
            if a == "recommend":
                return self.recommend(req.get("job") or "text_to_image", req.get("sensitivity") or "private")
            if a == "probe":
                return self.probe(req["models"][0] if req.get("models") else req.get("model"), int(req.get("n_probe") or 8), by)
            if a == "set_default":
                return self.set_default(req.get("job"), req.get("sensitivity") or "private", req.get("model") or "", by)
            raise LibraryError(f"unknown action {a!r}: list|recommend|probe|set_default (a bake-off is run by the user)")
        except (LibraryError, KeyError, TypeError, ValueError) as e:
            return {"ok": False, "error": str(e), "help": [f"jobs: {list(JOBS)}; sensitivity public|private",
                                                           "the bundled local models are the default; an OpenRouter upgrade is opt-in (Privacy panel: OpenRouter route)"]}


def bakeoff(probes: list, searchers: dict, k: int = 5) -> dict:
    """recall@k and MRR per searcher over hand-labelled ``{text, expect}`` probes; a searcher is ``fn(text, k) -> [asset ids]``."""
    out = {}
    for name, fn in searchers.items():
        hits, rr = 0, 0.0
        for p in probes:
            got = list(fn(p["text"], max(k, 10)))
            if p["expect"] in got[:k]:
                hits += 1
            rr += 1.0 / (got.index(p["expect"]) + 1) if p["expect"] in got[:k] else 0.0
        out[name] = {"recall_at_5": hits / len(probes) if probes else 0.0, "mrr": rr / len(probes) if probes else 0.0, "probes": len(probes)}
    return out
