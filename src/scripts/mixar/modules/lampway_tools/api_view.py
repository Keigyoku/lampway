# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T2's JSON entry. Registration and OBSERVE declaration are owned by api.py."""
from .view import ViewError
from .settings import PathOutsideProject

ACTIONS = ('focus', 'screenshot', 'render_still', 'help')
HELP = ['lampway_view action=focus object=<name>', 'lampway_view action=screenshot',
        'lampway_view action=render_still']


def view(action=None, object=None, data=None, unhide=False, area='VIEW_3D', shot=True,
         max_bytes=750000, preset='current', out='renders/still.png', **unknown):
    """Frame a named object, capture a masked editor or start a still render. Pixels require the UI-control opt-in.
    Uses the session-bound window scene, restores selection and render settings, and never overwrites an output.
    A hidden target needs unhide=true (one undo step); a busy renderer refuses. No spend or runtime egress."""
    def refuse(code, message, help=None):
        return {'ok': False, 'code': code, 'error': message, 'help': help or ['lampway_view action=help']}
    if unknown:
        return refuse('unknown_argument', 'Unknown arguments: ' + ', '.join(sorted(unknown)))
    if action is not None and action not in ACTIONS:
        return refuse('bad_argument', 'action must be focus, screenshot, render_still or help')
    if type(max_bytes) is not int or not 50000 <= max_bytes <= 900000:
        return refuse('bad_argument', 'max_bytes must be an integer in 50000..900000')
    if type(unhide) is not bool or type(shot) is not bool:
        return refuse('bad_argument', 'unhide and shot must be booleans')
    if not isinstance(area, str) or not area or preset not in ('current', 'thumbnail'):
        return refuse('bad_argument', 'area must be an editor type; preset must be current or thumbnail')
    if any(value is not None and not isinstance(value, str) for value in (object, data)) or not isinstance(out, str):
        return refuse('bad_argument', 'object, data and out must be strings')
    if action == 'help':
        return {'action': 'help', 'tool': 'lampway_view', 'description': view.__doc__,
                'arguments': {'action': list(ACTIONS), 'object': 'focus: one of object/data', 'data': 'focus: datablock name',
                              'unhide': False, 'area': 'VIEW_3D or editor UI type or WINDOW', 'shot': True,
                              'max_bytes': '750000; 50000..900000', 'preset': 'current or thumbnail', 'out': 'renders/still.png'},
                'fields': {'home': ['tool', 'description', 'action', 'scene', 'editors', 'active_camera', 'last_capture', 'help'],
                           'focus': ['action', 'object', 'area', 'framed_bounds', 'unhidden', 'undo', 'image_path', 'image', 'help'],
                           'screenshot': ['action', 'area', 'image_path', 'image', 'help'],
                           'render_still': ['action', 'job', 'preset', 'help']},
                'refusals': ['hidden', 'no_area', 'render_in_progress', 'path_outside_project', 'ui_control_off', 'capture_busy'],
                'help': HELP}
    if action == 'focus' and bool(object) == bool(data):
        return refuse('bad_argument', 'focus needs exactly one of object or data')
    try:
        from .view import runtime
        return runtime.run(action, object, data, unhide, area, shot, max_bytes, preset, out)
    except ViewError as exc:
        return refuse(exc.code, str(exc), exc.help)
    except PathOutsideProject:
        return refuse('path_outside_project', 'out must stay inside the project root')
