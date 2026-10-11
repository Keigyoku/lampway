# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared doubles for the open-run suites (test_open_run, test_socket_turns).

Not a test module: pytest puts this directory on sys.path (no __init__.py),
so the suites ``from _open_run_support import ...``. Fixtures imported by
name into a test module are collected like local ones.
"""

import os
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

_SRC_SCRIPTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), *([".."] * 4))
)
if _SRC_SCRIPTS not in sys.path:
    sys.path.insert(0, _SRC_SCRIPTS)

for _dep in ("keyring", "keyring.errors", "websocket", "requests", "jwt",
             "sentry_sdk", "bpy.utils.previews"):
    sys.modules.setdefault(_dep, MagicMock(name=_dep))

from mixar.modules.space_mixie_chat.core import turn_events  # noqa: E402
from mixar.modules.space_mixie_chat.core.session import SessionManager  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _Messages(list):
    """scene.mixie_chat_messages stand-in."""

    def add(self):
        msg = SimpleNamespace(sender='', text='', bubble_id='', loader_visible=False,
                              loader_texts='', delivery_hint='', content='',
                              feedback_visible=False, attachments=_Messages())
        self.append(msg)
        return msg

    def remove(self, idx):
        del self[idx]


class _Scenes(list):
    def get(self, name):
        return next((s for s in self if s.name == name), None)


class _Scene(SimpleNamespace):
    """RNA-style attributes plus Blender's separate custom-property mapping."""

    def __init__(self, **attributes):
        super().__init__(**attributes)
        self._props = {}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value

    def __contains__(self, key):
        return key in self._props

    def __delitem__(self, key):
        del self._props[key]


def _scene(name="Scene", session_id="sid-1", state="IDLE"):
    return _Scene(
        name=name, mixie_session_id=session_id, mixie_chat_state=state,
        mixie_chat_is_busy=False, mixie_run_open=False, mixie_run_id="",
        mixie_chat_active_turn_mode="", mixie_chat_mode="AGENT",
        mixie_chat_cat_activity="", mixie_chat_cat_activity_until="",
        mixie_chat_input="", mixie_chat_messages=_Messages(),
    )


@pytest.fixture(autouse=True)
def clean_state():
    SessionManager.reset()
    turn_events.shutdown(app_exit=True)
    yield
    SessionManager.reset()
    turn_events.shutdown(app_exit=True)


@pytest.fixture
def live_bpy(monkeypatch):
    """Use one current bpy double for call-time and cached module imports.

    Other suites install a fresh bpy double during collection. Chat modules
    already imported may still hold the previous double; restore those globals
    automatically with this fixture's monkeypatch lifetime.
    """
    bpy = sys.modules["bpy"]
    for name, module in list(sys.modules.items()):
        if (name.startswith("mixar.modules.space_mixie_chat.")
                and isinstance(module, ModuleType) and "bpy" in module.__dict__):
            monkeypatch.setattr(module, "bpy", bpy)
            assert module.bpy is bpy
    monkeypatch.setattr(bpy.data, "scenes", _Scenes(), raising=False)
    return bpy
