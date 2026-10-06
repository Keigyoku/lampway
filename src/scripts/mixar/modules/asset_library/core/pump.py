# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's pump (specs/asset_library/asset_ui_editor.md section 6.3): every HTTP call runs in a worker thread; its answer waits in a queue until the main thread's
tick, the only place the view-model changes. ``tick`` returns True when something landed (the caller redraws the Vault areas). No bpy here: ``spawn`` and the client are
handed in, so the rules are tested without Blender."""

import queue
import threading


def _thread(fn) -> None:
    threading.Thread(target=fn, name="lampway-vault", daemon=True).start()


class Pump:
    def __init__(self, vm, client, spawn=_thread):
        self.vm, self.client, self.spawn = vm, client, spawn
        self._done: queue.Queue = queue.Queue()

    def _run(self, kind, key, fn, *args) -> None:
        def job():
            try:
                self._done.put((kind, key, True, fn(*args)))
            except Exception as exc:  # noqa: BLE001 - any failure reaches the view-model as a message, never a traceback in the UI
                self._done.put((kind, key, False, str(exc)))
        self.spawn(job)

    def later(self, fn, on_result) -> None:
        """An operator's call (rate, find similar, add to a board): ``fn`` runs off the main thread, ``on_result(ok, value)`` on the next tick."""
        self._run("later", on_result, fn)

    def tick(self) -> bool:
        landed = False
        while True:
            try:
                kind, key, ok, value = self._done.get_nowait()
            except queue.Empty:
                break
            if kind == "query":
                landed |= self.vm.receive(key, value) if ok else self.vm.fail(key, value)
            elif kind == "detail" and ok:
                landed |= self.vm.receive_detail(key, value)
            elif kind == "views" and ok:
                landed |= self.vm.receive_views(key, value)
            elif kind == "later":
                key(ok, value)
                landed = True
        req = self.vm.due()
        if req:
            self._run("query", req["token"], self.client.query, req["payload"])
        aid = self.vm.detail_due()
        if aid:
            self._run("detail", aid, self.client.get, aid)
            if hasattr(self.client, "views"):
                self._run("views", aid, self.client.views, aid)
        return landed
