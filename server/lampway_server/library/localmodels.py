"""Bundled open-weights embeddings: CLIP ViT-B/32 (image tower, and its text tower for text-to-image queries in the SAME space) and bge-small (text), run by ONNX Runtime
on the CPU. Local, offline, zero egress once the weights are on disk.

No weights live in git. ``models.json`` pins every file to a repository commit and a sha256. The client build bundles them into the install
(``scripts/lampway/fetch_models.py`` from ``build_linux.sh``) and the launcher points the server at them with ``LAMPWAY_MODELS_DIR``; ``fetch`` remains the user's click for
an install without them (a plain GET of public weights through the declared ``model_download`` route; nothing of the user's is sent). Until weights and onnxruntime are both
present, ``status`` says which of ``needs_weights`` / ``needs_runtime`` applies and the Vault falls back to the deterministic spaces."""
from __future__ import annotations

import hashlib
import html
import importlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np

from .. import egress as EG
from .store import LibraryError

MODELS_FILE = Path(__file__).with_name("models.json")
MANIFEST = {m["id"]: m for m in json.loads(MODELS_FILE.read_text(encoding="utf-8"))["models"]}
BASES = {m["base"]: m["id"] for m in MANIFEST.values() if not m.get("query_only")}          # the spaces an asset can be embedded into
QUERY_ENCODERS = {m["space"]: m["id"] for m in MANIFEST.values() if m.get("query_only")}     # text encoders INTO an image space (CLIP's text tower)
CLIP_MEAN, CLIP_STD = (0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)


def clip_preprocess(im) -> np.ndarray:
    """CLIP's preprocessing: resize the short side to 224 (bicubic), centre crop 224x224, scale to 0..1, normalise, CHW float32."""
    from PIL import Image
    im = im.convert("RGB")
    w, h = im.size
    s = 224 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
    w, h = im.size
    l, t = (w - 224) // 2, (h - 224) // 2
    a = np.asarray(im.crop((l, t, l + 224, t + 224)), dtype="float32") / 255.0
    return ((a - np.array(CLIP_MEAN, "float32")) / np.array(CLIP_STD, "float32")).transpose(2, 0, 1).astype("float32")


class WordPiece:
    """BERT uncased tokenizer: lowercase, strip accents, split punctuation, greedy longest-match WordPiece, [CLS] ... [SEP]."""

    def __init__(self, vocab: list):
        self.vocab = {t: i for i, t in enumerate(vocab)}
        self.unk, self.cls, self.sep, self.pad = (self.vocab[t] for t in ("[UNK]", "[CLS]", "[SEP]", "[PAD]"))

    @classmethod
    def from_file(cls, path):
        return cls(Path(path).read_text(encoding="utf-8").splitlines())

    @staticmethod
    def _basic(text: str) -> list:
        text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
        out, cur = [], ""
        for ch in text:
            if ch.isspace():
                if cur:
                    out.append(cur)
                    cur = ""
            elif unicodedata.category(ch).startswith("P") or (33 <= ord(ch) <= 47) or (58 <= ord(ch) <= 64) or (91 <= ord(ch) <= 96) or (123 <= ord(ch) <= 126):
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(ch)
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    def _pieces(self, word: str) -> list:
        if len(word) > 100:
            return [self.unk]
        ids, start = [], 0
        while start < len(word):
            end, hit = len(word), None
            while end > start:
                piece = ("##" if start else "") + word[start:end]
                if piece in self.vocab:
                    hit = self.vocab[piece]
                    break
                end -= 1
            if hit is None:
                return [self.unk]
            ids.append(hit)
            start = end
        return ids

    def encode(self, texts, max_len: int = 128) -> dict:
        texts = [texts] if isinstance(texts, str) else list(texts)
        ids = np.full((len(texts), max_len), self.pad, dtype="int64")
        mask = np.zeros((len(texts), max_len), dtype="int64")
        for r, t in enumerate(texts):
            toks = [i for w in self._basic(t) for i in self._pieces(w)][: max_len - 2]
            row = [self.cls] + toks + [self.sep]
            ids[r, : len(row)] = row
            mask[r, : len(row)] = 1
        return {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}


def _bytes_to_unicode() -> dict:
    """CLIP / GPT-2's reversible map from the 256 byte values to printable characters (BPE runs over these, never over raw bytes)."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) + list(range(ord("\xae"), ord("\xff") + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class ClipBPE:
    """CLIP's tokenizer: html-unescaped, whitespace-collapsed, lowercased text split by CLIP's pattern (letters, single digits, other symbols), each piece byte-encoded
    and merged by rank with the last character marked ``</w>``; wrapped in start/end tokens and padded with the end token (the text tower pools at the first end token).
    The stdlib ``re`` stands in for CLIP's ``regex`` classes: letters are ``[^\\W\\d_]``, so ``_`` splits from adjacent punctuation (a rare divergence)."""
    PAT = re.compile(r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|[^\s\w]+|_+", re.IGNORECASE)

    def __init__(self, vocab: dict, merges: list, bos=None, eos=None, max_len: int = 77):
        self.vocab, self.max_len = vocab, max_len
        lines = [m for m in merges if m.strip() and not m.startswith("#version")]
        self.ranks = {tuple(m.split()): i for i, m in enumerate(lines)}
        self.bos = vocab["<|startoftext|>"] if bos is None else bos
        self.eos = vocab["<|endoftext|>"] if eos is None else eos
        self.byte = _bytes_to_unicode()
        self._cache: dict = {}

    @classmethod
    def from_dir(cls, d):
        d = Path(d)
        return cls(json.loads((d / "vocab.json").read_text(encoding="utf-8")), (d / "merges.txt").read_text(encoding="utf-8").splitlines())

    def _bpe(self, token: str) -> list:
        if token in self._cache:
            return self._cache[token]
        word = list(token[:-1]) + [token[-1] + "</w>"]
        while len(word) > 1:                                       # every merge shortens the word: bounded by its length
            best = min(((word[i], word[i + 1]) for i in range(len(word) - 1)), key=lambda p: self.ranks.get(p, float("inf")))
            if best not in self.ranks:
                break
            out, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and (word[i], word[i + 1]) == best:
                    out.append(word[i] + word[i + 1])
                    i += 2
                else:
                    out.append(word[i])
                    i += 1
            word = out
        self._cache[token] = word
        return word

    def ids(self, text: str) -> list:
        text = " ".join(html.unescape(html.unescape(text)).split()).lower()
        out = []
        for tok in self.PAT.findall(text):
            out += [self.vocab[p] for p in self._bpe("".join(self.byte[b] for b in tok.encode("utf-8"))) if p in self.vocab]
        return [self.bos] + out[: self.max_len - 2] + [self.eos]

    def encode(self, texts) -> dict:
        rows = [self.ids(t) for t in ([texts] if isinstance(texts, str) else texts)]
        n = max(len(r) for r in rows)
        return {"input_ids": np.array([r + [self.eos] * (n - len(r)) for r in rows], dtype="int64")}


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return (v / np.where(n == 0, 1, n)).astype("float32")


class OnnxEmbedder:
    def __init__(self, model_id: str, session, tokenizer: Optional[WordPiece] = None, batch: int = 32):
        self.model_id, self.session, self.tokenizer, self.batch = model_id, session, tokenizer, batch
        self.space = MANIFEST[model_id]["space"] if model_id in MANIFEST else model_id
        want = (MANIFEST.get(model_id) or {}).get("output")
        have = {o.name for o in session.get_outputs()} if hasattr(session, "get_outputs") else set()
        self._out = [want] if want in have else None                 # by name: an export's output order is not a contract

    def embed_images(self, paths) -> np.ndarray:
        from PIL import Image
        name = self.session.get_inputs()[0].name
        out = []
        for i in range(0, len(paths), self.batch):
            x = np.stack([clip_preprocess(Image.open(p)) for p in paths[i:i + self.batch]])
            out.append(np.asarray(self.session.run(self._out, {name: x})[0], dtype="float32").reshape(len(x), -1))
        return _unit(np.concatenate(out))

    def embed_texts(self, texts) -> np.ndarray:
        if self.tokenizer is None:
            raise LibraryError("this model has no tokenizer: it embeds images")
        names = {i.name for i in self.session.get_inputs()}
        out = []
        for i in range(0, len(texts), self.batch):
            enc = self.tokenizer.encode(texts[i:i + self.batch])
            hidden = np.asarray(self.session.run(self._out, {k: v for k, v in enc.items() if k in names})[0], dtype="float32")
            out.append(hidden[:, 0] if hidden.ndim == 3 else hidden)          # CLS pooling
        return _unit(np.concatenate(out))


def status(root) -> list:
    root = Path(root)
    try:
        importlib.import_module("onnxruntime")
        runtime = True
    except ImportError:
        runtime = False
    out = []
    for m in MANIFEST.values():
        missing = [f["name"] for f in m["files"] if not (root / m["id"] / f["name"]).is_file()]
        state = "needs_weights" if missing else ("ready" if runtime else "needs_runtime")
        out.append({"id": m["id"], "space": m["space"], "state": state, "missing": missing, "license": m["license"],
                    "hint": {"needs_weights": "fetch the weights (a click in the Vault panel; public files, nothing of yours is sent)", "needs_runtime": "onnxruntime is not installed in the server environment", "ready": ""}[state]})
    return out


def load(root, model_id: str) -> OnnxEmbedder:
    st = {s["id"]: s for s in status(root)}[model_id]
    if st["state"] != "ready":
        raise LibraryError(f"{st['state']}: {model_id}: {st['hint']}")
    ort = importlib.import_module("onnxruntime")
    sess = ort.InferenceSession(str(Path(root) / model_id / "model.onnx"), providers=["CPUExecutionProvider"])
    kind = MANIFEST[model_id].get("tokenizer")
    tok = WordPiece.from_file(Path(root) / model_id / "vocab.txt") if kind == "wordpiece" else ClipBPE.from_dir(Path(root) / model_id) if kind == "clip_bpe" else None
    return OnnxEmbedder(model_id, sess, tok)


def fetch(model_id: str, root, by: str, transport=None) -> dict:
    import httpx
    if by not in ("captain", "user"):
        raise LibraryError("fetching model weights needs the user's click in the Vault panel")
    spec = MANIFEST.get(model_id)
    if not spec:
        raise LibraryError(f"unknown model {model_id!r}; models: {sorted(MANIFEST)}")
    root = Path(root)
    made_root = not root.exists()
    dest = root / model_id
    dest.mkdir(parents=True, exist_ok=True)
    done = []
    try:
        for f in spec["files"]:
            part = dest / (f["name"] + ".part")
            h, n = hashlib.sha256(), 0
            with EG.context(route="model_download", kind="file", content_class="public"), httpx.Client(transport=transport, timeout=600, follow_redirects=True) as c:
                with c.stream("GET", f["url"]) as r:
                    if r.status_code >= 400:
                        raise LibraryError(f"download of {f['name']} answered HTTP {r.status_code}")
                    with open(part, "wb") as out:
                        for chunk in r.iter_bytes(1 << 20):
                            h.update(chunk)
                            n += len(chunk)
                            out.write(chunk)
            if f.get("sha256") and h.hexdigest() != f["sha256"]:
                raise LibraryError(f"sha256 mismatch for {f['name']}: expected {f['sha256'][:12]}..., got {h.hexdigest()[:12]}...: the file was discarded")
            os.replace(part, dest / f["name"])
            done.append({"name": f["name"], "url": f["url"], "sha256": h.hexdigest(), "bytes": n, "verified_against": "manifest" if f.get("sha256") else "none: pinned on first fetch"})
        (dest / "PROVENANCE.json").write_text(json.dumps({"id": model_id, "license": spec.get("license"), "source": spec.get("source"), "fetched_at": time.time(), "files": done}, indent=1))
    except BaseException:
        for p in dest.glob("*"):
            p.unlink()
        dest.rmdir()
        if made_root and not any(root.iterdir()):
            root.rmdir()
        raise
    return {"id": model_id, "files": done}


def finetune_plan() -> dict:
    """The documented fine-tune path, left as a decision: it changes what the Vault's default embedding space means, so it is the user's call."""
    return {"status": "needs_decision", "question": "Should the Vault learn the user's own vocabulary (armour pieces, materials) by fine-tuning the local image/text models on their rated assets?",
            "options": [{"id": "off", "what": "stay on the stock open weights (default)"},
                        {"id": "head", "what": "train a small linear head over frozen embeddings from the user's ratings and verdicts (cheap, local, reversible)"},
                        {"id": "full", "what": "fine-tune the model itself (needs a GPU box: never local, a compute-wrapper job under the spend caps)"}],
            "notes": "any trained artefact would be a new space (the model id changes), never an overwrite of the stock space"}


def default_spaces(root, ready: Optional[dict] = None) -> dict:
    """The Vault's default embedding spaces: the bundled local models when they can run, else the deterministic descriptors."""
    if ready is None:
        ready = {m["base"]: True for m in MANIFEST.values() if {s["id"]: s["state"] for s in status(root)}[m["id"]] == "ready"}
    image = [MANIFEST[BASES["image_local"]]["space"]] if "image_local" in ready else ["image_hist", "image_dhash"]
    text = [MANIFEST[BASES["text_local"]]["space"]] if "text_local" in ready else []
    return {"image": image, "text": text}
