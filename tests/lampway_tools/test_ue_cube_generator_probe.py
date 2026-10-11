# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic capability proof only; actual UE capture remains an owner-run check."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

PATH = Path(__file__).resolve().parents[2] / 'scripts/lampway/ue_cube_generator_probe.py'
SPEC = importlib.util.spec_from_file_location('cube_probe', PATH)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


def fake_ue():
    ue = SimpleNamespace()
    for owner, methods in P.REQUIRED.items():
        setattr(ue, owner, SimpleNamespace(**{m: lambda *args: None for m in methods}))
    ue.SystemLibrary.get_engine_version = lambda: '5.8.2-56702186+++UE5+Release-5.8'
    ue.PostProcessSettings = lambda: SimpleNamespace(get_editor_property=lambda key: 0)
    return ue


def test_missing_engine_api_is_reported_instead_of_crashing():
    ue = fake_ue()
    del ue.SystemLibrary.get_engine_version
    result = P.probe(ue)
    assert result['available'] is False
    assert result['engine_version'] is None
    assert 'SystemLibrary.get_engine_version' in result['missing']


def test_complete_capabilities_do_not_claim_a_capture():
    result = P.probe(fake_ue())
    assert result['available'] is True
    assert result['engine_version'].startswith('5.8.2-')
    assert 'no captured cube' in result['note']


def test_missing_readback_is_a_specific_refusal(capsys):
    ue = fake_ue()
    del ue.RenderingLibrary.read_render_target_raw_pixel
    assert P.run(ue) == 1
    output = capsys.readouterr().out
    assert 'LAMPWAY_UE_CUBE_PROBE ' in output
    assert 'error:' in output and 'help[1]:' in output
    assert 'RenderingLibrary.read_render_target_raw_pixel' in output


def test_missing_postprocess_property_blocks_generation():
    ue = fake_ue()
    def get_property(key):
        if key == 'film_slope':
            raise AttributeError(key)
        return 0
    ue.PostProcessSettings = lambda: SimpleNamespace(get_editor_property=get_property)
    result = P.probe(ue)
    assert not result['available']
    assert 'PostProcessSettings.film_slope' in result['missing']


def test_probe_reports_the_display_capture_pipeline():
    result = P.probe(fake_ue())
    assert result['capture'] == 'SCS_FINAL_COLOR_LDR'
    assert result['format'] == 'RTF_RGBA8_SRGB'
    assert result['readback'] == 'RenderingLibrary.read_render_target_pixel'
    assert result['raw_control_capture'] == 'SCS_SCENE_COLOR_HDR'
    assert result['raw_control_readback'] == 'RenderingLibrary.read_render_target_raw_pixel(normalize=False)'


@pytest.mark.parametrize('owner,method', [
    ('RenderingLibrary', 'read_render_target_pixel'),
    ('TextureRenderTargetFormat', 'RTF_RGBA8_SRGB'),
])
def test_missing_display_pipeline_surface_refuses(owner, method):
    ue = fake_ue()
    # The baseline fake exposes only the old required surface.
    if hasattr(getattr(ue, owner), method):
        delattr(getattr(ue, owner), method)
    result = P.probe(ue)
    assert not result['available']
    assert owner + '.' + method in result['missing']
