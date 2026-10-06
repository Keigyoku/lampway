# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 06 in the real build: the Studios panel's waiting spend says its price on the button, and a maybe-sent job
offers the user's two ways out."""

import harness


def test_the_studios_panel_draws_the_price_and_the_two_ways_out(tmp_path):
    buttons = harness.run_state("studios_face", tmp_path)["facts"]["buttons"]
    assert "LAMPWAY_OT_studio_confirm|Spend 13.5 credits" in buttons, buttons
    assert "LAMPWAY_OT_studio_reject|Not now" in buttons, buttons
    assert "LAMPWAY_OT_receipt_acknowledge|It did not run" in buttons, buttons
    assert "LAMPWAY_OT_receipt_link|Link its job id" in buttons, buttons
    assert not [b for b in buttons if b.endswith("|Confirm and spend")], buttons
