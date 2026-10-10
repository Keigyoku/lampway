# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The second adapter at the motion-graphics capture seam (specs/motion_graphics/motion_graphics.md section 2): synthetic PNG frames, no browser, so encode, the
receipt and the self-check are tested on their own. Each frame is a pure function of t: a ramp, a bar that moves and seeded noise."""
import io

import numpy as np
from PIL import Image


class FakeCapture:
    product = "FakeChrome/1.0"
    flags = ["--fake-capture"]

    def __init__(self, duration_s=1.0, requests=(), audit=None, animations=0, has_frame=True, setup=None, size=None):
        self.duration_s, self._requests, self._audit = duration_s, list(requests), audit
        self._animations, self._has_frame, self._setup, self._size = animations, has_frame, setup, size
        self.opened = self.closed = False
        self.frames_asked = []

    def open(self, entry, width, height):
        self.entry, self.width, self.height, self.opened = entry, width, height, True

    def has_frame(self):
        return self._has_frame

    def setup(self):
        return self._setup or {"fonts": [], "images": []}

    def scene(self):
        return {"duration_s": self.duration_s, "width": self.width, "height": self.height}

    def animations(self):
        return self._animations

    def frame(self, t):
        self.frames_asked.append(t)
        w, h = self._size or (self.width, self.height)
        x = np.linspace(0, 1, w, dtype=np.float32)[None, :].repeat(h, 0)
        a = np.zeros((h, w, 3), dtype=np.float32)
        a[..., 0], a[..., 2] = 60 + 120 * x * t, 40 + 80 * (1 - x)
        a += np.random.default_rng(int(round(t * 1000))).normal(0, 12, a.shape)
        bx = int(w * 0.1 + w * 0.6 * t)
        a[h // 2: h // 2 + max(2, h // 12), bx: bx + max(4, w // 10)] = 235
        buf = io.BytesIO()
        Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(buf, "PNG")
        return buf.getvalue()

    def audit(self):
        return self._audit or {"text": [], "marks": []}

    def requests(self):
        return list(self._requests)

    def close(self):
        self.closed = True
