"""Audit F9 (2026-10-06): the TOON encoder emitted non-conformant output that corrupts data on decode - "true", "42", "x: y" and
"#c" unquoted (read back as a bool, a number, a key and a DROPPED comment), ragged rows padded with invented nulls, 1234567.0 as
1.23457e+06, and the empty-array header key[0]: that TOON 4 forbids. The official encode fixtures (tests/fixtures/toon, MIT) are
the oracle: every case inside this encoder's scope - objects, primitive arrays, tabular and list-form arrays - must match byte
for byte. Out of scope (the shared encoder is the cloud crew's C0): keyed tabular objects, nested field groups, options."""
import json
from pathlib import Path

import pytest

from lampway_server.compute import toon_out as T

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "toon" / "encode").glob("*.json"))
OUT_OF_SCOPE = ("keyed", "nested field group", "keyed-eligible")


def _cases():
    for f in FIXTURES:
        for t in json.loads(f.read_text(encoding="utf-8"))["tests"]:
            if t.get("options") or t.get("shouldError") or not isinstance(t["input"], dict) or any(w in t["name"] for w in OUT_OF_SCOPE):
                continue
            yield pytest.param(t["input"], t["expected"], id=f"{f.stem}: {t['name']}")


CASES = list(_cases())


def test_the_fixture_scope_is_not_empty():
    assert len(CASES) >= 60, len(CASES)


@pytest.mark.parametrize("value,expected", CASES)
def test_the_encoder_matches_the_official_fixture(value, expected):
    assert T.dumps(value) == expected
