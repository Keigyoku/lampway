# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 11 in the real build: Spin turns every view together; a manual orbit in one view stops it (mrmak/05 6.6)."""

import harness


def _apart(a, b):
    return min(abs(a - b), 360 - abs(a - b))


def test_spin_turns_every_view_together_and_an_orbit_stops_it(tmp_path):
    f = harness.run_state("compare_spin", tmp_path)["facts"]
    assert f["spin_after_toggle"] is True, f
    assert len(f["yaw0"]) == 4 and len(set(f["yaw1"])) == 1, ("the views turn together", f)
    assert _apart(f["yaw1"][0], f["yaw0"][0]) > 5, ("Spin turned the views", f)
    assert f["spin_after_orbit"] is False, ("a manual orbit turns Spin off", f)
    assert f["yaw2"] == f["yaw3"], ("stopped: nothing turns after the orbit", f)
