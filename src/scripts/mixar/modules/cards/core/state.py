# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The cards list as Blender sees it: a cache the panel draws (``CACHE``), and the pump that runs every server call off the main thread and lands its answer on a timer
tick. Opening a card hands its URL (on the cards' own local origin) to the browser: Blender never renders a report's HTML."""

import queue
import threading

CACHE = {"cards": [], "status": "idle", "message": ""}


def _thread(fn):
    threading.Thread(target=fn, name="lampway-cards", daemon=True).start()


class Later:
    def __init__(self, spawn=_thread):
        self.spawn = spawn
        self._done: queue.Queue = queue.Queue()

    def later(self, fn, on_result) -> None:
        def job():
            try:
                self._done.put((on_result, True, fn()))
            except Exception as exc:  # noqa: BLE001 - the panel shows the message
                self._done.put((on_result, False, str(exc)))
        self.spawn(job)

    def tick(self) -> bool:
        landed = False
        while True:
            try:
                cb, ok, value = self._done.get_nowait()
            except queue.Empty:
                return landed
            cb(ok, value)
            landed = True


PUMP = Later()


def request(method: str, path: str, body=None):
    from mixar.modules.lampway_tools import library_client as LC
    return LC._data(LC._request(method, path, body))


def refreshed(ok, value) -> None:
    if ok:
        CACHE.update(cards=list(value.get("cards") or []), status="ready", message="")
    else:
        CACHE.update(status="offline", message=str(value))


def refresh() -> None:
    CACHE["status"] = "loading"
    PUMP.later(lambda: request("GET", "/app/cards?status=all"), refreshed)


def _tick():
    import bpy
    try:
        if PUMP.tick():
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == "MIXAR_ASSETS":
                        area.tag_redraw()
    except Exception:  # noqa: BLE001
        pass
    from .. import constants as K
    return K.TICK_S


def ensure_running() -> None:
    import bpy
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
