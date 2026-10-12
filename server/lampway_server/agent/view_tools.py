# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T2: one bound-scene Blender API call, offered automatically over MCP."""
from .tool_defs import Def, P
from ..mcp_view_schema import AREA_TYPES

class ViewDef(Def):
    def spec(self):
        spec = super().spec()
        props = spec.parameters['properties']
        props['action'].update(enum=['focus', 'screenshot', 'render_still', 'help'])
        props['unhide'].update(default=False)
        props['area'].update(enum=list(AREA_TYPES), default='VIEW_3D')
        props['shot'].update(default=True)
        props['max_bytes'].update(minimum=50000, maximum=900000, default=750000)
        props['preset'].update(enum=['current', 'thumbnail'], default='current')
        props['out'].update(default='renders/still.png')
        return spec


DEFS = [ViewDef('lampway_view',
    'Frame a named object, capture a masked editor or start a still render. Pixels require the UI-control opt-in. '
    'Uses the session-bound window scene, restores selection and render settings, and never overwrites an output. '
    'A hidden target needs unhide=true (one undo step); a busy renderer refuses. No spend or runtime egress.',
    [P('action', desc='focus | screenshot | render_still | help; omitted: live editors, camera and last capture'),
     P('object', desc='focus: exactly one of object/data'), P('data', desc='focus: data-block name with one scene user'),
     P('unhide', 'boolean', 'default false; one undo step when needed'),
     P('area', desc='editor UI type or WINDOW; default VIEW_3D'), P('shot', 'boolean', 'focus returns image; default true'),
     P('max_bytes', 'integer', '50000..900000; default 750000'),
     P('preset', desc='current | thumbnail; default current'),
     P('out', desc='project-relative PNG; default renders/still.png; exclusive numbered output')], api='view')]
