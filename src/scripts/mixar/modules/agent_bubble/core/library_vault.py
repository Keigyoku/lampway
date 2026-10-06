# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault in the island's Library tab (specs/asset_library/asset_ui_editor.md surface C).

The pane paints ``WindowManager.mixar_generations_files`` rows; ``library_media.refresh`` writes them from the connected folders and appends :func:`rows`, the Vault's
pictures and clips under the library name "Asset Vault". The rows come from ONE query, the Vault editor's own payload (``asset_library.core.session.VM.payload()``), so the
quick path in the bubble and the full editor show the same assets. The query runs off the main thread through the editor's pump, at most every :data:`INTERVAL` seconds.

The pane's tiles are pictures and videos only (its C++ has no mesh tile), so meshes, materials and the rest stay in the Vault editor; a row needs a file on disk."""

import os
import time

LIBRARY = "Asset Vault"
INTERVAL = 10.0
KINDS = {"image": "IMAGE", "hdri": "IMAGE", "map": "IMAGE", "video": "VIDEO"}

_rows: list = []
_state = {"at": None, "busy": False}


def page_rows(page: dict) -> list:
    """``[(library, path, kind, mtime, name)]`` for the tiles the pane can show (the tile shows the asset's name, not the file's)."""
    out = []
    for it in page.get("items") or []:
        kind = KINDS.get(it.get("kind"))
        path = it.get("path")
        if kind and path:
            out.append((LIBRARY, path, kind, 0, it.get("name") or os.path.basename(path)))
    return out


def rows() -> list:
    return list(_rows)


def _landed(ok, value) -> None:
    global _rows
    _state["busy"] = False
    if ok:
        _rows = page_rows(value)


def poll(force: bool = False) -> bool:
    """Land a finished answer, then ask the server for the current page when due; True when a request went out. Called from the island's own pump, so the Vault editor's
    timer is not started (and the editor's first page is not asked for) just because the island is open."""
    from mixar.modules.asset_library.core import session as SES
    from mixar.modules.lampway_tools import library_client as LC
    SES.PUMP.tick()
    now = time.monotonic()
    if _state["busy"] or (not force and _state["at"] is not None and now - _state["at"] < INTERVAL):
        return False
    payload = SES.VM.payload()
    _state.update(at=now, busy=True)
    SES.PUMP.later(lambda: LC.query(payload), _landed)
    return True
