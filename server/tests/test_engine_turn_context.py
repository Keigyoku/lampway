# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""R3 (docs/reports/agent-modes-spec.md): what the client attaches reaches the engine's prompt."""

from lampway_server.engine import turn_context as TC

RULES = {"version": 1, "global": [{"id": "g", "text": "Metric units.", "enabled": True}],
         "project": [{"id": "p", "text": "Keep under 10k tris.", "enabled": True}, {"id": "q", "text": "Off rule.", "enabled": False}]}
PNG = "iVBORw0KGgo="


def text_of(blocks):
    return blocks[0].text


def test_rules_folders_and_this_turn_ride_with_the_message_and_images_become_image_blocks():
    payload = {"rules": RULES, "content": [{"type": "text", "text": "x"},
                                           {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}],
               "folder_context": {"folders": [{"name": "refs", "available": True, "file_count": 2, "kinds": {"image": 2},
                                               "files": ["front.png", "side.png"]}]},
               "attachment_names": ["front.png"], "imported_object_names": ["Chair"]}
    blocks, key = TC.prompt_blocks("Model the chair.", payload)
    t = text_of(blocks)
    assert "Metric units." in t and "Keep under 10k tris." in t and "Off rule." not in t
    assert "refs: 2 files" in t and "front.png" in t and "Objects the user just imported: Chair" in t
    assert t.rstrip().endswith("Model the chair.")
    assert len(blocks) == 2 and blocks[1].type == "image" and blocks[1].mime_type == "image/png" and blocks[1].data == PNG
    assert key and key != "none"


def test_rules_ride_again_only_when_they_change():
    _, key = TC.prompt_blocks("one", {"rules": RULES})
    again, same = TC.prompt_blocks("two", {"rules": RULES}, key)
    assert same == key and "Metric units." not in text_of(again) and text_of(again) == "two"
    changed = {"global": [], "project": [{"text": "Use quads.", "enabled": True}]}
    later, new = TC.prompt_blocks("three", {"rules": changed}, key)
    assert new != key and "Use quads." in text_of(later) and "Metric units." not in text_of(later)
    cleared, gone = TC.prompt_blocks("four", {"rules": {"global": [], "project": []}}, new)
    assert gone == "none" and "removed every rule" in text_of(cleared)


def test_a_plain_message_is_just_the_message():
    blocks, key = TC.prompt_blocks("hello", {})
    assert text_of(blocks) == "hello" and len(blocks) == 1 and key == ""
