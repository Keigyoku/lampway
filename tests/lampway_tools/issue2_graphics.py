# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Graphics requests for the disposable GUI; hardware proof rejects CPU fallback."""
SOFTWARE_RENDERERS = ('llvmpipe', 'softpipe', 'software', 'swiftshader', 'swrast')


def prepare_environment(inherited):
    result = dict(inherited)
    requested = result.get('LAMPWAY_VIEW_SOFTWARE_GL', '1')
    if requested not in ('0', '1'):
        raise ValueError('LAMPWAY_VIEW_SOFTWARE_GL must be 0 or 1')
    result['LAMPWAY_VIEW_SOFTWARE_GL'] = requested
    result['LIBGL_ALWAYS_SOFTWARE'] = requested
    # The host assigns a fresh isolated display after Xvfb starts.
    result.pop('DISPLAY', None)
    result.pop('WAYLAND_DISPLAY', None)
    return result


def validate_renderer(requested, renderer):
    if not str(renderer).strip():
        raise ValueError('The GUI did not report an actual graphics renderer')
    if requested == '0' and any(marker in renderer.casefold() for marker in SOFTWARE_RENDERERS):
        raise ValueError(f'Requested hardware GL but actual renderer is software: {renderer}')
    return 'hardware' if requested == '0' else 'software'
