# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native viewport geometry and secret masking use physical, not logical pixels."""

import base64
from contextlib import nullcontext
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from mixar.modules.common.ui_control.core import input as native_input, observe


@pytest.mark.parametrize("key,mods,text", [
    ("TWO", {}, "2"), ("MINUS", {}, "-"), ("PERIOD", {}, "."),
    ("NUMPAD_2", {}, "2"), ("G", {}, "g"), ("A", {"shift": True}, "A"),
    ("TWO", {"shift": True}, "@"), ("A", {"oskey": True}, ""),
    ("A", {"ctrl": True}, ""), ("RET", {}, ""),
])
def test_keyboard_events_include_numeric_text(key, mods, text):
    assert native_input.keyboard_text(key, mods) == text


def test_transparent_zen_header_only_occludes_drawn_controls(monkeypatch):
    header = SimpleNamespace(type="TOOL_HEADER", width=100, height=80,
                             as_pointer=lambda: 7)
    area = SimpleNamespace(type="VIEW_3D", height=100, regions=[header])
    item = {"rect": [0, 0, 100, 100], "region_type": "WINDOW", "_area": area,
            "_win": SimpleNamespace(as_pointer=lambda: 1)}
    monkeypatch.setattr(observe, "widgets", lambda: [])
    assert native_input.point(item) == (50, 50)
    monkeypatch.setattr(observe, "widgets", lambda: [{"r": 7, "rect": [40, 0, 100, 100]}])
    assert native_input.point(item) == (20, 50)


def test_retina_secret_mask_uses_widget_pixels_without_double_scaling(monkeypatch):
    from mixar.modules.common.render_coordinator import core as renders
    monkeypatch.setattr(renders, "busy", lambda: False)

    def capture(filepath):
        Image.new("RGB", (100, 100), "red").save(filepath)
        return True

    win = SimpleNamespace(width=50, height=50, as_pointer=lambda: 1, mixar_ui_capture=capture)
    monkeypatch.setattr(observe, "bpy", SimpleNamespace(
        app=SimpleNamespace(is_job_running=lambda _: False),
        context=SimpleNamespace(window_manager=SimpleNamespace(mixar_window_resizing=False),
                                temp_override=lambda **kwargs: nullcontext())))
    block, frame = observe.image(win, [{"secret": True, "w": 1, "rect": [10, 10, 30, 30]}])
    with Image.open(io.BytesIO(base64.b64decode(block["data"]))) as image:
        assert image.getpixel((20, 80)) == (0, 0, 0)
        assert image.getpixel((40, 60)) == (255, 0, 0)
    assert frame["window_width"] == 100 and frame["window_height"] == 100


@pytest.mark.parametrize("start,end,blocked", [
    ((0, 50), (100, 50), True),  # Both endpoints clear, but crosses the panel.
    ((0, 10), (100, 10), False),
    ((50, 0), (50, 100), True),
    ((0, 0), (20, 20), False),
    ((50, 50), (50, 50), True),
])
def test_gesture_path_cannot_cross_an_occluding_panel(start, end, blocked):
    assert native_input.segment_intersects(start, end, (40, 40, 60, 60)) is blocked


@pytest.mark.parametrize("item,expected", [
    ({"text": "Save", "tip": "Save file"}, "Save"),
    ({"text": "", "tip": "Toggle overlay"}, "Toggle overlay"),
    ({"op": "wm.search_menu", "type": "BUTTON"}, "wm.search_menu"),
    ({"prop_owner": "Scene", "prop": "camera", "type": "SEARCH_MENU"}, "Scene.camera"),
    ({"surface": "profile", "type": "BUTTON"}, "profile"),
    ({"area_type": "VIEW_3D", "region_type": "HEADER", "type": "SEPARATOR"}, "VIEW_3D HEADER SEPARATOR"),
])
def test_observed_controls_have_labels_from_native_sources(item, expected, monkeypatch):
    win = SimpleNamespace(as_pointer=lambda: 1, screen=SimpleNamespace(areas=[]),
                          scene=SimpleNamespace(mixie_session_id="fixture", name="Fixture"))
    monkeypatch.setattr(observe, "main_window", lambda: win)
    monkeypatch.setattr(observe, "signature", lambda: ())
    monkeypatch.setattr(observe, "widgets", lambda: [{**item, "w": 1}])
    monkeypatch.setattr(observe, "window_extent", lambda _: {"width": 10, "height": 10})
    monkeypatch.setattr(observe, "bpy", SimpleNamespace(context=SimpleNamespace(
        window_manager=SimpleNamespace(windows=[win]))))
    result, _ = observe.observe("fixture", {})
    assert result["targets"][0]["label"] == expected


@pytest.mark.parametrize("item", json.loads((Path(__file__).parents[1] /
    "lampway_tools/fixtures/issue2_native_label_shapes.json").read_text())["targets"])
def test_native_unlabeled_control_shapes_keep_their_source_labels(item, monkeypatch):
    """Pin every text/tooltip-free row in the measured inventory, including duplicates."""
    expected = item["label"]
    raw = {key: value for key, value in item.items() if key != "label"}
    assert not raw.get("text") and not raw.get("tip")
    test_observed_controls_have_labels_from_native_sources(raw, expected, monkeypatch)


ORIGINAL_LABEL_INVENTORY = json.loads((Path(__file__).parents[1] /
    "lampway_tools/fixtures/issue2_native_label_shapes.json").read_text())["original_inventory"]


def test_original_71_target_inventory_preserves_every_unlabeled_identity():
    assert ORIGINAL_LABEL_INVENTORY["total_targets"] == 71
    assert ORIGINAL_LABEL_INVENTORY["unlabeled_targets"] == 16
    assert [row["original_target"] for row in ORIGINAL_LABEL_INVENTORY["targets"]] == [
        "t6", "t9", "t10", "t11", "t12", "t13", "t14", "t27", "t33", "t36",
        "t37", "t39", "t41", "t43", "t44", "t70"]
    assert ORIGINAL_LABEL_INVENTORY["targets"][-1]["label"] == "Scene.mixie_chat_input"


@pytest.mark.parametrize("item", ORIGINAL_LABEL_INVENTORY["targets"],
                         ids=lambda row: row["original_target"])
def test_original_unlabeled_controls_receive_native_source_labels(item, monkeypatch):
    """The exact sixteen failing controls, rather than a smaller new layout."""
    raw = {key: value for key, value in item.items() if key not in ("label", "original_target")}
    assert not raw.get("text") and not raw.get("tip")
    test_observed_controls_have_labels_from_native_sources(raw, item["label"], monkeypatch)
