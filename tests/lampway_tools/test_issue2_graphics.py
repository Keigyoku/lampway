# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Requested graphics mode must survive environment setup and match the driver."""
import pytest
from issue2_graphics import prepare_environment, validate_renderer


@pytest.mark.parametrize('requested,expected', [(None, '1'), ('1', '1'), ('0', '0')])
def test_graphics_mode_overrides_inherited_software_flag_and_display(requested, expected):
    inherited = {'LIBGL_ALWAYS_SOFTWARE': '1', 'DISPLAY': ':user-desktop', 'WAYLAND_DISPLAY': 'wayland-owner'}
    if requested is not None:
        inherited['LAMPWAY_VIEW_SOFTWARE_GL'] = requested
    prepared = prepare_environment(inherited)
    assert prepared['LIBGL_ALWAYS_SOFTWARE'] == expected
    assert prepared['LAMPWAY_VIEW_SOFTWARE_GL'] == expected
    assert 'DISPLAY' not in prepared and 'WAYLAND_DISPLAY' not in prepared
    assert inherited['DISPLAY'] == ':user-desktop'


@pytest.mark.parametrize('renderer', ['llvmpipe (LLVM 19)', 'softpipe', 'Software Rasterizer', 'SwiftShader'])
def test_hardware_mode_refuses_software_fallback(renderer):
    with pytest.raises(ValueError, match='hardware.*software'):
        validate_renderer('0', renderer)


def test_hardware_renderer_and_default_software_mode_are_supported():
    assert validate_renderer('0', 'NVIDIA GeForce RTX 4090') == 'hardware'
    assert validate_renderer('1', 'llvmpipe (LLVM 19)') == 'software'


def test_unknown_requested_mode_is_not_silently_treated_as_hardware():
    with pytest.raises(ValueError, match='0 or 1'):
        prepare_environment({'LAMPWAY_VIEW_SOFTWARE_GL': 'maybe'})
