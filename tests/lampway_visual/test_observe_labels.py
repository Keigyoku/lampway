# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cloud audit F17 in the real build: observe labels an icon-only control by its tooltip, and pages with ``offset``."""

import harness


def test_observe_labels_by_tooltip_and_pages_with_offset(tmp_path):
    f = harness.run_state("observe_labels", tmp_path)["facts"]
    assert f["empty_text"] > 0 and f["empty_label"] == 0, f
    assert f["tip_fallbacks_right"], "text and tooltip keep precedence over native identity"
    assert f["shown"] == f["total"], "label coverage must include the complete current inventory"
    assert f["identity_fallbacks"] > 0, "cover controls with neither text nor tooltip"
    assert f["offset_schema"] == "ok", f["offset_schema"]
    assert f["offset_echo"] == 5
    assert f["pages"][0] + f["pages"][1] == f["same_as_every"], "page 2 continues page 1, in observe's order"
    assert f["page_handles"] == [["t0", "t1", "t2", "t3", "t4"], ["t5", "t6", "t7", "t8", "t9"]], "handles are positions, unique across pages"
