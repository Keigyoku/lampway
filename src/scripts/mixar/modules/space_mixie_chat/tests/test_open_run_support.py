# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shared scene double models properties and restores cached bpy imports."""

import sys
from types import ModuleType

import pytest
from _open_run_support import _scene, live_bpy


def test_scene_custom_properties_are_distinct_from_rna_attributes():
    scene = _scene("Original")
    assert scene.get("missing", False) is False
    scene["name"] = "custom name"
    assert scene["name"] == scene.get("name") == "custom name"
    assert scene.name == "Original" and "name" in scene
    del scene["name"]
    assert "name" not in scene and scene.get("name") is None
    with pytest.raises(KeyError):
        scene["name"]


def test_live_bpy_rebinds_cached_chat_imports_and_restores_them(monkeypatch):
    chat = ModuleType("mixar.modules.space_mixie_chat.fixture_probe")
    unrelated = ModuleType("unrelated_fixture_probe")
    original = object()
    chat.bpy = unrelated.bpy = original
    monkeypatch.setitem(sys.modules, chat.__name__, chat)
    monkeypatch.setitem(sys.modules, unrelated.__name__, unrelated)
    current = sys.modules["bpy"]
    original_scenes = current.data.scenes
    with monkeypatch.context() as local:
        assert live_bpy.__wrapped__(local) is current
        assert chat.bpy is current and unrelated.bpy is original
        assert current.data.scenes == []
    assert chat.bpy is original and unrelated.bpy is original
    assert current.data.scenes is original_scenes
