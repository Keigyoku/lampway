# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Admission refuses oversized atomic work before hashing or geometry conversion."""
from types import SimpleNamespace
import time

from mixar.modules.lampway_tools import inspect as I
from mixar.modules.lampway_tools.inspect import cache


def test_large_mesh_budget_stops_before_hash(monkeypatch):
    mesh = SimpleNamespace(vertices=range(1_002_001), edges=range(3_002_000),
                           loops=range(6_000_000), polygons=range(2_000_000))
    ob = SimpleNamespace(name='TwoMillion', data=mesh)
    monkeypatch.setattr(I.bpy, 'context', SimpleNamespace(scene=SimpleNamespace(
        name='Synthetic', unit_settings=SimpleNamespace(scale_length=1))))
    monkeypatch.setattr(I, '_named', lambda *_: ob)
    entered = []
    def costly_hash(*args, **kwargs):
        entered.append(True)
        time.sleep(.25)  # Plant an indivisible call: a check afterwards is too late.
        return ('synthetic',)
    monkeypatch.setattr(cache, 'key', costly_hash)
    started = time.monotonic()
    result = I.run(view='mesh', name=ob.name, budget_ms=100)
    elapsed = time.monotonic() - started
    assert elapsed < .2, (elapsed, result)
    assert not entered, 'An oversized atomic hash must never start'
    assert result['ok'] and result['skipped'][0]['reason'] == 'budget_ms exceeded'
    assert any('budget_ms=<more>' in hint for hint in result['help'])


def test_budget_retry_preserves_measurement_arguments(monkeypatch):
    mesh = SimpleNamespace(vertices=range(1_002_001), edges=range(3_002_000),
                           loops=range(6_000_000), polygons=range(2_000_000))
    ob = SimpleNamespace(name='Two Million', data=mesh)
    monkeypatch.setattr(I.bpy, 'context', SimpleNamespace(scene=SimpleNamespace(
        name='Synthetic', unit_settings=SimpleNamespace(scale_length=1))))
    monkeypatch.setattr(I, '_named', lambda *_: ob)
    monkeypatch.setattr(I, '_render_busy', lambda: False)
    result = I.run(view='mesh', name=ob.name, deep=True, evaluated=True, budget_ms=100)
    hint = result['help'][-1]
    assert 'deep=true' in hint and 'evaluated=true' in hint, hint
    assert 'name="Two Million"' in hint and 'budget_ms=<more>' in hint, hint
