# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Connections: the one place that knows every credential Lampway can use (specs/connections/CONNECTIONS.md).

The consumer interface, the whole of it:

    cred = connections.require("openrouter")       # -> Credential, or raises NotConnected with the fixed text
    cred.headers()                                  # {"Authorization": "Bearer ..."} in the service's own scheme
    cred.env()                                      # {"OPENROUTER_API_KEY": "..."} for exactly one child process
    connections.env_for(["studio:meshy"])           # a child's whole environment: scrubbed, plus those connections only
    connections.report_use("openrouter", ok=False, status=401)

The server sets the active hub (``set_active``); any other process (the compute CLI, a studio driver) gets one built from its
environment on first use."""

import os
from pathlib import Path
from typing import Optional

from .errors import NotConnected, Refused
from .hub import Hub
from .registry import register_use
from .sources import Credential, secret_of

__all__ = ["Credential", "Hub", "NotConnected", "Refused", "active", "env_for", "register_use", "report_use", "require", "secret_of", "set_active"]

ACTIVE: Optional[Hub] = None


def set_active(hub: Optional[Hub]) -> None:
    global ACTIVE
    ACTIVE = hub


def active() -> Hub:
    global ACTIVE
    if ACTIVE is None:
        from ..config import _default_state_dir
        ACTIVE = Hub(Path(os.environ.get("LAMPWAY_STATE_DIR") or _default_state_dir()))
    return ACTIVE


def require(cid: str) -> Credential:
    return active().require(cid)


def credential(cid: str) -> Credential:
    return active().credential(cid)


def env_for(ids=()) -> dict:
    return active().env_for(ids)


def report_use(cid: str, ok: bool, status: Optional[int] = None) -> None:
    try:
        active().report_use(cid, ok, status)
    except Exception:  # noqa: BLE001 - recording a use must never break the call that made it
        pass
