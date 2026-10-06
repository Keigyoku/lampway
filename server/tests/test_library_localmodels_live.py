"""The bundled embedding models with their REAL weights on the CPU (needs LAMPWAY_MODELS_DIR holding the files models.json pins, and onnxruntime).

Sanity, not a benchmark: CLIP's text tower ranks the matching render first ("a red sphere" finds the red sphere, not the blue cube), the image tower puts two renders of the
same object nearest, bge places a paraphrase nearer than an unrelated phrase, and nothing opens a network connection. Latency is printed for the report."""
import importlib.util
import os
import socket
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import localmodels as LM
from lampway_server.library import render as R
from tests.test_library_render import glb
from tests.test_library_vectors import box, sphere, torus

ROOT = os.environ.get("LAMPWAY_MODELS_DIR")
pytestmark = pytest.mark.skipif(not (ROOT and Path(ROOT).is_dir() and importlib.util.find_spec("onnxruntime")), reason="needs LAMPWAY_MODELS_DIR with the pinned weights and onnxruntime")


@pytest.fixture
def offline(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a local model tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def render(tmp_path, name, mesh, colour, size=256, yaw=0.0):
    p = tmp_path / f"{name}.png"
    img, _ = R.render_mesh(R.glb_mesh(glb(*mesh, color=colour)), size, yaw)
    Image.fromarray(img).save(p)
    return p


@pytest.mark.timeout(600)
def test_the_real_models_rank_text_against_renders_offline(tmp_path, offline):
    assert {s["id"]: s["state"] for s in LM.status(ROOT)} == {m: "ready" for m in LM.MANIFEST}
    t0 = time.perf_counter()
    img, txt, bge = (LM.load(ROOT, m) for m in ("clip-vit-b-32", "clip-vit-b-32-text", "bge-small-en-v1.5"))
    load_s = time.perf_counter() - t0
    shots = {"red sphere": render(tmp_path, "rs", sphere(32, 48), (0.85, 0.05, 0.05)), "blue cube": render(tmp_path, "bc", box(), (0.05, 0.1, 0.85)),
             "green torus": render(tmp_path, "gt", torus(), (0.1, 0.75, 0.1)), "red sphere again": render(tmp_path, "rs2", sphere(32, 48), (0.8, 0.08, 0.06), size=180, yaw=0.7)}
    t0 = time.perf_counter()
    iv = img.embed_images(list(shots.values()))
    img_s = (time.perf_counter() - t0) / len(shots)
    queries = ["a red sphere", "a blue cube", "a green torus"]
    t0 = time.perf_counter()
    tv = txt.embed_texts(queries)
    txt_s = (time.perf_counter() - t0) / len(queries)
    names = list(shots)
    sims = tv @ iv[:3].T
    print(f"\nLIVE load {load_s:.2f} s, clip image {img_s * 1000:.0f} ms/image, clip text {txt_s * 1000:.0f} ms/query; text x image cosine:\n{np.round(sims, 4)}")
    for qi, q in enumerate(queries):
        assert names[int(np.argmax(sims[qi]))] == q.removeprefix("a "), (q, sims[qi])
    assert iv.shape == (4, 512) and tv.shape == (3, 512)
    same = float(iv[0] @ iv[3])
    assert same > float(iv[0] @ iv[1]) and same > float(iv[0] @ iv[2]), same     # two renders of the red sphere are nearest each other
    bv = bge.embed_texts(["a red sphere", "a crimson ball", "invoice for a blue wooden crate"])
    print(f"LIVE bge: paraphrase {float(bv[0] @ bv[1]):.4f}, unrelated {float(bv[0] @ bv[2]):.4f}")
    assert bv.shape == (3, 384) and float(bv[0] @ bv[1]) > float(bv[0] @ bv[2])


@pytest.mark.timeout(600)
def test_the_vault_searches_its_images_by_text_with_the_bundled_models(tmp_path, offline):
    import itertools
    from lampway_server.library import embed as EM
    from lampway_server.library.store import AssetLibrary
    ids_, clock = itertools.count(1), itertools.count(1000)
    lib = AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids_):05d}", clock=lambda: float(next(clock)))
    made = {}
    for name, mesh, col in (("red sphere", sphere(32, 48), (0.85, 0.05, 0.05)), ("blue cube", box(), (0.05, 0.1, 0.85)), ("green torus", torus(), (0.1, 0.75, 0.1))):
        p = render(tmp_path, name.replace(" ", "_"), mesh, col)
        made[name] = lib.put({"kind": "image", "name": p.stem, "source": {"kind": "t", "key": name}, "files": [{"role": "main", "path": str(p), "storage": "external"}]})["id"]
    svc = EM.Embed(lib, models_root=ROOT)
    plan = svc.plan("image_local")
    assert plan["uploads"] is False and svc.run(plan["plan_id"], by="agent")["done"] == 3
    for q in made:
        assert svc.search_images(f"a {q}", k=3)[0]["id"] == made[q], q
