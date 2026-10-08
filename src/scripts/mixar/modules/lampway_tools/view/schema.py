# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned Blender 5.2 editor identifiers accepted by the T2 screenshot contract.

Area.type aliases come from upstream/source/blender/makesrna/intern/rna_space.cc;
Area.ui_type expands image, graph, action, file and built-in node subtypes via
rna_screen.cc:rna_Area_ui_type_itemf. Source pin:
fbe6228777e7d9afefcd61a413844e790ae75db7. WINDOW requests the masked whole window.
Keep this pure module byte-identical to the server's mcp_view_schema.py.
"""

AREA_TYPES = (
    'VIEW_3D', 'IMAGE_EDITOR', 'UV', 'NODE_EDITOR',
    'ShaderNodeTree', 'CompositorNodeTree', 'TextureNodeTree', 'GeometryNodeTree',
    'SEQUENCE_EDITOR', 'CLIP_EDITOR', 'DOPESHEET_EDITOR', 'DOPESHEET', 'TIMELINE',
    'GRAPH_EDITOR', 'FCURVES', 'DRIVERS', 'NLA_EDITOR', 'TEXT_EDITOR', 'CONSOLE',
    'INFO', 'OUTLINER', 'PROPERTIES', 'FILE_BROWSER', 'FILES', 'ASSETS',
    'SPREADSHEET', 'PREFERENCES', 'WINDOW',
)
