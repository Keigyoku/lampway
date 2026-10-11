# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic surface checks, not real UE rendering acceptance."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

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
    ue.TextureRenderTarget2D = properties
    ue.SceneCaptureComponent2D = properties
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


def test_supplement_reports_explicit_srgb_display_route():
    result = P.probe(fake_ue())
    assert result['capture'] == 'SCS_FINAL_COLOR_LDR'
    assert result['format'] == 'RTF_RGBA8_SRGB'
    assert result['readback'] == 'RenderingLibrary.read_render_target_pixel'


@pytest.mark.parametrize('owner,field', [
    ('TextureRenderTarget2D', 'srgb'),
    ('TextureRenderTarget2D', 'render_target_format'),
    ('TextureRenderTarget2D', 'target_gamma'),
    ('TextureRenderTarget2D', 'use_legacy_gamma'),
    ('TextureRenderTarget2D', 'size_x'),
    ('TextureRenderTarget2D', 'size_y'),
    ('SceneCaptureComponent2D', 'post_process_blend_weight'),
    ('SceneCaptureComponent2D', 'capture_every_frame'),
    ('SceneCaptureComponent2D', 'capture_on_movement'),
])
def test_missing_capture_property_is_refused(owner, field):
    ue = fake_ue()
    def get_property(key):
        if key == field:
            raise AttributeError(key)
        return 0
    setattr(ue, owner, lambda: SimpleNamespace(get_editor_property=get_property))
    result = P.probe(ue)
    assert not result['available']
    assert owner + '.' + field in result['missing']


def test_missing_srgb_format_is_refused():
    ue = fake_ue()
    if hasattr(ue.TextureRenderTargetFormat, 'RTF_RGBA8_SRGB'):
        del ue.TextureRenderTargetFormat.RTF_RGBA8_SRGB
    result = P.probe(ue)
    assert not result['available']
    assert 'TextureRenderTargetFormat.RTF_RGBA8_SRGB' in result['missing']


def test_missing_same_capture_raw_readback_is_refused():
    ue = fake_ue()
    del ue.RenderingLibrary.read_render_target_raw_pixel
    result = P.probe(ue)
    assert not result['available']
    assert 'RenderingLibrary.read_render_target_raw_pixel' in result['missing']


@pytest.mark.parametrize('owner', ['TextureRenderTarget2D', 'SceneCaptureComponent2D'])
def test_capture_property_constructor_failure_is_refused(owner):
    ue = fake_ue()
    def unavailable():
        raise RuntimeError('unavailable')
    setattr(ue, owner, unavailable)
    result = P.probe(ue)
    assert not result['available']
    assert owner + '.constructor' in result['missing']


@pytest.mark.parametrize('owner', ['TextureRenderTarget2D', 'SceneCaptureComponent2D'])
def test_missing_capture_property_owner_is_refused(owner):
    ue = fake_ue()
    delattr(ue, owner)
    result = P.probe(ue)
    assert not result['available']
    assert owner in result['missing']
