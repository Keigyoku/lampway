"""Embedding service (specs/asset_library/asset_embed.md + asset_embed_models.md): plan, then run.

``plan`` never sends anything. The deterministic spaces (``image_hist``, ``image_dhash``, ``shape_d2``) run locally for anyone. A space that UPLOADS (``text_api:<model>``)
runs only on the user's confirm, and its routing law is the user's: private content (anything without a public licence) goes only to a model on OpenRouter's live ZDR
endpoint list, with ``provider: {"zdr": true, "data_collection": "deny"}``, and never to a ``:free`` model; the eligible list is read live, never hard-coded.
A request that timed out after being sent is ``submission_unknown`` and is never resent."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from .. import egress as EG
from ..agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact
from . import ingest as I
from . import localmodels as LM
from . import spaces as SP
from .store import AssetLibrary, LibraryError

PUBLIC_LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "MIT", "Apache-2.0"}
IMAGE_KINDS = ("image", "hdri", "map")
PRIVATE_ROUTING = {"zdr": True, "data_collection": "deny"}
DETERMINISTIC = ("image_hist", "image_dhash", "shape_d2")
BATCH = 32


class OpenRouterEmbed:
    def __init__(self, api_key: str, transport=None, base_url: str = BASE_URL):
        self._key, self._transport, self._base = api_key, transport, base_url

    def _client(self):
        return httpx.Client(transport=self._transport, timeout=60, headers={"Authorization": f"Bearer {self._key}", "HTTP-Referer": REFERER, "X-Title": TITLE})

    def catalogue(self, content_class: str):
        with EG.context(route="openrouter", kind="request", content_class=content_class), self._client() as c:
            live = {r["id"] for r in c.get(f"{self._base}/embeddings/models").json().get("data", [])}
            zdr = {(r.get("model_id") or r.get("id")) for r in c.get(f"{self._base}/endpoints/zdr").json().get("data", [])} if content_class == "private" else set()
        return live, zdr

    def check(self, model: str, content_class: str):
        live, zdr = self.catalogue(content_class)
        if model not in live:
            raise LibraryError(f"model not listed by OpenRouter today: {model}: run list")
        if content_class == "private":
            if model.endswith(":free"):
                raise LibraryError("this source is private: free models may retain what they receive; pick the deterministic spaces or a paid ZDR model")
            if model not in zdr:
                raise LibraryError(f"this source is private and {model} has no ZDR endpoint on OpenRouter's live list: pick one that does, or stay deterministic")

    def embed_texts(self, model: str, texts: list, content_class: str) -> dict:
        body = {"model": model, "input": texts}
        if content_class == "private":
            body["provider"] = dict(PRIVATE_ROUTING)
        with EG.context(route="openrouter", kind="text", content_class=content_class, constraints=dict(PRIVATE_ROUTING) if content_class == "private" else {}), self._client() as c:
            r = c.post(f"{self._base}/embeddings", json=body)
        if r.status_code >= 400:
            raise LibraryError(redact(f"OpenRouter answered HTTP {r.status_code}", self._key))
        data = r.json()
        return {"vectors": [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])], "cost_usd": (data.get("usage") or {}).get("cost")}


class Embed:
    def __init__(self, lib: AssetLibrary, openrouter: Optional[OpenRouterEmbed] = None, local: Optional[dict] = None, models_root=None):
        self.lib, self.or_ = lib, openrouter
        self._local = dict(local or {})
        self.models_root = Path(models_root) if models_root else lib.root / "models"
        self.plans = lib.root / "embed_plans"

    # -- targets -------------------------------------------------------------------------------------------------------
    def _assets(self):
        rows = self.lib._reader().execute("SELECT a.id,a.kind,a.name,a.description,a.license_id,v.id AS vid FROM asset a JOIN version v ON v.asset_id=a.id AND v.n=a.current_version WHERE a.status='active' ORDER BY a.id").fetchall()
        return [dict(r) for r in rows]

    def _main(self, asset_id: str) -> Optional[Path]:
        for f in self.lib.get(asset_id)["files"]:
            if f["role"] == "main":
                for loc in f["locations"]:
                    if not loc["missing"] and Path(loc["path"]).is_file():
                        return Path(loc["path"])
        return None

    @staticmethod
    def content_class(row) -> str:
        return "public" if row["license_id"] in PUBLIC_LICENSES else "private"

    def _understands(self, space: str, row) -> bool:
        if space.startswith("text_api") or space == "text_local":
            return True
        p = self._main(row["id"])
        if not p:
            return False
        head = p.read_bytes()[:16] if p.stat().st_size else b""
        c = I.classify(head, p.name)
        if space in ("image_hist", "image_dhash", "image_local"):
            return row["kind"] in IMAGE_KINDS and bool(c) and c["kind"] in ("image", "hdri") and c["container"] in ("png", "jpeg", "webp", "gif")
        return row["kind"] == "mesh" and bool(c) and c["container"] == "glb"

    def _have(self, space: str) -> set:
        r = self.lib._reader().execute("SELECT version_id FROM embedding WHERE space=? AND sub_key=''", (space,)).fetchall()
        return {x[0] for x in r}

    def _embedder(self, base: str):
        if base not in self._local:
            self._local[base] = LM.load(self.models_root, LM.BASES[base])
        return self._local[base]

    # -- plan / run ----------------------------------------------------------------------------------------------------
    def plan(self, space: str, asset_ids=None, missing_only: bool = True, model: Optional[str] = None) -> dict:
        base = space.split(":")[0]
        if base not in DETERMINISTIC and base != "text_api" and base not in LM.BASES:
            raise LibraryError(f"unknown space {space!r}; spaces: {list(DETERMINISTIC) + list(LM.BASES) + ['text_api']}")
        name = space
        if base in LM.BASES:
            self._embedder(base)                      # refuses with needs_weights / needs_runtime before anything is planned
            name = LM.MANIFEST[LM.BASES[base]]["space"]
        if base == "text_api":
            if not model:
                raise LibraryError("text_api needs a model")
            name = f"text_api:{model}"
        have = self._have(name) if missing_only else set()
        rows = [r for r in self._assets() if (not asset_ids or r["id"] in asset_ids) and r["vid"] not in have and self._understands(base, r)]
        uploads = base == "text_api"
        cc = "private" if any(self.content_class(r) == "private" for r in rows) else "public"
        est = 0.0
        if uploads:
            if not self.or_:
                raise LibraryError("no OpenRouter key: set it in Models and settings")
            if rows:
                self.or_.check(model, cc)
            est = 0.0
        pid = "plan-" + hashlib.sha1(json.dumps([name, [r["id"] for r in rows], self.lib._now()]).encode()).hexdigest()[:10]
        plan = {"plan_id": pid, "space": name, "base": base, "model": model, "targets": [r["id"] for r in rows], "planned": len(rows), "uploads": uploads, "content_class": cc,
                "estimate_usd": est, "estimate_basis": "price not in the live list: estimate unknown" if uploads else "no spend", "bytes_uploaded": 0}
        self.plans.mkdir(parents=True, exist_ok=True)
        (self.plans / f"{pid}.json").write_text(json.dumps(plan))
        return plan

    def _text(self, asset_id: str) -> str:
        a = self.lib.get(asset_id)
        terms = " ".join(t["label"] for t in a["terms"])
        return ". ".join(x for x in (a["name"], a.get("description") or "", terms, " ".join(a["tags"])) if x)

    def run(self, plan_id: str, by: str) -> dict:
        f = self.plans / f"{plan_id}.json"
        if not f.exists():
            raise LibraryError(f"no plan {plan_id}: plan first")
        plan = json.loads(f.read_text())
        if plan["uploads"] and by not in I.USER:
            raise LibraryError(f"this uploads text to openrouter: ask the user to confirm in the Vault panel (plan id {plan_id})")
        out = {"plan_id": plan_id, "space": plan["space"], "done": 0, "skipped": 0, "failed": [], "estimate_usd": plan["estimate_usd"], "actual_usd": 0.0, "bytes_uploaded": 0}
        targets = plan["targets"]
        if plan["uploads"]:
            self.or_.check(plan["model"], plan["content_class"])
            for i in range(0, len(targets), BATCH):
                chunk = targets[i:i + BATCH]
                texts = [self._text(t) for t in chunk]
                try:
                    res = self.or_.embed_texts(plan["model"], texts, plan["content_class"])
                except httpx.TimeoutException as e:
                    out["failed"] += [{"id": t, "why": f"submission_unknown: {type(e).__name__}; not resent (the request may have been accepted)"} for t in chunk]
                    continue
                except LibraryError as e:
                    out["failed"] += [{"id": t, "why": str(e)} for t in chunk]
                    continue
                out["bytes_uploaded"] += sum(len(t.encode()) for t in texts)
                out["actual_usd"] += res["cost_usd"] or 0.0
                for t, v in zip(chunk, res["vectors"]):
                    self.lib.put_embedding(self.lib.version_of(t), plan["space"], v, model=plan["model"])
                    out["done"] += 1
            return out
        if plan["base"] in LM.BASES:
            emb = self._embedder(plan["base"])
            for i in range(0, len(targets), 32):
                chunk = targets[i:i + 32]
                try:
                    vecs = emb.embed_images([self._main(t) for t in chunk]) if plan["base"] == "image_local" else emb.embed_texts([self._text(t) for t in chunk])
                except Exception as e:  # noqa: BLE001
                    out["failed"] += [{"id": t, "why": f"{type(e).__name__}: {str(e)[:120]}"} for t in chunk]
                    continue
                for t, v in zip(chunk, vecs):
                    self.lib.put_embedding(self.lib.version_of(t), plan["space"], v, model=emb.model_id)
                    out["done"] += 1
            return out
        for t in targets:
            try:
                self.ensure(t, plan["base"])
                out["done"] += 1
            except Exception as e:  # noqa: BLE001 - one bad file never stops the batch
                out["failed"].append({"id": t, "why": f"{type(e).__name__}: {str(e)[:120]}"})
        return out

    def ensure(self, asset_id: str, space: str):
        """Compute and store one deterministic descriptor now (the probe path: a similar-to query on an asset that has none yet)."""
        p = self._main(asset_id)
        if p is None:
            raise LibraryError(f"asset {asset_id} has no readable main file")
        vid = self.lib.version_of(asset_id)
        if space == "image_hist":
            self.lib.put_embedding(vid, space, SP.image_hist(p), model="deterministic")
        elif space == "image_dhash":
            self.lib.put_embedding(vid, space, SP.image_dhash(p), model="deterministic")
        elif space == "shape_d2":
            ck = self.lib._reader().execute("SELECT content_key FROM version WHERE id=?", (vid,)).fetchone()[0]
            self.lib.put_embedding(vid, space, SP.shape_d2(SP.glb_triangles(p), ck), model="deterministic", normalise=False)
        else:
            raise LibraryError(f"unknown space {space!r}")
