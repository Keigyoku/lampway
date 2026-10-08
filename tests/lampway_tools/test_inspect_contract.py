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


def test_nonmesh_object_detail_has_definitive_empty_layer_summary(monkeypatch):
    from types import SimpleNamespace
    from mixar.modules.lampway_tools import inspect as I
    from mixar.modules.lampway_tools.inspect import objects, layers

    camera = SimpleNamespace(name='Camera', type='CAMERA')
    scene = SimpleNamespace(name='Scene', unit_settings=SimpleNamespace(scale_length=1))
    monkeypatch.setattr(I.bpy, 'context', SimpleNamespace(scene=scene))
    monkeypatch.setattr(I, '_named', lambda *_: camera)
    monkeypatch.setattr(objects, 'detail', lambda *_: {'name': 'Camera', 'type': 'CAMERA'})
    monkeypatch.setattr(objects, 'canon', lambda *_: {'state': 'unstamped'})
    def forbid_mesh_paint_read(_):
        raise AssertionError('nonmesh object detail must not enter the mesh paint engine')
    monkeypatch.setattr(layers, 'measure', forbid_mesh_paint_read)

    result = I.run(view='object', name='Camera')
    assert result['ok'] and not result['skipped'], result
    assert result['data'].get('layers') == {'count': 0, 'top': None}, result
