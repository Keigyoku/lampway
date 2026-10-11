# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record derivative ancestry using the acceptance engine's existing geometry identity."""


def stamp_source(output, source):
    # Local import avoids workflows -> rig -> weights -> workflows at module load.
    from .workflows import mesh_hash
    parent_hash = mesh_hash(source)
    output['lw_source'] = str(source.get('lw_source') or source.name)
    output['lw_source_hash'] = str(source.get('lw_source_hash') or parent_hash)
    output['lw_parent'] = source.name
    output['lw_parent_hash'] = parent_hash
    return output['lw_source_hash']
