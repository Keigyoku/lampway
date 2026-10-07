# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shelf's AXI/TOON output conventions (tools/AXI.md, TOON-SPEC.md v4.3) for anything that stays a CLI:
structured output on stdout, refusals on stdout with exit 1, definitive empty states, next-step help[]."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import axi  # noqa: E402


def out(capsys):
    return capsys.readouterr().out


def test_table_prints_header_count_and_rows(capsys):
    axi.table("seeds", [{"id": "a1", "score": 0.5}, {"id": "b,2", "score": 12}], ["id", "score"])
    assert out(capsys) == 'seeds[2]{id,score}:\n  a1,0.5\n  "b,2",12'


def test_empty_table_is_a_definitive_zero(capsys):
    axi.table("seeds", [], ["id"])
    assert out(capsys) == "seeds: []"


def test_table_with_a_total_says_so(capsys):
    axi.table("seeds", [{"id": "a"}], ["id"], total=40)
    assert out(capsys).splitlines()[0] == "count: 1 of 40 total"


@pytest.mark.parametrize("value,expected", [
    (None, "null"), (True, "true"), (False, "false"), (3, "3"), (0.123456, "0.123456"),
    ("plain", "plain"), ("", '""'), ("true", '"true"'), ("12", '"12"'), ("a:b", '"a:b"'),
    ("- x", '"- x"'), ("#x", '"#x"'), (" lead", '" lead"'), ("two\nlines", '"two\\nlines"'),
    ('say "hi"', '"say \\"hi\\""'),
])
def test_primitives_are_quoted_per_spec_7_2(value, expected):
    assert axi._s(value) == expected


def test_kv_nests_one_level(capsys):
    axi.kv({"a": 1, "b": {"c": "x:y"}})
    assert out(capsys) == 'a: 1\nb:\n  c: "x:y"'


def test_helps_lists_next_steps(capsys):
    axi.helps(["tool x <id>"])
    assert out(capsys) == 'help[1]: Run `tool x <id>`'


def test_refuse_prints_on_stdout_and_exits_1(capsys):
    with pytest.raises(SystemExit) as e:
        axi.refuse("no such tag", ["lampway qa tags <scene>"])
    assert e.value.code == 1
    assert out(capsys) == 'error: no such tag\nhelp[1]: Run `lampway qa tags <scene>`'


def test_trunc_cuts_with_a_size_hint():
    assert axi.trunc("x" * 300, 10, "see file") == "x" * 10 + "… (truncated, 300 chars total — see file)"
    assert axi.trunc("short", 10) == "short"


def test_home_renders_the_home_directory_as_tilde(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(axi, "HOME", str(tmp_path))
    f = tmp_path / "tools" / "t.py"
    f.parent.mkdir()
    f.write_text("")
    axi.home(str(f), "does a thing")
    assert out(capsys) == "bin: ~/tools/t.py\ndescription: does a thing"
