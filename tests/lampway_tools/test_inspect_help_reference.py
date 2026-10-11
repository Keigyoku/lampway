# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Help must enumerate selectable list fields even for nested view schemas."""
from mixar.modules.lampway_tools.inspect import schema


def test_mesh_help_fields_include_holes_and_shells():
    fields = schema.reference_fields('mesh')
    assert set(fields['holes']) == set(schema.FIELDS['holes'])
    assert set(fields['shells']) == set(schema.FIELDS['shells'])


def test_scene_and_file_help_fields_disclose_optional_columns():
    assert {'clip_start', 'clip_end'} <= set(schema.reference_fields('scene')['cameras'])
    assert {'kind', 'name', 'path'} <= set(schema.reference_fields('file')['missing_files'])


def test_uv_help_layer_fields_use_uv_schema():
    assert schema.reference_fields('uv')['layers'] == ['name', 'active']


def test_deep_defect_rows_are_typed_and_discoverable():
    from jsonschema import Draft202012Validator
    fields = schema.reference_fields('mesh')
    assert {'id', 'kind', 'descriptor', 'severity'} <= set(fields['intersections'])
    validator = Draft202012Validator(schema.view_schema('mesh'))
    payload = {'view':'mesh','scene':'Scene','count':0,'total':0,'data':{
        'intersections':[{'id':'intersection-0','kind':'intersection','descriptor':{'faces':'many'}}]},
        'skipped':[], 'help':[]}
    assert list(validator.iter_errors(payload)), 'deep descriptor counts must be typed'
