"""Bundled open-weights embeddings (CLIP ViT-B image tower + bge-small text, ONNX on CPU): local, offline, zero egress.
No weights ship in git: the runner and the preprocessing are tested here with fakes; a real session needs onnxruntime and the user-fetched weights."""
import hashlib
import itertools
import json
import sys

import httpx
import numpy as np
import pytest
from PIL import Image

from lampway_server import egress as EG
from lampway_server.library import embed as EM
from lampway_server.library import localmodels as LM
from lampway_server.library.store import AssetLibrary, LibraryError

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


class FakeSession:
    """Stands in for an onnxruntime InferenceSession: records the feed and returns a fixed-shape output."""
    def __init__(self, dim, kind):
        self.dim, self.kind, self.feeds = dim, kind, []

    def get_inputs(self):
        names = ["pixel_values"] if self.kind == "clip" else ["input_ids", "attention_mask", "token_type_ids"]
        return [type("I", (), {"name": n})() for n in names]

    def run(self, outputs, feed):
        self.feeds.append(feed)
        if self.kind == "clip":
            n = feed["pixel_values"].shape[0]
            return [np.tile(np.arange(1, self.dim + 1, dtype="float32"), (n, 1))]
        n, t = feed["input_ids"].shape
        hidden = np.zeros((n, t, self.dim), "float32")
        hidden[:, 0, :] = np.arange(1, self.dim + 1)          # only token 0 (CLS) carries signal: CLS pooling must pick it
        hidden[:, 1:, :] = 99.0
        return [hidden]


def test_clip_preprocess_matches_the_documented_normalisation():
    im = Image.new("RGB", (300, 150), (255, 0, 128))
    x = LM.clip_preprocess(im)
    assert x.shape == (3, 224, 224) and x.dtype == np.float32
    mean, std = (0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)
    for c, v in enumerate((255, 0, 128)):
        assert np.allclose(x[c], (v / 255 - mean[c]) / std[c], atol=1e-5)


def test_clip_preprocess_resizes_the_short_side_and_centre_crops():
    arr = np.zeros((100, 300, 3), "uint8")
    arr[:, 80:220] = 255                                     # a white centre band (scaled x2.24 it spans 179..493 of 672 columns; the centre crop takes 224..448)
    x = LM.clip_preprocess(Image.fromarray(arr))
    assert x[0, 112, 112] > 1.5 and x[0, 112, 0] > 1.5 and x[0, 112, 223] > 1.5
    wide = np.zeros((100, 300, 3), "uint8")
    wide[:, :60] = 255                                       # white only at the far left: the crop must not see it
    assert LM.clip_preprocess(Image.fromarray(wide))[0].max() < -1.0        # the crop is all inside the band


VOCAB = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "gold", "greave", "##s", "plate", "un", "##known", ",", "."]


def test_wordpiece_tokenises_like_bert_uncased():
    tok = LM.WordPiece(VOCAB)
    enc = tok.encode("Gold Greaves, plate. Zzz", max_len=16)
    ids = enc["input_ids"][0]
    assert [VOCAB[i] for i in ids[:enc["attention_mask"][0].sum()]] == ["[CLS]", "gold", "greave", "##s", ",", "plate", ".", "[UNK]", "[SEP]"]
    assert enc["input_ids"].shape == (1, 16) and enc["token_type_ids"].sum() == 0
    long = tok.encode("gold " * 50, max_len=8)
    assert [VOCAB[i] for i in long["input_ids"][0]][-1] == "[SEP]" and long["input_ids"].shape == (1, 8)


def test_accents_and_case_are_folded():
    tok = LM.WordPiece(VOCAB + ["cafe"])
    assert [VOCAB[i] if i < len(VOCAB) else "cafe" for i in tok.encode("CAFÉ", 8)["input_ids"][0][:3]] == ["[CLS]", "cafe", "[SEP]"]


def test_clip_image_embeddings_are_l2_normalised_and_deterministic(tmp_path):
    p = tmp_path / "a.png"
    Image.new("RGB", (64, 64), (10, 200, 30)).save(p)
    emb = LM.OnnxEmbedder("clip-vit-b-32", FakeSession(512, "clip"))
    a, b = emb.embed_images([p, p]), emb.embed_images([p, p])
    assert a.shape == (2, 512) and np.allclose(np.linalg.norm(a, axis=1), 1) and np.array_equal(a, b)


def test_bge_pools_the_cls_token_and_normalises():
    sess = FakeSession(384, "bge")
    emb = LM.OnnxEmbedder("bge-small-en-v1.5", sess, tokenizer=LM.WordPiece(VOCAB))
    v = emb.embed_texts(["gold plate"])
    want = np.arange(1, 385, dtype="float32")
    assert v.shape == (1, 384) and np.allclose(v[0], want / np.linalg.norm(want))
    assert set(sess.feeds[0]) == {"input_ids", "attention_mask", "token_type_ids"}


def test_status_names_what_is_missing_and_never_downloads(tmp_path, monkeypatch):
    root = tmp_path / "models"
    st = LM.status(root)
    assert {m["id"]: m["state"] for m in st} == {"clip-vit-b-32": "needs_weights", "bge-small-en-v1.5": "needs_weights"}
    for m in LM.MANIFEST.values():
        for f in m["files"]:
            (root / m["id"]).mkdir(parents=True, exist_ok=True)
            (root / m["id"] / f["name"]).write_bytes(b"x")
    monkeypatch.setitem(sys.modules, "onnxruntime", None)             # import fails: the runtime is absent
    assert {m["state"] for m in LM.status(root)} == {"needs_runtime"}
    monkeypatch.setitem(sys.modules, "onnxruntime", object())
    assert {m["state"] for m in LM.status(root)} == {"ready"}
    assert not any(root.rglob("*.part"))


def test_the_manifest_records_licence_source_and_provenance_honestly():
    for m in LM.MANIFEST.values():
        assert m["license"] == "MIT" and m["source"].startswith("https://") and m["space"] and m["dim"] in (384, 512)
        for f in m["files"]:
            assert f["name"] and f["url"].startswith("https://") and "sha256" in f
    notice = (REPO / "NOTICE.md").read_text()
    assert "clip-vit-b-32" in notice and "bge-small-en-v1.5" in notice and "[UNVERIFIED]" in notice


def test_a_local_space_is_planned_and_run_with_zero_egress(tmp_path, monkeypatch):
    lib = make_lib(tmp_path)
    p = tmp_path / "gold.png"
    Image.new("RGB", (40, 40), (200, 160, 40)).save(p)
    lib.put({"kind": "image", "name": "gold plate", "source": {"kind": "t", "key": "g"}, "files": [{"role": "main", "path": str(p), "storage": "external"}]})
    sent = []
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: sent.append(1))
    local = {"image_local": LM.OnnxEmbedder("clip-vit-b-32", FakeSession(512, "clip")), "text_local": LM.OnnxEmbedder("bge-small-en-v1.5", FakeSession(384, "bge"), tokenizer=LM.WordPiece(VOCAB))}
    svc = EM.Embed(lib, local=local)
    for sp, dim in (("image_local", 512), ("text_local", 384)):
        plan = svc.plan(sp)
        assert plan["uploads"] is False and plan["planned"] == 1
        out = svc.run(plan["plan_id"], by="agent")                          # an agent may run a local space: nothing leaves the machine
        assert out["done"] == 1 and out["bytes_uploaded"] == 0
    assert sent == [] and set(lib.embedding_spaces()) == {"image_local:clip-vit-b-32", "text_local:bge-small-en-v1.5"}
    ids, mat = lib.load_space("image_local:clip-vit-b-32")
    assert mat.shape == (1, 512) and abs(np.linalg.norm(mat[0]) - 1) < 1e-5


def test_a_local_space_without_weights_or_runtime_is_refused_with_the_state(tmp_path):
    svc = EM.Embed(make_lib(tmp_path), models_root=tmp_path / "models")
    with pytest.raises(LibraryError, match="needs_weights"):
        svc.plan("image_local")


def test_fetch_is_the_users_click_verifies_the_pinned_hash_and_records_provenance(tmp_path, monkeypatch):
    data = b"onnx-bytes"
    good = hashlib.sha256(data).hexdigest()
    spec = {"id": "tiny", "files": [{"name": "m.onnx", "url": "https://huggingface.co/x/y/resolve/main/m.onnx", "sha256": good}]}
    monkeypatch.setitem(LM.MANIFEST, "tiny", spec)
    reqs = []
    tr = httpx.MockTransport(lambda r: (reqs.append(r), httpx.Response(200, content=data))[1])
    with pytest.raises(LibraryError, match="user's click"):
        LM.fetch("tiny", tmp_path / "models", by="agent", transport=tr)
    assert reqs == []
    out = LM.fetch("tiny", tmp_path / "models", by="captain", transport=tr)
    assert out["files"][0]["sha256"] == good and (tmp_path / "models" / "tiny" / "m.onnx").read_bytes() == data
    prov = json.loads((tmp_path / "models" / "tiny" / "PROVENANCE.json").read_text())
    assert prov["files"][0]["sha256"] == good and prov["files"][0]["verified_against"] == "manifest"
    spec["files"][0]["sha256"] = "0" * 64
    with pytest.raises(LibraryError, match="sha256 mismatch"):
        LM.fetch("tiny", tmp_path / "m2", by="captain", transport=tr)
    assert not list((tmp_path / "m2").rglob("*"))                                      # a wrong download leaves nothing behind
    spec["files"][0]["sha256"] = None
    out = LM.fetch("tiny", tmp_path / "m3", by="captain", transport=tr)
    assert json.loads((tmp_path / "m3" / "tiny" / "PROVENANCE.json").read_text())["files"][0]["verified_against"] == "none: pinned on first fetch"


def test_the_download_route_is_declared_and_content_free():
    r = EG.ROUTES["model_download"]
    assert "huggingface.co" in r.hosts and r.privacy_class == "ok" and "no user content" in r.retention


def test_the_fine_tune_path_is_a_documented_decision_not_a_silent_default():
    d = LM.finetune_plan()
    assert d["status"] == "needs_decision" and d["question"] and len(d["options"]) >= 2


def test_default_spaces_prefer_the_local_model_and_fall_back_to_deterministic(tmp_path):
    assert LM.default_spaces(tmp_path / "none") == {"image": ["image_hist", "image_dhash"], "text": []}
    ready = {"image_local": object(), "text_local": object()}
    assert LM.default_spaces(tmp_path / "none", ready=ready) == {"image": ["image_local:clip-vit-b-32"], "text": ["text_local:bge-small-en-v1.5"]}
