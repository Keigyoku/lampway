# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Boards as a free canvas (specs/asset_library/asset_ui_views.md section 5): tile places in board pixels (origin top-left, the canvas's image space), the grid cell a
never-placed tile takes, the topmost tile under a click, and a drag that ends with the place to save. Pure Python."""


def place(items: list, tile: float = 128, gap: float = 16, cols: int = 6) -> list:
    """The items with x, y filled: a tile the user placed keeps its place; the others take grid cells in their board order."""
    out, k = [], 0
    for it in sorted(items, key=lambda i: (i.get("ord") or 0)):
        it = dict(it)
        if it.get("x") is None or it.get("y") is None:
            it["x"], it["y"] = float(gap + (k % cols) * (tile + gap)), float(gap + (k // cols) * (tile + gap))
            k += 1
        out.append(it)
    return out


def extent(items: list, tile: float = 128, gap: float = 16) -> tuple:
    if not items:
        return (float(tile + 2 * gap), float(tile + 2 * gap))
    return (max(i["x"] for i in items) + tile + gap, max(i["y"] for i in items) + tile + gap)


def hit(items: list, ix: float, iy: float, tile: float = 128):
    for it in reversed(items):                       # drawn in order: the last one is on top
        if it["x"] <= ix < it["x"] + tile and it["y"] <= iy < it["y"] + tile:
            return it["id"]
    return None


class Drag:
    def __init__(self, items: list, asset_id: str, ix: float, iy: float):
        self.item = next(i for i in items if i["id"] == asset_id)
        items.remove(self.item)
        items.append(self.item)                      # the tile in hand is drawn last: on top
        self.dx, self.dy = ix - self.item["x"], iy - self.item["y"]

    def move(self, ix: float, iy: float) -> None:
        self.item["x"], self.item["y"] = max(0.0, float(round(ix - self.dx))), max(0.0, float(round(iy - self.dy)))      # whole board pixels

    def end(self) -> tuple:
        return (self.item["id"], self.item["x"], self.item["y"])
