# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generated JSON-model round trips supplement the official conformance corpus."""
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
from lampway_server.compute.toon_out import decode, encode, normalize

strings = st.text(alphabet=st.characters(blacklist_categories=('Cs',)), max_size=40)
primitives = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | strings
values = st.recursive(primitives, lambda child: st.lists(child, max_size=5) | st.dictionaries(strings, child, max_size=5), max_leaves=30)

def json_equal(a, b):
    # TOON §2 compares numbers after host numeric normalization. A binary64
    # source float's shortest decimal token must round-trip as binary64; Python
    # instead compares int == float against the exact binary expansion.
    # Two arbitrary-precision integers still compare exactly.
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b) if isinstance(a, float) or isinstance(b, float) else a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return a == b


@given(values, st.sampled_from([',', '\t', '|']), st.integers(min_value=1, max_value=4))
@settings(max_examples=1000, deadline=None, database=None, derandomize=True)
def test_generated_json_roundtrip(value, delimiter, indent):
    text = encode(value, delimiter=delimiter, indent_size=indent)
    assert json_equal(decode(text, indent_size=indent), normalize(value))
    assert not text.endswith('\n')
    assert all(not line.endswith(' ') for line in text.split('\n'))


def test_normalization_and_surrogate_refusal():
    import pytest
    assert decode(encode({'n': float('nan'), 'inf': float('inf'), 'negative_zero': -0.0,
                          'tuple': (1, 2), 'set': {3}, 'unsupported': object()})) == {
                              'n': None, 'inf': None, 'negative_zero': 0, 'tuple': [1, 2], 'set': [3], 'unsupported': None}
    with pytest.raises(ValueError, match='surrogates'):
        encode('\ud800')
