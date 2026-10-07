# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory-only 64-entry LRU; all geometry, UV, material and world-array inputs participate."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import struct
import numpy as np

_ENTRIES = OrderedDict()


def key(ob, evaluated, scale, options, budget=None):
    if budget:
        budget.admit_geometry(ob.data)
    check = budget.check if budget else lambda: None
    mesh = ob.data
    digest = hashlib.sha1()
    for collection, field, width, dtype in ((mesh.vertices, 'co', 3, np.float32),
                                           (mesh.edges, 'vertices', 2, np.int32),
                                           (mesh.loops, 'vertex_index', 1, np.int32),
                                           (mesh.polygons, 'material_index', 1, np.int32),
                                           (mesh.polygons, 'loop_total', 1, np.int32),
                                           (mesh.polygons, 'loop_start', 1, np.int32),
                                           (mesh.edges, 'use_seam', 1, np.bool_)):
        check()
        digest.update(field.encode() + b'\0')
        digest.update(struct.pack('<QQ', len(collection), width))
        array = np.empty(len(collection) * width, dtype=dtype)
        collection.foreach_get(field, array)
        _update_array(digest, array, check)
    for layer in mesh.uv_layers:
        name = layer.name.encode()
        digest.update(struct.pack('<QQ', len(name), len(layer.data)))
        digest.update(name)
        check()
        array = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get('uv', array)
        _update_array(digest, array, check)
    check()
    digest.update(str(mesh.uv_layers.active_index).encode())
    digest.update(np.asarray(ob.matrix_world, dtype=np.float64).tobytes())
    return ob.name, mesh.name, evaluated, scale, digest.hexdigest(), tuple(options)


def _update_array(digest, array, check):
    """Bound each hashing step without allocating a second full array copy."""
    raw = memoryview(array).cast('B')
    for offset in range(0, len(raw), 262144):
        check()
        digest.update(raw[offset:offset + 262144])
    check()


def get_or_compute(cache_key, compute, budget=None):
    check = budget.check if budget else lambda: None
    check()
    if cache_key in _ENTRIES:
        _ENTRIES.move_to_end(cache_key)
        value = deepcopy(_ENTRIES[cache_key])
        check()
        return value
    value = compute()
    check()
    # Partial deadline results must never become a successful warm-cache result.
    if value.get("skipped"):
        return value
    stored = deepcopy(value)
    check()
    _ENTRIES[cache_key] = stored
    while len(_ENTRIES) > 64:
        _ENTRIES.popitem(last=False)
    return value
