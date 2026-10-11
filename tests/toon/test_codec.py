# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Official encoder examples, and local corruption regressions."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server'))
from lampway_server.compute import toon_out as toon

CASES = [(path.name, case) for path in sorted((Path(__file__).parent / 'fixtures/encode').glob('*.json'))
         for case in json.loads(path.read_text())['tests']]

@pytest.mark.parametrize('source,case', CASES, ids=[c['name'] for _, c in CASES])
def test_official_encode(source, case):
    options = case.get('options', {})
    assert toon.dumps(case['input'], **({'delimiter': options['delimiter']} if 'delimiter' in options else {}),
                      **({'indent_size': options['indentSize']} if 'indentSize' in options else {})) == case['expected']

@pytest.mark.parametrize('value,expected', [([], '[]'), ({'seeds': []}, 'seeds: []'),
    ({'n': 1234567.0}, 'n: 1234567'), ({'n': 'true'}, 'n: "true"'),
    ({'n': '42'}, 'n: "42"'), ({'n': '#c'}, 'n: "#c"'),
    ({'my-key': 1}, '"my-key": 1'), ({'n': float('inf')}, 'n: null')])
def test_corruption_regressions(value, expected):
    assert toon.dumps(value) == expected

DECODE_CASES = [(path.name, case) for path in sorted((Path(__file__).parent / 'fixtures/decode').glob('*.json'))
                for case in json.loads(path.read_text())['tests']]

@pytest.mark.parametrize('source,case', DECODE_CASES, ids=[c['name'] for _, c in DECODE_CASES])
def test_official_decode(source, case):
    options = case.get('options', {})
    kwargs = {'strict': options.get('strict', True), 'indent_size': options.get('indentSize', 2)}
    if case.get('shouldError') or 'error' in case:
        with pytest.raises(ValueError):
            toon.decode(case['input'], **kwargs)
    else:
        assert toon.decode(case['input'], **kwargs) == case['expected']

@pytest.mark.parametrize('source,case', CASES, ids=[c['name'] for _, c in CASES])
def test_official_encode_roundtrip(source, case):
    options = case.get('options', {})
    encoded = toon.encode(case['input'], delimiter=options.get('delimiter', ','), indent_size=options.get('indentSize', 2))
    assert toon.decode(encoded, indent_size=options.get('indentSize', 2)) == case['input']


def test_server_vendored_codec_is_identical():
    assert (ROOT / 'server/lampway_server/compute/toon_out.py').read_bytes() == (ROOT / 'src/scripts/mixar/modules/common/toon/codec.py').read_bytes()
