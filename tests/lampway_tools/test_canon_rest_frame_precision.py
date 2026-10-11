# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual measured native frame errors, unchanged strict validator, falsifiers."""
import numpy as np
import pytest
import json
import os
from pathlib import Path

from mixar.modules.lampway_tools import canon_asset as CA
from mixar.modules.lampway_tools.canon_geom.rest_frames import canonical_rest_frame, FLOAT32_FRAME_BUDGET

@pytest.mark.parametrize('index', [0,1,2])
def test_actual_float32_native_frames_project_only_for_serialization(index):
    # Owner measurements remain external, read-only; no authored asset data is
    # copied into the public synthetic regression suite.
    path=os.environ.get('LAMPWAY_FRAME_DIAGNOSTIC_RECEIPT')
    if not path:pytest.skip('actual owner frame diagnostic receipt not supplied')
    source=np.asarray(json.loads(Path(path).read_text())['frames'][index]['frame']);before=source.copy()
    assert not CA._proper(source)
    result, correction=canonical_rest_frame(source,CA._proper)
    assert CA._proper(np.round(result,12))
    assert correction['spectral_correction']<FLOAT32_FRAME_BUDGET
    assert correction['max_axis_correction_deg']<.01
    assert np.array_equal(source,before)


def test_synthetic_float32_sized_nonorthogonality_is_bounded():
    source=np.eye(3);source[0,1]=6e-6
    source/=np.linalg.norm(source,axis=0)
    before=source.copy();assert not CA._proper(source)
    result,correction=canonical_rest_frame(source,CA._proper)
    assert CA._proper(result) and correction['spectral_correction']<FLOAT32_FRAME_BUDGET
    assert np.array_equal(source,before)


def test_already_valid_rotation_keeps_every_original_value():
    source=np.array([[0,-1,0],[1,0,0],[0,0,1]],dtype=float)
    result,correction=canonical_rest_frame(source,CA._proper)
    assert np.array_equal(result,source) and correction is None


@pytest.mark.parametrize('matrix',[
    [[1,.001,0],[0,1,0],[0,0,1]], np.diag([-1,1,1]),
    np.zeros((3,3)), np.full((3,3),np.nan), np.eye(4),
])
def test_material_shear_reflection_singularity_and_invalid_values_refuse(matrix):
    with pytest.raises(ValueError):canonical_rest_frame(matrix,CA._proper)


def test_producer_budget_boundary_remains_a_real_refusal():
    inside=np.diag([1+FLOAT32_FRAME_BUDGET*.99,1,1])
    outside=np.diag([1+FLOAT32_FRAME_BUDGET*1.01,1,1])
    assert CA._proper(canonical_rest_frame(inside,CA._proper)[0])
    with pytest.raises(ValueError,match='budget'):canonical_rest_frame(outside,CA._proper)
