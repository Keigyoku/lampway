# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory-only 64-entry LRU; all geometry, UV, material and world-array inputs participate."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import numpy as np

_ENTRIES = OrderedDict()


def key(ob, evaluated, scale, options):
    mesh = ob.data
    digest = hashlib.sha1()
    for collection, field, width, dtype in ((mesh.vertices, 'co', 3, np.float32),
                                           (mesh.edges, 'vertices', 2, np.int32),
                                           (mesh.loops, 'vertex_index', 1, np.int32),
                                           (mesh.polygons, 'material_index', 1, np.int32),
                                           (mesh.polygons, 'loop_total', 1, np.int32),
                                           (mesh.edges, 'use_seam', 1, np.bool_)):
        array = np.empty(len(collection) * width, dtype=dtype)
        collection.foreach_get(field, array)
        digest.update(array.tobytes())
    for layer in mesh.uv_layers:
        digest.update(layer.name.encode())
        array = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get('uv', array)
        digest.update(array.tobytes())
    digest.update(str(mesh.uv_layers.active_index).encode())
    digest.update(np.asarray(ob.matrix_world, dtype=np.float64).tobytes())
    return ob.name, mesh.name, evaluated, scale, digest.hexdigest(), tuple(options)


def get_or_compute(cache_key, compute):
    if cache_key in _ENTRIES:
        _ENTRIES.move_to_end(cache_key)
        return deepcopy(_ENTRIES[cache_key])
    value = compute()
    _ENTRIES[cache_key] = deepcopy(value)
    while len(_ENTRIES) > 64:
        _ENTRIES.popitem(last=False)
    return value
