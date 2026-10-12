# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One bounded read-only inspection tool, with views instead of extra tools."""
from copy import deepcopy
from .tool_defs import Def, P
from ..mcp_inspect_schema import INPUT_SCHEMA


class InspectDef(Def):
    def spec(self):
        spec = super().spec()
        spec.parameters = deepcopy(INPUT_SCHEMA)
        return spec


DEFS = [InspectDef('lampway_inspect',
    'Read the open scene as typed data; never edits it. No arguments returns the dashboard. '
    'Views: scene, objects, object, mesh, uv, parts, layers, relations, file. '
    'Use view=help name=<view> for fields, bounds and refusals or view=schema name=<view> for its schema. '
    'Reads raw imports and reports their canon state (OBSERVE); no normalization is required. '
    'Measurements use world space, metres and the existing canon 01/13 algorithms. '
    'Unknown arguments and fields are refused; lists are paged with limit and offset.',
    [P(name, prop['type'], desc=prop['description']) for name, prop in INPUT_SCHEMA['properties'].items()], api='inspect')]
