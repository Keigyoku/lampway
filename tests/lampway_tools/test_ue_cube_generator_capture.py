# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure packing/input falsifiers. These fixtures are SYNTHETIC, never UE render proof."""
import importlib.util
import json
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[2] / 'scripts/lampway/ue_cube_generator_capture.py'
SPEC = importlib.util.spec_from_file_location('cube_capture', PATH)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
SHAPER = dict(base=2, lin_side_slope=1, lin_side_offset=1, log_side_slope=1, log_side_offset=0)


def test_input_grid_is_red_fastest_and_does_not_compute_an_output():
    assert list(C.grid(2, SHAPER))[:4] == [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]


@pytest.mark.parametrize('shaper', [dict(SHAPER, base=10), dict(SHAPER, log_side_slope=0),
                                    dict(SHAPER, lin_side_offset=3), dict(SHAPER, base=float('nan'))])
def test_invalid_input_shaper_is_refused(shaper):
    with pytest.raises(ValueError):
        list(C.grid(2, shaper))


def test_engine_is_measured_and_exact_version_and_changelist_must_match():
    expected = dict(version='5.8.2', changelist=56702186)
    assert C.engine_identity('5.8.2-56702186+++UE5+Release-5.8', expected)['raw'].startswith('5.8.2-')
    for raw in ('5.8.2-1+++UE5', '5.8.1-56702186+++UE5', '5.8.2'):
        with pytest.raises(ValueError, match='actual UE'):
            C.engine_identity(raw, expected)


def test_incomplete_capture_never_publishes_a_sidecar(tmp_path):
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 2}}}}
    with pytest.raises(ValueError, match='incomplete'):
        C.write_outputs(tmp_path, request, {}, [[0, 0, 0]], {}, [])
    assert not list(tmp_path.iterdir())


def test_uncontrolled_capture_never_claims_a_genuine_cube(tmp_path):
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 2}}, 'tonemap': {}},
               'name': 'synthetic', 'shaper': SHAPER, 'shaper_source': 'synthetic test only'}
    with pytest.raises(ValueError, match='controls'):
        C.write_outputs(tmp_path, request, {}, [[0, 0, 0]] * 8, {}, [])
    assert not list(tmp_path.iterdir())


def test_synthetic_capture_packing_matches_existing_cube_validator(tmp_path):
    repo = PATH.parents[2]
    profile = json.loads((repo / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    profile['project']['cvars']['r.LUT.Size'] = 2
    request = dict(profile=profile, name='synthetic', shaper=SHAPER, shaper_source='synthetic test only')
    controls = [dict(input=[0.18] * 3, raw=[0.18] * 3, display=[0.4] * 3,
                     tone_curve_disabled=[0.5] * 3) for _ in range(4)]
    cube, sidecar = C.write_outputs(tmp_path, request, profile['engine'], list(C.grid(2, SHAPER)), {}, controls)
    spec = importlib.util.spec_from_file_location('existing_cube_validator',
            repo / 'src/scripts/mixar/modules/lampway_tools/ue/cube.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    assert validator.validate(profile, cube, sidecar)['state'] == 'valid'
    meta = json.loads(sidecar.read_text())
    assert meta['capture']['precision_bits_per_channel'] == 8
    assert meta['capture']['controls'] == controls
    with pytest.raises(ValueError, match='already exists'):
        C.write_outputs(tmp_path, request, profile['engine'], list(C.grid(2, SHAPER)), {}, controls)


def test_plan_counts_actual_renderer_calls_without_claiming_runtime():
    request = dict(profile={'project': {'cvars': {'r.LUT.Size': 32}}}, shaper=SHAPER, max_seconds=600)
    result = C.plan(request)
    assert result['cube_rows'] == 32768 and result['scene_captures'] == 32780
    assert result['writes'] is False and 'unmeasured' in result['runtime_estimate']
