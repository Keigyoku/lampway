# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Content keys distinguish array boundaries and partial results never enter LRU."""
from types import SimpleNamespace

import numpy as np

from mixar.modules.lampway_tools.inspect import cache


class Collection:
    def __init__(self, count):
        self.count = count
    def __len__(self):
        return self.count
    def foreach_get(self, field, array):
        array[:] = 0


def object_with(vertices, edges, loops):
    return SimpleNamespace(name='Raw', matrix_world=np.eye(4), data=SimpleNamespace(
        name='RawMesh', vertices=Collection(vertices), edges=Collection(edges),
        loops=Collection(loops), polygons=Collection(0),
        uv_layers=SimpleNamespace(active_index=-1)))


class NoUV:
    active_index = -1
    def __iter__(self):
        return iter(())


def test_cache_frames_array_lengths_not_just_concatenated_bytes():
    # Removing a zero vertex and replacing its 12 bytes with zero loops must
    # change the key even though the concatenated raw bytes are identical.
    a = object_with(1, 0, 0)
    b = object_with(0, 0, 3)
    a.data.uv_layers = b.data.uv_layers = NoUV()
    assert cache.key(a, False, 1, []) != cache.key(b, False, 1, [])


def test_partial_sections_are_not_cached():
    cache._ENTRIES.clear()
    calls = []
    def compute():
        calls.append(1)
        return {'holes': [], 'skipped': [{'section': 'mesh', 'reason': 'budget_ms exceeded'}]}
    cache.get_or_compute(('raw',), compute)
    cache.get_or_compute(('raw',), compute)
    assert len(calls) == 2
    assert not cache._ENTRIES


def test_cache_results_are_copies_and_lru_is_bounded():
    cache._ENTRIES.clear()
    for index in range(65):
        cache.get_or_compute((index,), lambda: {'holes': []})
    assert len(cache._ENTRIES) == 64 and (0,) not in cache._ENTRIES
    result = cache.get_or_compute((64,), lambda: None)
    result['holes'].append({'id': 1})
    assert cache.get_or_compute((64,), lambda: None)['holes'] == []
    cache._ENTRIES.clear()
