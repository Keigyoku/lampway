# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure ARAP candidate proofs; no original-piece physical acceptance claim."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'src/scripts/mixar/modules/lampway_tools/pipeline/soft_conform.py'


def solver():
    assert MODULE.exists(), 'ARAP candidate solver is not implemented'
    spec = importlib.util.spec_from_file_location('soft_conform_under_test', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.solve_arap


def tetra():
    return (np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]),
            np.array([[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]]))


@pytest.mark.parametrize('rotate', [False, True])
def test_rigid_handles_preserve_shape_and_inputs(rotate):
    v, t = tetra()
    original = v.copy()
    angle = .45 if rotate else 0.
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0.],
                         [np.sin(angle), np.cos(angle), 0.], [0., 0., 1.]])
    expected = v @ rotation.T + [.01, .02, .03]
    handles = {i: expected[i] for i in (0, 1, 2)}
    result, metrics = solver()(v, t, np.ones(4, dtype=bool), handles)
    np.testing.assert_allclose(result, expected, atol=1e-7)
    np.testing.assert_array_equal(v, original)
    assert metrics['converged'] and metrics['strain_max'] < 1e-6
    assert metrics['physical_status'] == 'untested'


def golden_tube():
    folder = ROOT / 'docs/canon/goldens/C03_seam_tube'
    vertices, triangles = [], []
    for line in (folder / 'piece.obj').read_text().splitlines():
        fields = line.split()
        if fields and fields[0] == 'v':
            vertices.append([float(x) for x in fields[1:4]])
        elif fields and fields[0] == 'f':
            face = [int(x.split('/')[0]) - 1 for x in fields[1:]]
            triangles.extend([face[0], face[i], face[i + 1]] for i in range(1, len(face) - 1))
    v = np.asarray(vertices)
    pairs = [(i, j) for i in range(len(v)) for j in range(i + 1, len(v)) if np.array_equal(v[i], v[j])]
    assert len(pairs) == json.loads((folder / 'expected.json').read_text())['seam_ledger_pairs']
    return v, np.asarray(triangles), pairs


def test_c03_fixed_metal_and_source_seams():
    v, t, pairs = golden_tube()
    movable = v[:, 2] > 1.20
    handles = {int(i): v[i] + [0., 0., .001] for i in np.flatnonzero(v[:, 2] == v[:, 2].max())}
    result, metrics = solver()(v, t, movable, handles, pairs)
    np.testing.assert_array_equal(result[~movable], v[~movable])
    for i, j in pairs:
        np.testing.assert_array_equal(result[i], result[j])
    assert metrics['fixed_max_m'] == 0. and metrics['seam_gap_max_m'] == 0.
    assert metrics['welded_vertices'] >= 32
    assert np.max(np.linalg.norm(result - v, axis=1)) >= .001 - 1e-12


def test_clearance_handle_propagates_beyond_the_handle():
    v, t = tetra()
    result, metrics = solver()(v, t, np.array([False, True, True, True]), {1: [1., 0., .05]}, max_iterations=150)
    np.testing.assert_array_equal(result[0], v[0])
    np.testing.assert_array_equal(result[1], [1., 0., .05])
    assert np.linalg.norm(result[2:] - v[2:]) > 1e-4
    assert metrics['iterations'] > 1


def test_outer_nonconvergence_refuses_without_mutating_inputs():
    v, t = tetra()
    original = v.copy()
    with pytest.raises(RuntimeError, match='converg'):
        solver()(v, t, np.array([False, True, True, True]), {1: [1., 0., .05]}, max_iterations=1)
    np.testing.assert_array_equal(v, original)


@pytest.mark.parametrize('offender', ['nonfinite', 'degenerate', 'unanchored', 'fixed_handle', 'seam_handles', 'float_triangles', 'movable_dtype'])
def test_admission_falsifiers(offender):
    v, t = tetra()
    movable = np.ones(4, dtype=bool)
    handles, seams = {0: v[0]}, []
    if offender == 'nonfinite':
        v[2, 0] = np.nan
    elif offender == 'degenerate':
        t[0] = [0, 0, 2]
    elif offender == 'unanchored':
        v = np.concatenate([v, v + [3., 0., 0.]])
        t = np.concatenate([t, t + 4])
        movable = np.ones(8, dtype=bool)
    elif offender == 'fixed_handle':
        movable[0] = False
        handles[0] = [1., 0., 0.]
    elif offender == 'seam_handles':
        seams = [(0, 1)]
        handles[1] = v[1] + [0., 1., 0.]
    elif offender == 'float_triangles':
        t = t.astype(float)
    elif offender == 'movable_dtype':
        movable = [1, 1, 1, 1]
    with pytest.raises(ValueError):
        solver()(v, t, movable, handles, seams)


def test_linear_nonconvergence_refuses_c03_candidate():
    v, t, pairs = golden_tube()
    original = v.copy()
    handles = {int(i): v[i] + [0., 0., .001] for i in np.flatnonzero(v[:, 2] == v[:, 2].max())}
    with pytest.raises(RuntimeError, match='linear solve did not converge'):
        solver()(v, t, v[:, 2] > 1.20, handles, pairs, linear_iterations=1)
    np.testing.assert_array_equal(v, original)


def test_even_subpicometre_fixed_handle_motion_is_refused():
    v, t = tetra()
    with pytest.raises(ValueError, match='contradictory'):
        solver()(v, t, np.array([False, True, True, True]), {0: [1e-13, 0., 0.]})


def test_seam_duplicate_positions_are_bit_identical_with_decimal_handles():
    v, t = tetra()
    v = np.concatenate([v, v[:1]])
    t[1:, :][t[1:, :] == 0] = 4
    target = np.array([.013333333333333334, .02857142857142857, .03636363636363637])
    result, _ = solver()(v, t, np.ones(5, dtype=bool), {0: target}, [(0, 4)])
    np.testing.assert_array_equal(result[0], result[4])
    np.testing.assert_array_equal(result[0], target)


def test_source_ledger_closes_seams_when_generated_welding_is_disabled():
    v, t, pairs = golden_tube()
    shift = np.array([.01, .02, .03])
    result, _ = solver()(v, t, np.ones(len(v), dtype=bool), {0: v[0] + shift}, pairs, weld_m=0.)
    np.testing.assert_allclose(result, v + shift, atol=1e-12)
    for i, j in pairs:
        np.testing.assert_array_equal(result[i], result[j])


def test_generated_duplicate_weld_crosses_spatial_hash_bin_boundary():
    v = np.array([[.999e-5, 0., 0.], [1., 0., 0.], [0., 1., 0.],
                  [1.001e-5, 0., 0.], [-1., 0., 0.], [0., -1., 0.]])
    t = np.array([[0, 1, 2], [3, 4, 5]])
    shift = np.array([.01, .02, .03])
    result, metrics = solver()(v, t, np.ones(6, dtype=bool), {0: v[0] + shift})
    np.testing.assert_allclose(result, v + shift, atol=1e-12)
    assert metrics['welded_vertices'] == 1
    with pytest.raises(ValueError, match='no fixed vertex or clearance handle anchor'):
        solver()(v, t, np.ones(6, dtype=bool), {0: v[0] + shift}, weld_m=0.)
