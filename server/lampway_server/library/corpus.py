"""A deterministic synthetic Vault for the gates (specs/asset_library/asset_gates.md section 6): N assets with the contract's kind mix, names from an armour
vocabulary, closed-facet terms, 20 % rated, derived_from chains, generation rows, clustered 512-d vectors with known ground truth, shared tiny thumbnails, and
planted duplicates (exact copies under new source keys; re-encoded images for the near-duplicate check). Same seed, same library: built in a temp dir, never
the user's."""
from __future__ import annotations

import hashlib
import io
import itertools
import random
from pathlib import Path

import numpy as np

from .store import AssetLibrary

KIND_MIX = (("mesh", 40), ("image", 30), ("material", 10), ("map", 10), ("video", 4), ("receipt", 6))
PIECES = ("helmet", "chest", "gauntlets", "greaves", "waist", "boots", "cuirass", "pauldron", "plume", "shield")
LOOKS = ("bronze", "gold", "iron", "steel", "leather", "linen", "crimson", "brass", "silver", "copper")
STUDIOS = ("tripo", "meshy", "hi3d", "higgsfield", "openrouter", "local")
ROLES = ("plate_metal", "leather", "cloth", "trim")
CLUSTERS = 40
DIM = 512
SPACE = "gate_vec"


def _png(seed: int, size=48, jpeg=False, scale=None) -> bytes:
    from PIL import Image
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (6, 6, 3), dtype=np.uint8)
    im = Image.fromarray(base).resize((size, size), Image.Resampling.BICUBIC)
    if scale:
        im = im.resize((int(size * scale), int(size * scale)), Image.Resampling.BICUBIC)
    b = io.BytesIO()
    im.save(b, "JPEG" if jpeg else "PNG", **({"quality": 80} if jpeg else {}))
    return b.getvalue()


def build(root, n: int = 10000, seed: int = 20261005, exact_dupes: int = 200, near_dupes: int = 200) -> tuple:
    """(library, meta). ``meta`` holds the ground truth the gates check against: clusters, planted duplicates, the token queries."""
    rnd = random.Random(seed)
    ids, clock = itertools.count(1), itertools.count(1_000_000)
    lib = AssetLibrary(Path(root), idgen=lambda: f"g{next(ids):07d}", clock=lambda: float(next(clock)))
    centres = np.random.default_rng(seed).normal(size=(CLUSTERS, DIM)).astype("float32")
    vrng = np.random.default_rng(seed + 1)
    kinds = [k for k, w in KIND_MIX for _ in range(w)]
    thumbs = [_png(seed * 7 + p, 64, jpeg=True) for p in range(16)]                     # shared per palette: few blobs
    meta = {"seed": seed, "n": n, "cluster_of": {}, "exact": [], "near": [], "images": {}, "token_queries": []}
    made: list = []
    with lib.bulk():
        for i in range(n):
            kind = kinds[rnd.randrange(len(kinds))]
            piece, look = rnd.choice(PIECES), rnd.choice(LOOKS)
            name = f"{look} {piece} {i:05d}"
            data = _png(seed + i) if kind in ("image", "map") else f"{kind}-{seed}-{i}".encode()
            spec = {"kind": kind, "name": name, "source": {"kind": "corpus", "key": f"k{i}"}, "files": [{"role": "main", "bytes": data, "storage": "cas", "name": f"{i}.bin"}],
                    "terms": [{"facet": "piece_type", "label": piece}, {"facet": "material_role", "label": rnd.choice(ROLES)}]}
            if kind in ("mesh", "image", "material", "map", "video"):
                spec["files"].append({"role": "thumb", "bytes": thumbs[i % len(thumbs)], "storage": "cas", "name": "thumb.jpg"})
            if kind == "mesh":
                spec["stats"] = {"faces": rnd.randrange(500, 90000), "topology": rnd.choice(("Quad", "Tri"))}
            if rnd.random() < 0.35:
                prompt = f"a {look} {piece}, game armour"
                spec["generation"] = {"studio": rnd.choice(STUDIOS), "model": "m1", "action": "image_gen", "prompt_text": prompt,
                                      "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "job_id": f"job{i}", "cost_basis": "none"}
            r = lib.put(spec)
            if rnd.random() < 0.2:
                lib.rate(r["id"], "captain", stars=rnd.randrange(1, 6))
            c = (PIECES.index(piece) * len(LOOKS) + LOOKS.index(look)) % CLUSTERS
            lib.put_embedding(lib.version_of(r["id"]), SPACE, centres[c] + 0.35 * vrng.normal(size=DIM).astype("float32"), model="corpus")
            meta["cluster_of"][r["id"]] = c
            if kind == "image":
                meta["images"][r["id"]] = seed + i
            if made and rnd.random() < 0.3:                                           # derived_from to one of the last five: chains of length 1..5
                prev = made[-rnd.randrange(1, min(5, len(made)) + 1)]
                if prev != r["id"]:
                    lib.relate(r["id"], "derived_from", prev, "rule")
            made.append(r["id"])
        originals = [a for a in list(meta["cluster_of"])[:exact_dupes]]
        for k, aid in enumerate(originals):                                           # the same bytes under a new source key: must dedupe
            a = lib.get(aid)
            data = open(next(f for f in a["files"] if f["role"] == "main")["locations"][0]["path"], "rb").read()
            files = [{"role": "main", "bytes": data, "storage": "cas", "name": "copy.bin"}]
            files += [{"role": "thumb", "bytes": open(f["locations"][0]["path"], "rb").read(), "storage": "cas"} for f in a["files"] if f["role"] == "thumb"]
            r = lib.put({"kind": a["kind"], "name": a["name"] + " copy", "source": {"kind": "corpus-copy", "key": f"c{k}"}, "files": files})
            meta["exact"].append({"original": aid, "result": r["id"], "deduped": r["deduped"]})
        for k, (aid, s) in enumerate(list(meta["images"].items())[:near_dupes]):      # re-encoded / resized images: candidates, never auto-merged
            r = lib.put({"kind": "image", "name": f"near {k}", "source": {"kind": "corpus-near", "key": f"n{k}"},
                         "files": [{"role": "main", "bytes": _png(s, jpeg=True, scale=1.5), "storage": "cas", "name": "near.jpg"},
                                   {"role": "thumb", "bytes": thumbs[k % len(thumbs)], "storage": "cas", "name": "thumb.jpg"}]})
            meta["near"].append({"original": aid, "result": r["id"], "seed": s})
    for t in range(0, n, max(1, n // 50)):
        meta["token_queries"].append(f"{t:05d}")
    return lib, meta

