# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shelf's AXI/TOON output conventions (tools/AXI.md, TOON-SPEC.md v4.1) for anything that stays a CLI:
structured output on stdout, refusals on stdout with exit 1, definitive empty states, next-step help[]."""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import axi  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def out(capsys):
    return capsys.readouterr().out


def test_table_prints_header_count_and_rows(capsys):
    axi.table("seeds", [{"id": "a1", "score": 0.5}, {"id": "b,2", "score": 12}], ["id", "score"])
    assert out(capsys) == 'seeds[2]{id,score}:\n  a1,0.5\n  "b,2",12\n'


def test_empty_table_is_a_definitive_zero(capsys):
    axi.table("seeds", [], ["id"])
    assert out(capsys) == "seeds: []\n"          # TOON 4's empty array (the legacy seeds[0]: MUST NOT be emitted)


def test_table_with_a_total_says_so(capsys):
    axi.table("seeds", [{"id": "a"}], ["id"], total=40)
    assert out(capsys).splitlines()[0] == "count: 1 of 40 total"


@pytest.mark.parametrize("value,expected", [
    (None, "null"), (True, "true"), (False, "false"), (3, "3"), (0.123456, "0.123456"),     # canonical, never rounded (audit F9: rounding lost values)
    ("plain", "plain"), ("", '""'), ("true", '"true"'), ("12", '"12"'), ("a:b", '"a:b"'),
    ("- x", '"- x"'), ("#x", '"#x"'), (" lead", '" lead"'), ("two\nlines", '"two\\nlines"'),
    ('say "hi"', '"say \\"hi\\""'),
])
def test_primitives_are_quoted_per_spec_7_2(value, expected):
    assert axi._s(value) == expected


def test_kv_nests_one_level(capsys):
    axi.kv({"a": 1, "b": {"c": "x:y"}})
    assert out(capsys) == 'a: 1\nb:\n  c: "x:y"\n'


def test_helps_lists_next_steps(capsys):
    axi.helps(["tool x <id>"])
    assert out(capsys) == 'help[1]:\n  - Run `tool x <id>`\n'


def test_refuse_prints_on_stdout_and_exits_1(capsys):
    with pytest.raises(SystemExit) as e:
        axi.refuse("no such tag", ["lampway qa tags <scene>"])
    assert e.value.code == 1
    assert out(capsys) == 'error: no such tag\nhelp[1]:\n  - Run `lampway qa tags <scene>`\n'


def test_trunc_cuts_with_a_size_hint():
    assert axi.trunc("x" * 300, 10, "see file") == "x" * 10 + "… (truncated, 300 chars total — see file)"
    assert axi.trunc("short", 10) == "short"


def test_home_renders_the_home_directory_as_tilde(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(axi, "HOME", str(tmp_path))
    f = tmp_path / "tools" / "t.py"
    f.parent.mkdir()
    f.write_text("")
    axi.home(str(f), "does a thing")
    assert out(capsys) == "bin: ~/tools/t.py\ndescription: does a thing\n"


@pytest.mark.parametrize("path", ["src/scripts/mixar/modules/lampway_tools/axi.py", "server/lampway_server/studios/axi.py"])
def test_numbers_are_canonical_and_empty_tables_use_the_toon_4_form(path, capsys):
    """Audit F9: axi printed 1234567.0 as 1.235e+06 (four significant digits: the value is LOST on decode) and an empty table as
    seeds[0]:, which TOON 4 forbids (an empty array is `key: []`). Both copies of the module are held to the same rules."""
    spec = importlib.util.spec_from_file_location("axi_under_test", REPO / path)
    ax = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ax)
    assert [ax._s(v) for v in (1234567.0, 0.1, 2.5e-7, 1e21, -0.0, 3.0, 12)] == ["1234567", "0.1", "2.5e-7", "1e+21", "0", "3", "12"]
    ax.table("seeds", [], ["id"])
    ax.kv({"line\n": 1})
    out = capsys.readouterr().out
    assert "seeds: []" in out and "[0]:" not in out and '"line\\n": 1' in out, out
