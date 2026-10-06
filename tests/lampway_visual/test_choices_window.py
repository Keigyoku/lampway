# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Choices window in the real build: a fallback purpose with its skipped option's fix, a waiting proposal, the eye."""

import harness


def test_a_fallback_purpose_with_a_proposal(tmp_path):
    facts = harness.run_state("choices_window", tmp_path)["facts"]
    texts = facts["texts"]
    for text in ("Agents", "Images", "Tracking and motion", "Plates", "Main agent", "Body tracking", "Spending",
                 "Accept for this project", "Accept for all projects", "Decline", "route studio:tripo is off", "Open in Privacy"):
        assert text in texts, (text, texts)
    assert any(t.startswith("Now: openai/gpt-image-2.5-flare, openrouter") for t in texts), texts
    assert ("LAMPWAY_OT_choices_acknowledge", "") in [tuple(o) for o in facts["ops"]], "the eye takes an acknowledgement back"
