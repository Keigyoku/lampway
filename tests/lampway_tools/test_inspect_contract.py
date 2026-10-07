# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only observation is explicit, rather than a migration exception."""
import importlib.util
from pathlib import Path

from mixar.modules.lampway_tools import canon_door as D

ROOT = Path(__file__).resolve().parents[2]


def test_observe_is_an_explicit_registered_declaration():
    observation = getattr(D, 'OBSERVE', None)
    assert observation is not None, 'Q1 requires OBSERVE instead of NONE or LEGACY'
    D.validate_declaration(observation('reads raw or canonical assets without changing them'))


def test_inspect_schema_vendor_is_identical():
    client = ROOT / 'src/scripts/mixar/modules/lampway_tools/inspect/schema.py'
    server = ROOT / 'server/lampway_server/mcp_inspect_schema.py'
    assert client.read_bytes() == server.read_bytes()
