# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""NumPy-only ARAP clearance-handle candidate (canon 01, 03 and 05).

Sorkine & Alexa (2007): local proper rotations, global constrained graph solve.
Positive uniform weights on unique mesh edges are a delegated candidate choice;
CG uses edge matvecs, never a dense vertex-by-vertex matrix. Coordinates are in
body-frame metres. All nonmovable vertices remain exactly fixed. Explicit source
ledger pairs share displacement; their authored source offsets are retained.
Generated UV duplicates weld analytically at 1e-5 m; output keeps original ids.
This generated-armour adjacency weld is unsuitable for authored rig topology.

Defaults were delegated on 2026-10-08 and remain physically untested. This solver
neither infers handles from a body nor certifies collision/clearance or appearance:
the native adapter must recheck the full candidate before publication. Exceptions
refuse candidates, and inputs are never modified.
"""
from collections.abc import Mapping
from itertools import product

import numpy as np


def _index(value, n):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or not 0 <= value < n:
        raise ValueError('vertex indices must be integers within the source mesh')
    return int(value)


def _groups(v, pairs, weld_m):
    parent = np.arange(len(v))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        parent[root(j)] = root(i)

    for i, j in pairs:
        join(i, j)
    if weld_m:
        bins = {}
        offsets = tuple(product((-1, 0, 1), repeat=3))
        for i, position in enumerate(v):
            key = tuple(int(x) for x in np.floor(position / weld_m))
            for offset in offsets:
                for j in bins.get(tuple(a + b for a, b in zip(key, offset)), ()):
                    if np.linalg.norm(position - v[j]) <= weld_m:
                        join(i, j)
            bins.setdefault(key, []).append(i)
    return np.unique([root(i) for i in range(len(v))], return_inverse=True)[1]


def _cg(matvec, rhs, initial, diagonal, iterations, tolerance):
    """Independent preconditioned CG columns, with a checked residual."""
    answer = initial.copy()
    used, residual_max = 0, 0.
    for column in range(3):
        b, x = rhs[:, column], answer[:, column]
        r = b - matvec(x)
        bound = tolerance * max(1., float(np.linalg.norm(b)))
        if np.linalg.norm(r) <= bound:
            continue
        z = r / diagonal
        p, rz = z.copy(), float(r @ z)
        for step in range(1, iterations + 1):
            ap = matvec(p)
            denominator = float(p @ ap)
            if not np.isfinite(denominator) or denominator <= 0:
                raise RuntimeError('ARAP linear solve did not converge (nonpositive CG curvature)')
            alpha = rz / denominator
            x += alpha * p
            r -= alpha * ap
            if np.linalg.norm(r) <= bound:
                break
            z = r / diagonal
            next_rz = float(r @ z)
            p = z + (next_rz / rz) * p
            rz = next_rz
        actual = float(np.linalg.norm(b - matvec(x)))
        if not np.isfinite(actual) or actual > bound:
            raise RuntimeError('ARAP linear solve did not converge within linear_iterations')
        used = max(used, step)
        residual_max = max(residual_max, actual)
    return answer, used, residual_max


def solve_arap(vertices, triangles, movable, handles, seam_pairs=(), *, weld_m=1e-5,
               max_iterations=30, convergence_m=1e-7, linear_iterations=300, linear_tol=1e-10):
    """Return ``(original-id positions, metrics)`` or refuse with an exception.

    ``movable`` is an explicit boolean vector (cloth/leather membership). ``handles``
    maps original integer vertex ids to explicit clearance-target positions. Seam
    pairs come only from the frozen source ledger. ``weld_m=0`` disables generated
    duplicate welding, while retaining the ledger's hard displacement constraints.
    No mesh is returned if either iterative solve exhausts its configured budget.
    """
    v = np.array(vertices, dtype=float, copy=True)
    t = np.asarray(triangles)
    move = np.asarray(movable)
    if v.ndim != 2 or v.shape[1:] != (3,) or len(v) < 3 or not np.isfinite(v).all():
        raise ValueError('vertices must be a nonempty finite Nx3 metre array')
    if t.ndim != 2 or t.shape[1:] != (3,) or not len(t) or t.dtype.kind not in 'iu':
        raise ValueError('triangles must be a nonempty integer Mx3 array')
    if np.any(t < 0) or np.any(t >= len(v)):
        raise ValueError('triangle vertex index outside source mesh')
    if move.shape != (len(v),) or move.dtype.kind != 'b':
        raise ValueError('movable must be an explicit boolean vector matching vertices')
    if not isinstance(handles, Mapping):
        raise ValueError('handles must map integer source ids to finite positions')
    for name, value in (('max_iterations', max_iterations), ('linear_iterations', linear_iterations)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    for name, value in (('convergence_m', convergence_m), ('linear_tol', linear_tol), ('weld_m', weld_m)):
        if not np.isscalar(value) or isinstance(value, (bool, str)) or not np.isfinite(value) or value < 0 or (name != 'weld_m' and value == 0):
            raise ValueError(f'{name} must be finite and positive (weld_m may be zero)')
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    with np.errstate(over='ignore', invalid='ignore'):
        areas = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if not np.isfinite(areas).all() or np.any(areas == 0):
        raise ValueError('degenerate or numerically unrepresentable source triangle')
    pairs = []
    for pair in seam_pairs:
        if len(pair) != 2:
            raise ValueError('source seam pairs must contain two vertex ids')
        pairs.append(tuple(_index(i, len(v)) for i in pair))
    targets = {}
    for i, position in handles.items():
        i = _index(i, len(v))
        position = np.asarray(position, dtype=float)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError('clearance handle must have three finite metre coordinates')
        targets[i] = position.copy()
    groups = _groups(v, pairs, weld_m)
    count = int(groups.max()) + 1
    fixed = np.zeros(count, dtype=bool)
    constraints = np.zeros((count, 3))

    def constrain(i, displacement):
        group = groups[i]
        if fixed[group] and not np.array_equal(constraints[group], displacement):
            raise ValueError('contradictory fixed/handle/seam displacement constraints')
        fixed[group] = True
        constraints[group] = displacement

    for i in np.flatnonzero(~move):
        constrain(i, np.zeros(3))
    for i, position in targets.items():
        constrain(i, position - v[i])
    edges = np.unique(np.sort(np.concatenate((t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]])), axis=1), axis=0)
    source_edges = v[edges[:, 0]] - v[edges[:, 1]]
    lengths = np.linalg.norm(source_edges, axis=1)
    if np.any(lengths == 0):
        raise ValueError('zero-length rest edge')
    gi, gj = groups[edges[:, 0]], groups[edges[:, 1]]
    neighbours = [[] for _ in range(count)]
    for i, j in zip(gi, gj):
        if i != j:
            neighbours[i].append(j)
            neighbours[j].append(i)
    seen = set()
    components = []
    for start in range(count):
        if start in seen:
            continue
        pending, component = [start], []
        seen.add(start)
        while pending:
            i = pending.pop()
            component.append(i)
            for j in neighbours[i]:
                if j not in seen:
                    seen.add(j)
                    pending.append(j)
        if not fixed[component].any():
            raise ValueError('disconnected graph component has no fixed vertex or clearance handle anchor')
        components.append(component)
    active = gi != gj
    ei, ej = gi[active], gj[active]
    free = np.flatnonzero(~fixed)
    degree = np.bincount(np.concatenate((ei, ej)), minlength=count).astype(float)

    def laplacian(x):
        out = np.zeros_like(x)
        difference = x[ei] - x[ej]
        np.add.at(out, ei, difference)
        np.add.at(out, ej, -difference)
        return out

    def matvec(x):
        full = np.zeros(count)
        full[free] = x
        return laplacian(full)[free]

    fixed_lap = laplacian(constraints)
    displacement = constraints.copy()
    # A rigid handle configuration gives an exact ARAP seed. Otherwise seed each
    # component by translation; the local/global steps determine free vertices.
    group_ids = [[] for _ in range(count)]
    for i, group in enumerate(groups):
        group_ids[group].append(i)
    for component in components:
        ids = np.array([i for group in component for i in group_ids[group]])
        anchor_ids = [i for i in ids if fixed[groups[i]]]
        p = v[anchor_ids]
        q = p + constraints[groups[anchor_ids]]
        rotation = np.eye(3)
        if len(p) >= 3:
            u, _, vt = np.linalg.svd((p - p.mean(axis=0)).T @ (q - q.mean(axis=0)))
            correction = np.eye(3)
            correction[2, 2] = np.linalg.det(vt.T @ u.T)
            rotation = vt.T @ correction @ u.T
        translation = q.mean(axis=0) - p.mean(axis=0) @ rotation.T
        candidate = v[ids] @ rotation.T + translation - v[ids]
        displacement[groups[ids]] = candidate
    displacement[fixed] = constraints[fixed]
    max_linear, residual, delta = 0, 0., 0.
    converged = False
    for iteration in range(1, max_iterations + 1):
        positions = v + displacement[groups]
        current_edges = positions[edges[:, 0]] - positions[edges[:, 1]]
        covariance = np.zeros((count, 3, 3))
        outer = source_edges[:, :, None] * current_edges[:, None, :]
        np.add.at(covariance, gi, outer)
        np.add.at(covariance, gj, outer)
        u, _, vt = np.linalg.svd(covariance)
        correction = np.broadcast_to(np.eye(3), (count, 3, 3)).copy()
        correction[:, 2, 2] = np.linalg.det(vt.transpose(0, 2, 1) @ u.transpose(0, 2, 1))
        rotations = vt.transpose(0, 2, 1) @ correction @ u.transpose(0, 2, 1)
        desired = np.einsum('eij,ej->ei', .5 * (rotations[gi] + rotations[gj]), source_edges) - source_edges
        rhs = np.zeros((count, 3))
        np.add.at(rhs, ei, desired[active])
        np.add.at(rhs, ej, -desired[active])
        previous = displacement.copy()
        if len(free):
            displacement[free], used, current_residual = _cg(matvec, (rhs - fixed_lap)[free], displacement[free],
                                                            degree[free], linear_iterations, linear_tol)
            max_linear = max(max_linear, used)
            residual = max(residual, current_residual)
        delta = float(np.linalg.norm(displacement - previous, axis=1).max())
        if not np.isfinite(displacement).all():
            raise RuntimeError('ARAP produced nonfinite candidate')
        if delta <= convergence_m:
            converged = True
            break
    if not converged:
        raise RuntimeError('ARAP local/global solve did not converge within max_iterations')
    positions = v + displacement[groups]
    for i, target in targets.items():
        positions[i] = target
        # Avoid subtraction/addition roundoff splitting an exact source seam.
        duplicates = [j for j in group_ids[groups[i]] if np.array_equal(v[j], v[i])]
        positions[duplicates] = target
    positions[~move] = v[~move]
    strain = np.abs(np.linalg.norm(positions[edges[:, 0]] - positions[edges[:, 1]], axis=1) / lengths - 1.)
    gap = max((float(np.linalg.norm(positions[i] - positions[j])) for i, j in pairs), default=0.)
    return positions, {'engine': 'arap_clearance_handles', 'physical_status': 'untested', 'converged': True,
                       'iterations': iteration, 'linear_iterations_max': max_linear, 'linear_residual_max': residual,
                       'update_max_m': delta, 'fixed_max_m': 0., 'seam_gap_max_m': gap,
                       'strain_p95': float(np.percentile(strain, 95)), 'strain_max': float(strain.max()),
                       'welded_vertices': len(v) - count, 'handle_count': len(targets), 'weights': 'positive_uniform',
                       'settings': {'weld_m': weld_m, 'max_iterations': max_iterations, 'convergence_m': convergence_m,
                                    'linear_iterations': linear_iterations, 'linear_tol': linear_tol}}
