# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""L0 triangle totals use one RNA bulk read, preserving n-gon arithmetic."""
from mixar.modules.lampway_tools.inspect import home


class Polygons:
    def __len__(self): return 3
    def __iter__(self): raise AssertionError('dashboard must not visit every polygon through Python RNA')
    def foreach_get(self, field, output):
        raise AssertionError('L0 must be O(objects), not O(polygons)')


class Mesh:
    polygons = Polygons()
    # Three valid Blender polygons with 3, 4 and 9 loops: (3-2)+(4-2)+(9-2).
    loops = range(16)


def test_exact_bulk_triangle_count():
    assert home.triangle_count(Mesh()) == 10
