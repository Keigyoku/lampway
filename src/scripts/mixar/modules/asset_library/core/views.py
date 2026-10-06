# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault's inspection views on the client (specs/asset_library/asset_ui_views.md): the flipbook clock for turntables and video proxies, and the words each view shows.
Pure Python: the panels and the canvas draw what these return. The heavy products (turntable frames, the ball, overlays, the maps sheet, proxy frames) are rendered by the
server's workers (asset_render, asset_video); a view whose product is missing says so and names who makes it."""

MODES = ("preview", "uv", "maps", "lineage", "compare", "video")
FPS_MIN, FPS_MAX, FPS_DEFAULT = 6, 24, 12
DUP_GATE = 0.1                     # [UNVERIFIED] the duplicate-frame ratio above which the chip shows; asset_video's gate owns the real number

PRODUCT = {"preview": ("turntable", "no turntable yet: queued (asset_render)"), "uv": ("overlay", "no UV overlay yet: queued (asset_render)"),
           "maps": ("sheet", "no maps sheet yet: queued (asset_render)"), "video": ("proxy", "no proxy frames yet: queued (asset_video)")}


class Flipbook:
    """A list of frame paths played at ``fps`` (6..24) by the editor's timer; the frame is computed from the clock, so a slow redraw never slows the playback."""

    def __init__(self, clock):
        self.clock = clock
        self.frames: list = []
        self.fps = FPS_DEFAULT
        self.playing = False
        self.frame = 0
        self._t0, self._f0 = clock(), 0

    def load(self, frames, fps=FPS_DEFAULT) -> None:
        self.frames, self.frame, self.playing = list(frames), 0, False
        self.set_fps(fps)

    def _anchor(self) -> None:
        self._t0, self._f0 = self.clock(), self.frame

    def set_fps(self, fps) -> None:
        self.advance()
        self.fps = max(FPS_MIN, min(FPS_MAX, int(fps)))
        self._anchor()

    def toggle(self) -> None:
        self.advance()
        self.playing = not self.playing
        self._anchor()

    def scrub(self, frame: int) -> None:
        self.frame = max(0, min(len(self.frames) - 1, int(frame))) if self.frames else 0
        self._anchor()

    def advance(self) -> bool:
        if not self.playing or not self.frames:
            return False
        new = (self._f0 + int((self.clock() - self._t0) * self.fps)) % len(self.frames)
        changed, self.frame = new != self.frame, new
        return changed

    def path(self):
        return self.frames[self.frame] if self.frames else None


def view_status(mode: str, record: dict, products: dict):
    """None when the view can show something, else the sentence that says what is missing and who makes it."""
    if mode not in PRODUCT:
        return None
    key, missing = PRODUCT[mode]
    return None if products.get(key) else missing


def compare_refusal(records: list):
    if len(records) < 2:
        return ("compare needs two assets of the same kind: press Compare on two" if not records else
                f"compare needs two assets of the same kind: press Compare on a second {records[0]['kind']}")
    a, b = records[-2:]
    if a["kind"] != b["kind"]:
        return f"compare needs two assets of the same kind: {a['kind']} and {b['kind']} differ"
    return None


def dup_chip(stats: dict, gate: float = DUP_GATE):
    if (stats.get("dup_ratio") or 0) > gate:
        return {"text": f"{int(stats.get('dup_frames') or 0)} duplicate frames", "colour": "stop", "glyph": "cross"}
    return None


def fps_badge(stats: dict) -> str:
    def g(v):
        return f"{float(v):g}"
    motion = f"{g(stats['motion_fps'])} fps motion" if stats.get("motion_fps") else "motion not measured"
    return f"{g(stats.get('container_fps') or 0)} fps file, {motion}"


def normal_stamp(record: dict):
    sub = str(record.get("subtype") or "")
    conv = str((record.get("stats") or {}).get("convention") or (record.get("stats") or {}).get("normal_convention") or "").lower()
    if sub in ("normal_dx", "normal_gl"):                         # a map's subtype is the convention it was filed under
        conv = sub[-2:]
    elif record.get("kind") != "image":
        return None                                               # only a normal map, or an image the extractor measured as one, has a convention
    return {"dx": "DX (green down)", "gl": "GL (green up)"}.get(conv)
