# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 07 in the real build: the Way is registered in the captain's order, each tool has its typed operator, the
free-text runners are gone, and a typed run marks its step done."""

import harness


def test_the_way_is_registered_and_a_typed_run_marks_its_step(tmp_path):
    r = harness.run_state("the_way", tmp_path)["facts"]
    assert r["panels"] == ["seeds", "uv", "mesh_qa", "parts", "mesh_paint", "fit", "bind"], r
    assert r["kinds"] == {"object": "STRING", "target_faces": "INT", "symmetry": "BOOLEAN", "adaptivity": "FLOAT"}, r
    assert r["free_text"] == [], r
    assert r["run"] == ["FINISHED"] and r["done"] == ["uv"], r
