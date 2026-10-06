# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault's pan/zoom canvas: the screen <-> image mapping that the gpu draw handler (to place the picture) and the modal operator (wheel zoom, middle-drag pan, click
to select) share. Pure Python.

Screen coordinates are the region's (origin bottom-left, y up). Image coordinates are pixels with the origin top-left (y down), the convention of the lineage layout's
node rects, so a click goes straight into ``views.hit_test``."""

ZOOM_MIN, ZOOM_MAX = 0.05, 16.0


class Canvas:
    def __init__(self, view=(0, 0, 1, 1), image=(1, 1)):
        self.view = tuple(float(v) for v in view)          # x0, y0, x1, y1 of the canvas inside the region
        self.image = (max(1.0, float(image[0])), max(1.0, float(image[1])))
        self.zoom, self.fit_zoom = 1.0, 1.0
        self.ox, self.oy = self.view[0], self.view[1]       # screen position of the image's bottom-left corner

    def set_view(self, view) -> None:
        self.view = tuple(float(v) for v in view)

    def fit(self) -> None:
        x0, y0, x1, y1 = self.view
        w, h = self.image
        self.fit_zoom = self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, min((x1 - x0) / w, (y1 - y0) / h)))
        self.ox = x0 + ((x1 - x0) - w * self.zoom) / 2
        self.oy = y0 + ((y1 - y0) - h * self.zoom) / 2

    def quad(self) -> tuple:
        w, h = self.image
        return (self.ox, self.oy, self.ox + w * self.zoom, self.oy + h * self.zoom)

    def to_image(self, sx: float, sy: float) -> tuple:
        w, h = self.image
        return ((sx - self.ox) / self.zoom, h - (sy - self.oy) / self.zoom)

    def zoom_at(self, factor: float, sx: float, sy: float) -> None:
        ix, iy = self.to_image(sx, sy)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        h = self.image[1]
        self.ox = sx - ix * self.zoom
        self.oy = sy - (h - iy) * self.zoom

    def pan(self, dx: float, dy: float) -> None:
        self.ox += dx
        self.oy += dy

    def inside(self, sx: float, sy: float) -> bool:
        x0, y0, x1, y1 = self.view
        return x0 <= sx <= x1 and y0 <= sy <= y1
