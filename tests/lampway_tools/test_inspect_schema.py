# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-view inspection schemas describe the actual nested data, not just envelopes."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/scripts/mixar/modules/lampway_tools/inspect/schema.py'
spec = importlib.util.spec_from_file_location('inspect_schema_contract', SOURCE)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def envelope(view, data):
    return {'view': view, 'scene': 'Scene', 'count': 0, 'total': 0,
            'data': data, 'skipped': [], 'help': []}


def test_mesh_schema_checks_topology_counts_and_hole_fields():
    validator = Draft202012Validator(S.view_schema('mesh'))
    valid = envelope('mesh', {'counts': {'verts': 8, 'edges': 12, 'faces': 5, 'tris': 10,
                                        'quads': 5, 'ngons': 0, 'loose_verts': 0, 'loose_edges': 0},
                              'manifold': {'non_manifold_edges': 4, 'boundary_edges': 4},
                              'shells': [], 'holes': [{'id': 0, 'edges': 4, 'rim_length_m': 4.0}],
                              'defects': {'degenerate': 0, 'isolated_tri': 0, 'flipped_shells': 0}})
    validator.validate(valid)
    bad = copy.deepcopy(valid)
    bad['data']['holes'][0]['edges'] = 'four'
    assert list(validator.iter_errors(bad)), 'a hole edge count must be typed'
    bad = copy.deepcopy(valid)
    bad['data']['counts']['verts'] = -1
    assert list(validator.iter_errors(bad)), 'a topology count must be nonnegative'


def test_uv_and_relations_schemas_have_distinct_typed_rows():
    uv = S.view_schema('uv')['properties']['data']['properties']
    assert uv['layers']['items']['properties']['active']['type'] == 'boolean'
    assert uv['flipped_faces']['type'] == 'integer'
    relations = S.view_schema('relations')['properties']['data']['properties']
    assert relations['pairs']['items']['properties']['relation']['enum'] == [
        'inside', 'overlaps', 'on_top_of', 'under', 'touching', 'near', 'apart']


def test_all_per_view_schemas_are_current_generated_artifacts():
    for view in ['home', *S.VIEWS]:
        expected = S.view_schema(view)
        Draft202012Validator.check_schema(expected)
        artifact = ROOT / f'docs/schemas/inspect/{view}.schema.json'
        assert artifact.exists(), f'missing generated {view} schema'
        assert json.loads(artifact.read_text()) == expected


def test_budget_expiry_can_return_partial_data_but_present_fields_stay_typed():
    validator = Draft202012Validator(S.view_schema('mesh'))
    partial = envelope('mesh', {})
    partial['skipped'] = [{'object': 'Mesh', 'section': 'mesh', 'reason': 'budget exceeded'}]
    validator.validate(partial)
    partial['data'] = {'counts': {'verts': 'eight'}}
    assert list(validator.iter_errors(partial))


def test_generator_check_catches_modified_missing_and_extra_artifacts(tmp_path):
    S.generate_schemas(tmp_path)
    assert S.generate_schemas(tmp_path, check=True) == []
    (tmp_path / 'mesh.schema.json').write_text('{}\n')
    (tmp_path / 'home.schema.json').unlink()
    (tmp_path / 'unexpected.schema.json').write_text('{}\n')
    assert S.generate_schemas(tmp_path, check=True) == [
        'home.schema.json', 'mesh.schema.json', 'unexpected.schema.json']
