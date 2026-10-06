# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chat LIBRARY mode on the Asset Vault (specs/asset_library/asset_ui_editor.md surface D).

Browsing (an empty send, switching into the mode) and a typed search ask the Vault's query (``POST /api/v1/library/query``) on a worker thread; a token drops an answer
that a newer request superseded; the main-thread poll fills the one library bubble. No .blend is opened to list or search. A tile's identity is ``library="Asset Vault"``,
``blend_file="vault:<asset id>"``; a click places it with ``lampway_tools.api.asset_place`` (one undo step, the kind's own way). A picture is its own thumbnail; other kinds
show as text rows until the Vault renders thumbnails (asset_render)."""

import hashlib
import threading

import bpy

from mixar.config.logging_config import get_logger

logger = get_logger(__name__)

LIBRARY = "Asset Vault"
PREFIX = "vault:"
PICTURES = ("image", "hdri", "map")

_lock = threading.Lock()
_token = 0
_result = None              # (token, query, ok, value)


def SPAWN(fn):              # replaced by tests: run the worker inline
    threading.Thread(target=fn, name="lampway-chat-vault", daemon=True).start()


def payload(query: str, limit: int) -> dict:
    p = {"limit": int(limit), "include": ["thumb", "tags", "path"]}
    return {"text": query, **p} if query else p


def _publish(token, query, ok, value) -> None:
    global _result
    with _lock:
        if token == _token:
            _result = (token, query, ok, value)


def start(context, query: str = "") -> None:
    """Ask the Vault (browse when ``query`` is empty) and show a searching state."""
    global _token
    from . import library_browse as LB
    _token += 1
    token, body = _token, payload(query, LB._MAX_GRID)
    msg = LB._grid_bubble(context.scene)
    LB._cleanup_bubble(msg)
    msg.action_items.clear()
    LB._set_content(msg, f"Searching the Asset Vault for “{query}”…" if query else "Reading the Asset Vault…")
    LB._redraw()

    def work():
        from mixar.modules.lampway_tools import library_client as LC
        try:
            _publish(token, query, True, LC.query(body))
        except Exception as exc:  # noqa: BLE001 - the poll words it
            _publish(token, query, False, str(exc))
    SPAWN(work)
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.2)


def _image_for(item: dict) -> str:
    """A picture's own file as the row's thumbnail image (named like the picker's, so its cleanup frees it)."""
    from . import asset_choice_previews as ACP
    path = item.get("thumb")
    if not path:
        return ""
    name = ACP.IMAGE_PREFIX + hashlib.sha1(f"{LIBRARY}|{item['id']}".encode()).hexdigest()[:16]
    if bpy.data.images.get(name) is None:
        try:
            img = bpy.data.images.load(path, check_existing=False)
        except RuntimeError:
            return ""
        img.name = name
    return name


def apply(context, query: str, page: dict) -> None:
    from . import library_browse as LB
    scene = context.scene
    msg = LB._grid_bubble(scene)
    LB._cleanup_bubble(msg)
    msg.action_items.clear()
    items = (page.get("items") or [])[:LB._MAX_GRID]
    total = int(page.get("total") or len(items))
    head = f"**{total}** asset(s) matching “{query}”" if query else f"**The Asset Vault** — {total} asset(s)"
    if not items:
        LB._set_content(msg, head + "\n\n" + ("No matches — try a different search." if query else (page.get("note") or "The Vault is empty: Initial import adds your folders.")))
        LB._redraw()
        return
    more = f" · showing the first {len(items)}, refine your search" if total > len(items) else ""
    LB._set_content(msg, head + more + "\n\nClick an asset to put it in the scene.")
    for i, it in enumerate(items):
        action = msg.action_items.add()
        action.label = it["name"]
        action.value = f"{LB.LIB_ADD_PREFIX}{i}"
        action.style = "DEFAULT"
        action.asset_name = it["name"]
        action.library = LIBRARY
        action.blend_file = PREFIX + it["id"]
        action.asset_type = it["kind"]
        action.image = _image_for(it) if it.get("kind") in PICTURES else ""
    scene.mixie_chat_user_has_engaged = True
    LB._redraw()


def _poll():
    global _result
    with _lock:
        result, _result = _result, None
    if result is None:
        return 0.2
    token, query, ok, value = result
    context = bpy.context
    scene = getattr(context, "scene", None)
    if token != _token or scene is None or getattr(scene, "mixie_chat_mode", "") != "LIBRARY":
        return None
    if ok:
        apply(context, query, value)
    else:
        from . import library_browse as LB
        msg = LB._grid_bubble(scene)
        LB._cleanup_bubble(msg)
        msg.action_items.clear()
        LB._set_content(msg, f"**The Asset Vault is not reachable** ({value}).\n\nStart the Lampway server and sign in, then send again.")
        LB._redraw()
    return None


def place(context, blend_file: str) -> tuple:
    """(ok, message) for a clicked Vault tile."""
    from mixar.modules.lampway_tools import api
    res = api.asset_place(asset_id=blend_file[len(PREFIX):])
    if not res.get("ok"):
        return False, f"{res.get('error')} ({'; '.join(res.get('help') or [])})"
    return True, ", ".join(p["name"] for p in res["placed"] if p.get("name"))
