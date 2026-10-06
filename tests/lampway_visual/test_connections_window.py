# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections window in the real build (specs/connections/connections_face.md 10.10): a missing row with the paste
field (a password field the dump reports as secret), and a sign-in waiting on the browser."""

import harness


def test_a_missing_row_offers_the_paste_field(tmp_path):
    facts = harness.run_state("connections_missing", tmp_path)["facts"]
    for text in ("Agents", "Studios", "Video and images", "ChatGPT plan", "OpenRouter", "Meshy", "Higgsfield", "Paste a key", "Save and test",
                 "Open in Privacy", "Meshy is not connected: connect it in Connections"):
        assert text in facts["texts"], (text, facts["texts"])
    assert facts["secret"] == [True], facts


def test_a_sign_in_waiting_on_the_browser(tmp_path):
    facts = harness.run_state("connections_waiting", tmp_path)["facts"]
    assert "Sign in with Higgsfield" in facts["texts"], facts["texts"]
