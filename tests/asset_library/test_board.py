# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Boards as a free canvas (specs/asset_library/asset_ui_views.md section 5, "Boards"): tiles keep the place the user dragged them to (collection_item.x, y); a tile never
placed yet takes the next free grid cell; a click hits the topmost tile; a drag moves it by the pointer's travel and ends with the place to save. And two clips on one scrub
bar: the aligned frame pairs from the server play as one flipbook."""

from mixar.modules.asset_library.core import board as B
from mixar.modules.asset_library.core.viewmodel import VaultViewModel


def test_unplaced_tiles_fill_the_grid_and_placed_ones_stay():
    items = [{"id": "a", "x": None, "y": None, "ord": 0}, {"id": "b", "x": 500.0, "y": 20.0, "ord": 1}, {"id": "c", "x": None, "y": None, "ord": 2}]
    placed = {i["id"]: (i["x"], i["y"]) for i in B.place(items, tile=100, gap=10, cols=3)}
    assert placed["b"] == (500.0, 20.0)
    assert placed["a"] == (10.0, 10.0) and placed["c"] == (120.0, 10.0)
    assert B.extent(B.place(items, tile=100, gap=10, cols=3), tile=100, gap=10) == (610.0, 130.0)


def test_a_click_hits_the_topmost_tile():
    items = B.place([{"id": "a", "x": 0.0, "y": 0.0, "ord": 0}, {"id": "b", "x": 50.0, "y": 50.0, "ord": 1}], tile=100, gap=10, cols=3)
    assert B.hit(items, 60, 60, tile=100) == "b", "b is drawn after a: it is on top"
    assert B.hit(items, 20, 20, tile=100) == "a" and B.hit(items, 400, 400, tile=100) is None


def test_a_drag_moves_by_the_pointer_travel_and_ends_with_the_place_to_save():
    items = B.place([{"id": "a", "x": 40.0, "y": 40.0, "ord": 0}], tile=100, gap=10, cols=3)
    d = B.Drag(items, "a", 50, 60)
    d.move(150, 30)
    assert (items[0]["x"], items[0]["y"]) == (140.0, 10.0)
    d.move(-500, -500)
    assert (items[0]["x"], items[0]["y"]) == (0.0, 0.0), "a tile never leaves the board's top-left"
    assert d.end() == ("a", 0.0, 0.0)


def test_two_aligned_clips_play_as_one_flipbook():
    class Clock:
        t = 0.0

        def __call__(self):
            return self.t
    clock = Clock()
    vm = VaultViewModel(clock=clock)
    vm.load_pairs({"mode": "motion", "a": ["/a0", "/a1", "/a2"], "b": ["/b0", "/b1", "/b2"], "offset": {"a": 2, "b": 0}, "fps": 8})
    assert vm.align["mode"] == "motion" and vm.flipbook.path() == ("/a0", "/b0") and vm.view_mode == "compare"
    vm.flipbook.toggle()
    clock.t += 0.25
    vm.flipbook.advance()
    assert vm.flipbook.path() == ("/a2", "/b2")


def test_the_dragged_tile_comes_to_the_top():
    """Seen in the windowed board run: a tile dragged over its neighbour was drawn under it."""
    items = B.place([{"id": "a", "x": 0.0, "y": 0.0, "ord": 0}, {"id": "b", "x": 50.0, "y": 50.0, "ord": 1}], tile=100, gap=10, cols=3)
    B.Drag(items, "a", 10, 10)
    assert [i["id"] for i in items] == ["b", "a"] and B.hit(items, 60, 60, tile=100) == "a"
