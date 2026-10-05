# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Start the live bridge with the app (a bootstrap module: ``register()`` runs at launch).

Windowed launches always start it (port ``LAMPWAY_BRIDGE_PORT`` / ``BLENDER_MCP_PORT`` / 9876, ``0`` = off);
a headless (``-b``) run starts it only when a port is set explicitly, so batch jobs never take the port a
live window is listening on. ``LAMPWAY_BRIDGE_DIR`` turns on the file door (inbox/, outbox/, frames/).
"""

import os
from pathlib import Path

import bpy

from mixar.config.logging_config import get_logger
from mixar.modules.lampway_tools import bridge

logger = get_logger(__name__)

_bridge = None
_POLL_S = 0.1


def get_bridge():
    return _bridge


def _tick():
    b = _bridge
    if b is None or not b.enabled:
        return None
    try:
        b.pump()
        b.poll_inbox()
    except Exception:
        logger.exception("bridge tick failed")
    return _POLL_S


def register():
    global _bridge
    if bpy.app.background and not bridge.explicitly_configured():
        logger.debug("bridge: headless run without an explicit port; not listening")
        return
    root = os.environ.get("LAMPWAY_BRIDGE_DIR")
    dirs = {}
    if root:
        base = Path(root)
        dirs = {"inbox": base / "inbox", "outbox": base / "outbox", "frames": base / "frames"}
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
    b = bridge.Bridge(port=bridge.port_from_env(), **dirs)
    if b.start():
        _bridge = b
        bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)
        logger.info("Lampway bridge listening on 127.0.0.1:%s", b.port)
    else:
        logger.warning("Lampway bridge not started: %s", b.error)


def unregister():
    global _bridge
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _bridge is not None:
        _bridge.stop()
        _bridge = None
