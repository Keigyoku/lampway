# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The anneal rule as a pure function (rail/anneal.py): each test names the behaviour and would go red if it regressed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rail"))

import anneal as A  # noqa: E402
import railcore  # noqa: E402

FM = "---\nanneal_on_error: true\nanneal_on_success: true\nanneal_safety: gated\nverification-mode: mixed\n---\n\n"
HEAD = "## Anneal log\n\n| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |\n|---|---|---|---|---|---|\n"
R0 = "| 2026-10-01 | a | b | c | d | e |\n"
R1 = "| 2026-10-02 | f | g | h | i | j |\n"
R2 = "| 2026-10-03 | k | l | m | n | o |\n"


def rail(body="rule one\n", rows=(R0,)):
    return FM + "# X\n\n" + body + "\n" + HEAD + "".join(rows)


def codes(findings):
    return sorted(f["code"] for f in findings)


def test_a_receipted_change_is_clean():
    assert A.assess({"a/AGENTS.md": rail()}, {"a/AGENTS.md": rail("rule two\n", (R0, R1))}, {}) == []


def test_a_body_change_without_a_row_is_refused():
    assert codes(A.assess({"a/AGENTS.md": rail()}, {"a/AGENTS.md": rail("rule two\n")}, {})) == ["RAIL-010"]


def test_a_row_without_a_body_change_is_a_receipt_for_nothing():
    assert codes(A.assess({"a/AGENTS.md": rail()}, {"a/AGENTS.md": rail(rows=(R0, R1))}, {})) == ["RAIL-012"]


def test_an_edited_prior_row_is_refused_even_with_a_new_row_and_body():
    edited = R0.replace("| a |", "| z |")
    assert codes(A.assess({"a/AGENTS.md": rail()}, {"a/AGENTS.md": rail("rule two\n", (edited, R1))}, {})) == ["RAIL-011"]


def test_a_new_rail_with_rows_is_clean_and_one_without_is_not():
    assert A.assess({}, {"a/AGENTS.md": rail()}, {}) == []
    assert codes(A.assess({}, {"a/AGENTS.md": FM + "# X\n"}, {})) == ["RAIL-005"]


def test_a_trigger_owes_its_owner_a_row_and_a_body_change():
    owner = "rail/skills/demo/SKILL.md"
    before = {"tool.py": "v1", owner: rail()}
    assert codes(A.assess(before, {"tool.py": "v2", owner: rail()}, {"tool.py": owner})) == ["RAIL-013"]
    assert codes(A.assess(before, {"tool.py": "v2", owner: rail(rows=(R0, R1))}, {"tool.py": owner})) == ["RAIL-012", "RAIL-013"]
    assert A.assess(before, {"tool.py": "v2", owner: rail("new step\n", (R0, R1))}, {"tool.py": owner}) == []


def test_a_file_beside_a_skill_is_part_of_the_skill():
    skill, leaf = "rail/skills/demo/SKILL.md", "rail/skills/demo/leaf.md"
    before = {skill: rail(), leaf: "v1"}
    assert codes(A.assess(before, {skill: rail(), leaf: "v2"}, {})) == ["RAIL-010", "RAIL-013"]
    assert A.assess(before, {skill: rail(rows=(R0, R1)), leaf: "v2"}, {}) == []   # the sibling IS the body change


def test_a_deleted_rail_needs_a_successor_carrying_its_rows():
    before = {"a/AGENTS.md": rail()}
    assert codes(A.assess(before, {}, {})) == ["RAIL-014"]
    assert A.assess(before, {"b/AGENTS.md": rail("moved\n", (R0, R1))}, {}) == []
    assert codes(A.assess(before, {"b/AGENTS.md": rail("moved\n", (R1,))}, {})) == ["RAIL-014"]


def test_prose_inside_the_anneal_log_is_refused():
    with pytest.raises(A.RailError) as exc:
        A.anneal_rows(rail() + "a note under the table\n")
    assert exc.value.code == "RAIL-005"


def test_rows_must_be_in_date_order():
    with pytest.raises(A.RailError):
        A.anneal_rows(rail(rows=(R1, R0)))


def test_a_merge_keeping_both_lanes_rows_inherits_them():
    base = {"a/AGENTS.md": rail("one\n\nmiddle\n\ntwo\n")}
    lane_a = {"a/AGENTS.md": rail("one A\n\nmiddle\n\ntwo\n", (R0, R1))}
    lane_b = {"a/AGENTS.md": rail("one\n\nmiddle\n\ntwo B\n", (R0, R2))}
    merged = {"a/AGENTS.md": rail("one A\n\nmiddle\n\ntwo B\n", (R0, R1, R2))}
    assert A.assess_merge([lane_a, lane_b], merged, {}, base, railcore._merge3) == []
    # without a three-way merge to recognise the combination, the merge authored the body and owes a row
    assert codes(A.assess_merge([lane_a, lane_b], merged, {}, base, None)) == ["RAIL-010"]
    # a rule only the merge wrote is authored, whatever the merge tool says
    authored = {"a/AGENTS.md": rail("one A\n\nmiddle, rewritten\n\ntwo B\n", (R0, R1, R2))}
    assert codes(A.assess_merge([lane_a, lane_b], authored, {}, base, railcore._merge3)) == ["RAIL-010"]


def test_a_merge_that_loses_a_parents_row_is_refused():
    lane_a = {"a/AGENTS.md": rail("x\n", (R0, R1))}
    lane_b = {"a/AGENTS.md": rail("x\n", (R0, R2))}
    assert codes(A.assess_merge([lane_a, lane_b], {"a/AGENTS.md": rail("x\n", (R0, R2))}, {})) == []           # equals lane b: inherited
    assert codes(A.assess_merge([lane_a, lane_b], {"a/AGENTS.md": rail("x\ny\n", (R0, R1.replace("| f |", "| F |"), R2))}, {})) == ["RAIL-011"]


def test_a_merge_taking_a_file_from_one_parent_owes_nothing():
    old = {"tool.py": "v1", "rail/skills/d/SKILL.md": rail()}
    new = {"tool.py": "v2", "rail/skills/d/SKILL.md": rail("step 2\n", (R0, R1))}
    assert A.assess_merge([old, new], new, {"tool.py": "rail/skills/d/SKILL.md"}) == []
    authored = dict(new, **{"tool.py": "v3"})
    assert codes(A.assess_merge([old, new], authored, {"tool.py": "rail/skills/d/SKILL.md"})) == ["RAIL-013"]


def test_frontmatter_holds_the_gated_contract():
    with pytest.raises(A.RailError) as exc:
        A.check_frontmatter(rail().replace("gated", "auto"))
    assert exc.value.code == "RAIL-004"
    with pytest.raises(A.RailError):
        A.check_frontmatter(rail(), skill_name="demo")              # a skill needs name and description
    skill = rail().replace("---\n\n", 'name: demo\ndescription: "use it"\n---\n\n', 1)
    assert A.check_frontmatter(skill, skill_name="demo")["name"] == "demo"
