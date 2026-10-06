# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 01 D: vertex identities.

Tripo smart meshes split vertices at every UV seam, so vertex-index adjacency sees every UV island as its own component:
weld by position (1e-5 m) before any adjacency-based segmentation, weighting or measurement of GENERATED armour (D.1).
A position weld can invent identity across independent topology on an authored rig: never a publication step there (D.2).
Render vertices map to source vertices by rest position within a tolerance, never by a rounded key (D.3)."""

import numpy as np

WELD_M = 1e-5


def weld_keys(V, tol=WELD_M):
    """(n,) int: per vertex, the index of the first vertex in the same ``tol`` cell (equal keys = one welded vertex)."""
    V = np.asarray(V, float)
    cells = np.round(V / tol).astype(np.int64)
    _u, first, inv = np.unique(cells, axis=0, return_index=True, return_inverse=True)
    return first[np.asarray(inv).reshape(-1)]


def components(F, key=None):
    """The number of connected components of faces sharing a vertex key (the index by default)."""
    key = key or (lambda v: v)
    par = {}

    def find(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for f in F:
        ks = [key(v) for v in f]
        for k in ks[1:]:
            par[find(k)] = find(ks[0])
    return len({find(key(f[0])) for f in F})

