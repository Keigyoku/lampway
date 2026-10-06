"""The asset-search index: what the client's "Asset Library" search, training and batch scene-fill talk to.

Proven code first: TEXT by BM25 over the asset's own words (name split on camel case and separators, library, type, file name),
IMAGE by an RGB colour histogram of the preview compared by histogram intersection, HYBRID as a weighted sum. An embedding model is
the slot (not wired): ``Entry.hist`` is where a vector would sit, and ``score`` is the one place that would change. The index is a
JSON file in the server's state directory. An asset's identity, as the client sends it, is ``name|library|blend_file``; the preview
file is ``<image_name>.jpg``, paired by the ``image_name`` in the metadata row.
"""

import hashlib
import io
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

_WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|\d+")
_STOP = frozenset({"a", "an", "the", "of", "for", "with", "and", "to", "in", "on", "me", "some"})
K1, B = 1.5, 0.75
TEXT_WEIGHT, IMAGE_WEIGHT = 0.6, 0.4
MAX_PREVIEW_BYTES = 20 * 1024 * 1024       # one preview; the client's own batch cap is 250 MB over up to 500 of them
MAX_TOP_K = 50


def tokens(text: str) -> list:
    out = []
    for word in _WORDS.findall(str(text)):
        w = word.lower()
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w not in _STOP:
            out.append(w)
    return out


def identity(row: dict) -> str:
    return f"{row.get('name', '')}|{row.get('library', '')}|{row.get('blend_file', '')}"


def histogram(data: bytes) -> Optional[list]:
    """A 4x4x4 RGB histogram (64 bins, sums to 1) of an image's 32x32 thumbnail; None when the bytes are not an image."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB").resize((32, 32))
    except Exception:  # noqa: BLE001 - a corrupt preview is skipped, the asset stays text-searchable
        return None
    bins = [0] * 64
    for r, g, b in im.getdata():
        bins[(r >> 6) * 16 + (g >> 6) * 4 + (b >> 6)] += 1
    total = float(sum(bins)) or 1.0
    return [round(x / total, 5) for x in bins]


def intersection(a: list, b: list) -> float:
    return float(sum(min(x, y) for x, y in zip(a, b)))


def cosine(a: list, b: list) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return float(sum(x * y for x, y in zip(a, b)) / (na * nb)) if na and nb else 0.0


class AssetIndex:
    def __init__(self, state_dir, embedder=None):
        """``embedder``: bytes -> vector (the slot). None keeps the colour histogram and its intersection; any vector embedder is compared by cosine."""
        self.embed = embedder or histogram
        self.similar = intersection if embedder is None else cosine
        self.path = Path(state_dir) / "asset_index.json"
        self.assets: dict = {}
        self.checksum = ""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.assets = data.get("assets", {}) if isinstance(data, dict) else {}
            self.checksum = data.get("checksum", "") if isinstance(data, dict) else ""
        except (OSError, ValueError):
            pass

    # -------------------------------------------------------------- persistence
    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".assets")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"assets": self.assets, "checksum": self.checksum}, fh)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @property
    def count(self) -> int:
        return len(self.assets)

    # --------------------------------------------------------------------- diff
    def prepare(self, metadata: list) -> dict:
        wanted = {identity(r) for r in metadata}
        have = set(self.assets)
        new, removed, unchanged = sorted(wanted - have), sorted(have - wanted), len(wanted & have)
        action = "full_train" if not have else ("skip" if not new and not removed else "incremental")
        return {"action": action, "new_assets": new, "removed_assets": removed, "asset_count": len(wanted), "unchanged_count": unchanged,
                "metadata_checksum": hashlib.sha256("\n".join(sorted(wanted)).encode("utf-8")).hexdigest()}

    def status(self, metadata: list) -> dict:
        p = self.prepare(metadata)
        if not self.count:
            return {"needs_retraining": True, "message": "No trained model found. Please train first."}
        if p["action"] == "skip":
            return {"needs_retraining": False, "message": "Embeddings are up to date"}
        return {"needs_retraining": True, "message": f"{len(p['new_assets'])} new, {len(p['removed_assets'])} removed since the last training"}

    # ----------------------------------------------------------------- training
    def train(self, mode: str, metadata: list, removed: list, images: dict, checksum: str = "") -> dict:
        if mode == "full":
            self.assets = {}
        deleted = 0
        for ident in removed:
            if self.assets.pop(ident, None) is not None:
                deleted += 1
        embedded = 0
        for row in metadata:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            raw = images.get(row.get("image_name"))
            hist = self.embed(raw) if raw is not None and len(raw) <= MAX_PREVIEW_BYTES else None
            embedded += int(hist is not None)
            self.assets[identity(row)] = {"name": row["name"], "library": row.get("library", ""), "blend_file": row.get("blend_file", ""),
                                          "type": row.get("type", ""), "image_name": row.get("image_name", ""), "hist": hist}
        if checksum:
            self.checksum = checksum
        self._save()
        return {"images_embedded": embedded, "removed": deleted}

    def clear(self) -> bool:
        had = bool(self.assets)
        self.assets, self.checksum = {}, ""
        if self.path.exists():
            self.path.unlink()
        return had

    # ------------------------------------------------------------------- search
    def _doc(self, a: dict) -> list:
        return tokens(a["name"]) * 2 + tokens(a["library"]) + tokens(a["type"]) + tokens(Path(a["blend_file"]).stem)

    def search(self, prompt: str = "", image: Optional[bytes] = None, top_k: int = 10, libraries=None) -> list:
        if not self.assets:
            raise LookupError("no trained model")
        q = tokens(prompt)
        qh = self.embed(image) if image else None
        docs = {k: self._doc(a) for k, a in self.assets.items()}
        n = len(docs)
        avg = sum(len(d) for d in docs.values()) / max(n, 1)
        df = {}
        for d in docs.values():
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        scored = []
        for k, a in self.assets.items():
            if libraries and a["library"] not in libraries:
                continue
            d = docs[k]
            text = 0.0
            for t in set(q):
                f = d.count(t)
                if f:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    text += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * len(d) / max(avg, 1e-9)))
            text_norm = text / (text + 2.0)
            img = self.similar(qh, a["hist"]) if qh is not None and a.get("hist") else 0.0
            if q and qh is not None:
                score = TEXT_WEIGHT * text_norm + IMAGE_WEIGHT * img if (text > 0 or img > 0.3) else 0.0
            elif q:
                score = text_norm
            elif qh is not None:
                score = img if img > 0.05 else 0.0
            else:
                score = 0.0
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda s: (-s[0], s[1]["name"]))
        return [{"model_name": a["name"], "similarity_score": round(s, 4),
                 "metadata": {"name": a["name"], "library": a["library"], "blend_file": a["blend_file"], "type": a["type"]}}
                for s, a in scored[:max(1, min(int(top_k), MAX_TOP_K))]]
