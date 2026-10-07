# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic surface checks, not real UE rendering acceptance."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

PATH = Path(__file__).resolve().parents[2] / 'scripts/lampway/ue_cube_generator_supplemental_probe.py'
SPEC = importlib.util.spec_from_file_location('cube_supplement', PATH)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def fake_ue():
    ue = SimpleNamespace(**{owner: SimpleNamespace(**{method: lambda *args: None for method in methods})
                            for owner, methods in P.REQUIRED.items()})
    properties = lambda: SimpleNamespace(get_editor_property=lambda key: 0)
    ue.PostProcessSettings = properties
    ue.Material = properties
    ue.MaterialExpressionVectorParameter = properties
    return ue


def test_missing_display_readback_is_refused_before_render():
    ue = fake_ue()
    del ue.RenderingLibrary.read_render_target_pixel
    result = P.probe(ue)
    assert not result['available']
    assert 'RenderingLibrary.read_render_target_pixel' in result['missing']


def test_complete_surface_still_does_not_claim_pixels():
    result = P.probe(fake_ue())
    assert result['available']
    assert 'does not prove' in result['note']


def test_missing_grading_override_is_refused():
    ue = fake_ue()
    def get_property(key):
        if key == 'override_color_gain_highlights':
            raise AttributeError(key)
        return 0
    ue.PostProcessSettings = lambda: SimpleNamespace(get_editor_property=get_property)
    result = P.probe(ue)
    assert not result['available']
    assert 'PostProcessSettings.override_color_gain_highlights' in result['missing']
