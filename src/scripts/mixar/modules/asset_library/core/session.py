# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's one live session: the view-model, its pump over the server's ``/api/v1/library`` routes, the timer that ticks it on the main thread, and the thumbnail
previews. Panels read it; operators change it; nothing here runs in ``draw``."""

import time

import bpy

from .. import constants as K
from .pump import Pump
from .viewmodel import ThumbLRU, VaultViewModel

TICK_S = 0.1


class RestClient:
    """The view-model's two reads over the library client (the same door asset_place uses)."""

    def query(self, payload: dict) -> dict:
        from mixar.modules.lampway_tools import library_client as LC
        return LC.query(payload)

    def get(self, asset_id: str) -> dict:
        from mixar.modules.lampway_tools import library_client as LC
        return LC.get_asset(asset_id, include=("members",))

    def views(self, asset_id: str) -> dict:
        from mixar.modules.lampway_tools import library_client as LC
        return LC.views(asset_id)


VM = VaultViewModel(clock=time.monotonic)
PUMP = Pump(VM, RestClient())
THUMBS = ThumbLRU(K.THUMB_LRU)
BACKEND = {"location": "local"}          # where "find similar" runs; the server's status says otherwise when a remote route is in use
_previews = None


def vault_areas():
    wm = getattr(bpy.context, "window_manager", None)
    for win in getattr(wm, "windows", []) or []:
        for area in win.screen.areas:
            if area.type == K.SPACE:
                yield area


def _tick():
    try:
        if PUMP.tick() | VM.flipbook.advance():
            for area in vault_areas():
                area.tag_redraw()
    except Exception:  # noqa: BLE001 - a failing tick must never stop the timer
        pass
    return TICK_S


def ensure_running() -> None:
    """Start the pump's timer once; the first start also asks for the first page."""
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
        if VM.status == "idle":
            VM.submit()


def stop() -> None:
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def file_icon(path) -> int:
    """The preview icon id of an image file (a flipbook frame, a ball, a sheet, a lineage picture), kept in the same LRU; 0 when there is no file."""
    return thumb_icon({"id": f"file:{path}", "thumb": path}) if path else 0


def thumb_icon(item: dict) -> int:
    """The preview icon id of a tile's thumbnail file, loaded once and kept in the LRU; 0 = none (the panel shows the kind's icon instead)."""
    global _previews
    path = item.get("thumb")
    if not path:
        return 0
    if _previews is None:
        import bpy.utils.previews
        _previews = bpy.utils.previews.new()
    key = item["id"]
    icon = THUMBS.get(key)
    if icon is None:
        try:
            icon = _previews.load(key, path, "IMAGE").icon_id
        except (KeyError, RuntimeError):
            icon = _previews[key].icon_id
        for gone in THUMBS.put(key, icon):
            if gone in _previews:
                del _previews[gone]
    return icon
