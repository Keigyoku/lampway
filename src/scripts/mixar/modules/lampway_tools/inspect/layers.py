# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the existing paint package's stack; absence is a definitive empty state."""
from ..features import layered_material as LM


def measure(ob):
    if LM._mp(ob) is None:
        return {'object': ob.name, 'layers': []}
    output = LM.layered_material(action='inspect', object=ob.name)
    return {'object': ob.name, 'layers': output['stack'], 'material': output['material'],
            'active_layer_index': output['active_layer_index']}
