# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Progress of one render or verify: a long render must not look like a hung one (bug 10 of issue #8).

The contract: ``report(phase, done, total)`` after every frame of a phase (``render``, then ``probe``; verify's re-render is ``render``)
calls ``emit({phase, frame, frames, elapsed_s, eta_s})`` on its first and last frame and at most once per ``every`` seconds between. The
ETA is the phase's own (frames left at its mean pace since its first frame). ``phases`` is the closed record: {phase, frames, seconds} per phase,
which the tool's answer carries. Wall-clock only: nothing here reaches a frame, a hash or the receipt. ``emit`` runs on the render thread
and must not block; an exception from it is the caller's bug and stops the render like any other."""
import time

EVERY_S = 5.0


class Progress:
    def __init__(self, emit=None, every: float = EVERY_S, clock=time.monotonic):
        self.emit, self.every, self.clock = emit, every, clock
        self.phases, self._phase, self._t0, self._last = [], None, 0.0, None

    def report(self, phase: str, done: int, total: int) -> None:
        now = self.clock()
        if phase != self._phase:
            self._phase, self._t0, self._last = phase, now, None
            self.phases.append({"phase": phase, "frames": 0, "seconds": 0.0})
        elapsed = now - self._t0
        self.phases[-1].update(frames=done, seconds=round(elapsed, 3))
        if self.emit is None:
            return
        if done in (1, total) or self._last is None or now - self._last >= self.every:
            self._last = now
            eta = elapsed / done * (total - done) if done else None
            self.emit({"phase": phase, "frame": done, "frames": total, "elapsed_s": round(elapsed, 1),
                       "eta_s": round(eta, 1) if eta is not None else None})
