# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault's drag and drop in the real build (coordinator's addition to the facelift lane): a Vault tile dragged
onto the Cube in the 3D viewport places that asset on that object, through ``mixar.asset_library_place``."""

import harness


def test_a_vault_tile_dropped_on_the_cube_is_placed_on_the_cube(tmp_path):
    report = harness.run_state("vault_drag", tmp_path)
    facts = report["facts"]
    assert facts["queued"], facts
    assert facts["placed"] == [{"asset_id": "a-42", "where": "object:Cube"}], facts
    assert facts["selected"] == ["a-42"], "a plain click still selects the tile, and a drag does not"
