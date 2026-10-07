# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The native weight sidecar (canon 03 F.6, canon 07 INV-07.3): the MetaHuman body's weights as the ENGINE holds them, read into
the body frame. Pure numpy (no bpy).

The file is the one Titan's ``armour-validate.py sidecar`` writes through its UE editor leg (``recipes/armour-sidecar-ue.py``):
schema ``titan.native-weight-sidecar/1`` around a result ``titan.native-weight-sidecar-result/1`` - for every render vertex a bone
under ``root_bone`` influences: position and normal in UE asset/component space (cm, Z up, left-handed), UV0 and every named bone
weight (all influences: never the 4 of a GLB copy), plus every triangle touching a kept vertex and the bone parents.

Frames (canon 01 B): the MetaHuman's wearer's left is UE +X and up is +Z, so in a left-handed frame its front is +Y; the body frame
is metres, Z up, front -Y, wearer's left +X. Hence ``(x, -y, z) / 100``. A triangle's winding is NOT assumed across the handedness
change: each triangle is oriented so its face normal agrees with the engine's own normals at its corners (``reoriented`` counts the
flips). A triangle with a corner outside the sidecar is dropped (counted): its weights there are unknown.

``read`` refuses a file that is not the engine's weights, by name; ``skin`` poses the body with all its influences
(linear blend of the per-bone rest -> pose maps), the way canon 05 B validates against the native body."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCHEMA = "titan.native-weight-sidecar/1"
RESULT_SCHEMA = "titan.native-weight-sidecar-result/1"
SUM_TOL = 1e-3                  # an engine row sums to 1 within its storage quantum (1/255 per influence at worst is far above this)
UE_TO_BODY = np.diag([0.01, -0.01, 0.01])           # (x, -y, z) / 100: canon 01 B, the MetaHuman's left is UE +X


class SidecarError(ValueError):
    pass


@dataclass
class NativeBody:
    ids: np.ndarray             # (n,) render vertex ids, ascending
    V: np.ndarray               # (n, 3) rest positions, body frame, metres
    N: np.ndarray               # (n, 3) unit normals, body frame
    T: np.ndarray               # (m, 3) triangles over the rows of V (winding for the body frame)
    names: list                 # bones, sorted
    W: np.ndarray               # (n, len(names)) engine weights
    parents: dict
    root_bone: str
    dropped_triangles: int
    reoriented: int


def _doc(source):
    if isinstance(source, dict):
        return source
    p = Path(source)
    if not p.is_file():
        raise SidecarError(f"{source} not found: the sidecar is the file the UE editor leg wrote (Titan armour-validate.py sidecar)")
    return json.loads(p.read_text(encoding="utf-8"))


def read(source):
    """A NativeBody from a sidecar document or file; a SidecarError names what makes it not the engine's weights."""
    d = _doc(source)
    if d.get("schema") != SCHEMA:
        raise SidecarError(f"not a native weight sidecar: schema {d.get('schema')!r}, expected {SCHEMA} (Titan armour-validate.py sidecar)")
    if (d.get("conventions") or {}).get("units") != "cm":
        raise SidecarError(f"the sidecar's units are {(d.get('conventions') or {}).get('units')!r}: the engine's are cm (UE asset space)")
    r = d.get("result") or {}
    if r.get("errors"):
        raise SidecarError(f"the editor leg reported errors: {sorted(r['errors'])} - re-run it; a failed read is not a body")
    if r.get("schema") != RESULT_SCHEMA:
        raise SidecarError(f"the sidecar's result schema is {r.get('schema')!r}, expected {RESULT_SCHEMA}")
    parents = dict(r.get("bones") or {})
    rows = r.get("vertices") or {}
    if not rows:
        raise SidecarError("the sidecar has no vertices: no bone under its root_bone influences the body")
    ids = np.array(sorted(int(k) for k in rows), dtype=np.int64)
    names = sorted(parents)
    col = {b: j for j, b in enumerate(names)}
    P = np.zeros((len(ids), 3))
    Nr = np.zeros((len(ids), 3))
    W = np.zeros((len(ids), len(names)))
    for i, vid in enumerate(ids):
        row = rows[str(int(vid))]
        P[i], Nr[i] = row["position"], row.get("normal") or (0.0, 0.0, 0.0)
        for b, w in row["weights"].items():
            if b not in col:
                raise SidecarError(f"vertex {int(vid)} is weighted to {b!r}, which is not among the sidecar's bones")
            W[i, col[b]] += float(w)
    s = W.sum(1)
    bad = np.flatnonzero(np.abs(s - 1.0) > SUM_TOL)
    if len(bad):
        raise SidecarError(f"{len(bad)} vertices' weights do not sum to 1 within {SUM_TOL} (e.g. vertex {int(ids[bad[0]])}: sum {s[bad[0]]:.6f}): "
                           "not the engine's normalised weights")
    V = P @ UE_TO_BODY.T
    N = Nr @ UE_TO_BODY.T
    n = np.linalg.norm(N, axis=1)
    N = np.where(n[:, None] > 0, N / np.maximum(n, 1e-30)[:, None], 0.0)
    where = {int(v): i for i, v in enumerate(ids)}
    tris, dropped, flipped = [], 0, 0
    for t in r.get("triangles") or []:
        c = t[1:4]
        if all(int(x) in where for x in c):
            a, b, e = (where[int(x)] for x in c)
            if np.cross(V[b] - V[a], V[e] - V[a]) @ (N[a] + N[b] + N[e]) < 0:
                b, e = e, b                                                  # orient by the engine's normals, never by an assumed handedness
                flipped += 1
            tris.append((a, b, e))
        else:
            dropped += 1
    return NativeBody(ids=ids, V=V, N=N, T=np.array(tris, dtype=np.int64).reshape(-1, 3), names=names, W=W, parents=parents,
                      root_bone=r.get("root_bone"), dropped_triangles=dropped, reoriented=flipped)


def skin(body, mats):
    """(V, N) of the native body posed by ``mats`` {bone: 4x4 rest -> pose map in the body frame}, every influence blended
    (linear blend skinning; normals by the blended linear part, renormalised). A weighted bone missing from ``mats`` is refused."""
    used = [j for j in range(len(body.names)) if body.W[:, j].any()]
    missing = [body.names[j] for j in used if body.names[j] not in mats]
    if missing:
        raise SidecarError(f"the skeleton lacks bones the native body is weighted to: {missing[:10]} - the armature must be the native skeleton")
    M = np.zeros((len(body.V), 4, 4))
    for j in used:
        M += body.W[:, j, None, None] * np.asarray(mats[body.names[j]], float)[None]
    Ph = np.concatenate([body.V, np.ones((len(body.V), 1))], 1)
    V = np.einsum("nij,nj->ni", M, Ph)[:, :3]
    N = np.einsum("nij,nj->ni", M[:, :3, :3], body.N)
    n = np.linalg.norm(N, axis=1)
    return V, np.where(n[:, None] > 0, N / np.maximum(n, 1e-30)[:, None], 0.0)
