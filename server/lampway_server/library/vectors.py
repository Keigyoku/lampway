"""Vectors: float32 little-endian, L2-normalised on write (cosine = dot), and a brute-force numpy index.

At the Vault's scale (10k x 768 float32 = 31 MB) one matmul beats any index structure and needs no daemon, no extension and no resident model; ties break by id so a
result is reproducible. A space's name includes its model, so vectors from different models are never in one matrix."""
from __future__ import annotations

import numpy as np


def pack(vec) -> bytes:
    v = np.asarray(vec, dtype="<f4").reshape(-1)
    n = float(np.linalg.norm(v))
    return (v / n if n > 0 else v).astype("<f4").tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4")


class NumpyBrute:
    def __init__(self, ids: list, matrix: np.ndarray):
        self.ids = np.asarray(ids, dtype=object)
        self.matrix = np.ascontiguousarray(matrix, dtype="float32")

    def topk(self, query, k: int) -> list:
        q = np.asarray(query, dtype="float32").reshape(-1)
        n = float(np.linalg.norm(q))
        q = q / n if n > 0 else q
        if not len(self.ids):
            return []
        sims = self.matrix @ q
        order = np.lexsort((self.ids.astype(str), -np.round(sims, 6)))[:k]
        return [(str(self.ids[i]), float(sims[i])) for i in order]
