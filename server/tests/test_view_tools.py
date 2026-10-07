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
