# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded AXI intake retains semantic output while using the paired PR4 codec."""
import importlib
import sys
from pathlib import Path
import pytest
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'src/scripts'))
sys.path.insert(0, str(REPO / 'server'))

@pytest.mark.parametrize('module,codec', [('mixar.modules.lampway_tools.axi', 'mixar.modules.common.toon.codec'),
                                        ('lampway_server.studios.axi', 'lampway_server.compute.toon_out')])
def test_axi_delegates_to_unchanged_authoritative_codec(module, codec):
    ax, shared = importlib.import_module(module), importlib.import_module(codec)
    assert ax.encode is shared.encode and ax.normalize is shared.normalize
    assert ax._num(9007199254740993) == '9007199254740993'
    assert ax._s(float('nan')) == 'null' and ax._s(float('-inf')) == 'null'
    assert ax._s('12') == '"12"'

@pytest.mark.parametrize('module', ['mixar.modules.lampway_tools.axi', 'lampway_server.studios.axi'])
def test_canonical_help_and_newline_contract_preserves_decoded_commands(module, capsys):
    ax = importlib.import_module(module)
    from lampway_server.compute.toon_out import encode, decode
    commands = ['tool x <id>', 'tool y "two words"']
    ax.helps(commands)
    actual = capsys.readouterr().out
    data = {'help': [f'Run `{cmd}`' for cmd in commands]}
    assert actual == encode(data)
    assert decode(actual) == data
    assert not actual.endswith('\n')
    # Expanded primitive-list syntax remains legal input; the migration adopts
    # the shared encoder's canonical output, not a new grammar refusal.
    legacy = 'help[2]:\n  - Run `tool x <id>`\n  - "Run `tool y \\"two words\\"`"\n'
    assert decode(legacy) == data

@pytest.mark.parametrize('module', ['mixar.modules.lampway_tools.axi', 'lampway_server.studios.axi'])
def test_empty_count_missing_cells_and_quoted_keys_keep_their_data(module, capsys):
    ax = importlib.import_module(module)
    from lampway_server.compute.toon_out import decode
    ax.table('empty', [], ['id'])
    ax.table('rows', [{'id': 'a', 'n': 3}, {'id': 'b'}], ['id', 'n'], total=40)
    ax.kv({'line\n': 'a:b', 'nested': {'passed': False}})
    actual = capsys.readouterr().out
    assert 'empty: []' in actual and '[0]:' not in actual
    assert decode(actual) == {'empty': [], 'count': '2 of 40 total', 'rows': [{'id': 'a', 'n': 3}, {'id': 'b'}],
                              'line\n': 'a:b', 'nested': {'passed': False}}

@pytest.mark.parametrize('module', ['mixar.modules.lampway_tools.axi', 'lampway_server.studios.axi'])
def test_unknown_values_remain_null_without_serialization_hooks(module, capsys):
    import numpy as np
    ax = importlib.import_module(module)
    from lampway_server.compute.toon_out import decode
    class Hostile:
        def __str__(self):
            pytest.fail('Unsupported host values cannot invoke string hooks')
        def tolist(self):
            pytest.fail('Unsupported host values cannot invoke array hooks')
    ax.kv({'unsupported': Hostile(), 'array': np.array([1, 2])})
    assert decode(capsys.readouterr().out) == {'unsupported': None, 'array': None}

def test_paired_codecs_are_byte_identical_and_schema_preserving():
    assert (REPO / 'src/scripts/mixar/modules/common/toon/codec.py').read_bytes() == (REPO / 'server/lampway_server/compute/toon_out.py').read_bytes()
