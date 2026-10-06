# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Keyboard shortcuts fire in the Zen workspace, the one a new profile opens in (a lane vault-ui finding)."""

import harness


def test_a_shortcut_fires_in_zen_mode(tmp_path):
    facts = harness.run_state("zen_shortcuts", tmp_path)["facts"]
    assert facts["workspace"] == "Lamplight", facts
    assert facts["sidebar_toggled"], f"N did nothing over the viewport: {facts}"
    assert facts["full_screen"], f"ctrl+alt+Space did nothing over the viewport: {facts}"
