# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T2's single API door and complete bounded input schema."""
from lampway_server.agent.view_tools import DEFS


def test_view_definition_and_closed_schema():
    assert len(DEFS) == 1
    tool = DEFS[0]
    assert tool.name == 'lampway_view' and tool.api == 'view'
    schema = tool.spec().parameters
    assert schema['additionalProperties'] is False
    assert set(schema['properties']) == {'action', 'object', 'data', 'unhide', 'area', 'shot', 'max_bytes', 'preset', 'out'}
    assert schema['properties']['max_bytes']['minimum'] == 50000
    assert schema['properties']['max_bytes']['maximum'] == 900000
    assert schema['properties']['preset']['enum'] == ['current', 'thumbnail']


def test_area_values_are_closed_before_blender_execution():
    from lampway_server import mcp_envelope
    schema = DEFS[0].spec().parameters
    values = schema['properties']['area'].get('enum', [])
    assert {'VIEW_3D', 'IMAGE_EDITOR', 'UV', 'ShaderNodeTree', 'GeometryNodeTree',
            'CompositorNodeTree', 'TextureNodeTree', 'WINDOW', 'FCURVES',
            'DRIVERS', 'DOPESHEET', 'TIMELINE', 'FILES', 'ASSETS'} <= set(values)
    for area in values:
        assert mcp_envelope.argument_error('lampway_view', {'area': area}, schema) is None
    invalid = mcp_envelope.argument_error('lampway_view', {'area': 'INVENTED_EDITOR'}, schema)
    assert invalid and invalid['code'] == 'bad_argument'
