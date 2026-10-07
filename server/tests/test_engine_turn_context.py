# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""R3 (docs/reports/agent-modes-spec.md): what the client attaches reaches the engine's prompt. Spec A2: the island's turn is
``image.attach_bytes`` per image, then ``prompt.submit`` with the text carrying R3's context blocks."""

from lampway_server.engine import turn_context as TC

RULES = {"version": 1, "global": [{"id": "g", "text": "Metric units.", "enabled": True}],
         "project": [{"id": "p", "text": "Keep under 10k tris.", "enabled": True}, {"id": "q", "text": "Off rule.", "enabled": False}]}
PNG = "iVBORw0KGgo="


def test_rules_folders_and_this_turn_ride_with_the_message_and_images_become_attachments():
    payload = {"rules": RULES, "content": [{"type": "text", "text": "x"},
                                           {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
                                           {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{PNG}"}}],
               "folder_context": {"folders": [{"name": "refs", "available": True, "file_count": 2, "kinds": {"image": 2},
                                               "files": ["front.png", "side.png"]}]},
               "attachment_names": ["front.png"], "imported_object_names": ["Chair"]}
    t, key = TC.prompt_text("Model the chair.", payload)
    assert "Metric units." in t and "Keep under 10k tris." in t and "Off rule." not in t
    assert "refs: 2 files" in t and "front.png" in t and "Objects the user just imported: Chair" in t
    assert t.rstrip().endswith("Model the chair.")
    assert key and key != "none"
    # spec A2: each image is one image.attach_bytes before the prompt, named by the client's attachment name when it has one
    assert TC.attachments(payload) == [("front.png", PNG), ("image-2.jpg", PNG)]


def test_rules_ride_again_only_when_they_change():
    _, key = TC.prompt_text("one", {"rules": RULES})
    again, same = TC.prompt_text("two", {"rules": RULES}, key)
    assert same == key and "Metric units." not in again and again == "two"
    changed = {"global": [], "project": [{"text": "Use quads.", "enabled": True}]}
    later, new = TC.prompt_text("three", {"rules": changed}, key)
    assert new != key and "Use quads." in later and "Metric units." not in later
    cleared, gone = TC.prompt_text("four", {"rules": {"global": [], "project": []}}, new)
    assert gone == "none" and "removed every rule" in cleared


def test_a_plain_message_is_just_the_message():
    text, key = TC.prompt_text("hello", {})
    assert text == "hello" and key == "" and TC.attachments({}) == []


def test_an_empty_rules_snapshot_on_a_first_turn_says_nothing():
    """The client sends ``{"project": [], "global": []}`` when there are no rules: nothing was removed, so nothing is said."""
    text, key = TC.prompt_text("hello", {"rules": {"project": [], "global": []}})
    assert text == "hello" and key == "none"
