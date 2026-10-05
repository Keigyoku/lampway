# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The inpainting half of robust skin-weight transfer, after Abdrashitov, Raichstat, Monsen and Hill, "Robust Skin Weights Transfer via Weight Inpainting" (SIGGRAPH Asia 2023): vertices with a trustworthy
# match keep their weights; every other vertex is filled by a constrained biharmonic solve over the robust Laplacian (Sharp and Crane): Q = -L + L M^-1 L, matched weights fixed. Written from the paper's
# description (not copied from the add-on of the same name). Runs in the science python (numpy, scipy, robust_laplacian); the matching is done on the Blender side so both engines see the same matches.
# python robust_weight_transfer.py <in.npz> <out.npz> [point|surface]
#   in.npz: V (n x 3 target vertices), F (m x 3 triangles), matched (n bool), W (n x g weights; rows of unmatched vertices ignored)
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
if __name__ == '__main__' and len(_A) < 2:
    if not _A: _ax.home(__file__, 'Fill the weights of unmatched vertices by a biharmonic solve over the robust Laplacian (robust skin-weight transfer, inpainting half)')
    else: print(f'error: {len(_A)} argument(s); at least 2 needed')
    _ax.helps(['python scripts/rig/robust_weight_transfer.py <in.npz> <out.npz> [point|surface]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
import numpy as np, scipy.sparse as sp, scipy.sparse.linalg as spl, robust_laplacian
d = np.load(_A[0]); V, F, matched, W = d['V'].astype(float), d['F'], d['matched'].astype(bool), d['W'].astype(float)
mode = _A[2] if len(_A) > 2 else 'point'
if mode == 'surface':
    L, M = robust_laplacian.mesh_laplacian(V, F.astype(np.int64))
else:
    L, M = robust_laplacian.point_cloud_laplacian(V)
Minv = sp.diags(1.0 / np.maximum(M.diagonal(), 1e-12))
Q = (-L + L @ Minv @ L).tocsc()
known, unknown = np.flatnonzero(matched), np.flatnonzero(~matched)
out = W.copy()
if len(unknown) and len(known):
    Quu = Q[unknown][:, unknown].tocsc(); Quk = Q[unknown][:, known]
    rhs = -(Quk @ W[known])
    out[unknown] = spl.splu(Quu).solve(rhs) if Quu.shape[0] < 20000 else np.column_stack([spl.cg(Quu, rhs[:, k])[0] for k in range(W.shape[1])])
out = np.clip(out, 0, None)
np.savez(_A[1], W=out)
_ax.kv({'matched': int(len(known)), 'inpainted': int(len(unknown)), 'groups': int(W.shape[1]), 'mode': mode})
