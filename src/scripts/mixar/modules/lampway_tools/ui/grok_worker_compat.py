# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-owned Grok worker compatibility: disclosure and explicit human consent only."""
import secrets
import copy
import re
import textwrap

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from .. import capabilities_client, capabilities_state as state, human_gate
from . import launch_notice
from .onboarding import iface_, n_

CAPABILITY = 'grok.worker_compat'
CONSENT_VERSION = 1
CLIENT_FACTORY = lambda: capabilities_client.CapabilitiesClient()
_PENDING = {}
_ERROR = ''


def _scope():
    return state.STATE['project'], state.write_project()


def _payload(row):
    detail = row.get('worker_compat') if isinstance(row, dict) else None
    if (not isinstance(detail, dict) or type(detail.get('consent_version')) is not int
            or detail['consent_version'] != CONSENT_VERSION
            or not isinstance(detail.get('effects_sha256'), str)
            or re.fullmatch(r'[0-9a-f]{64}', detail['effects_sha256']) is None
            or not isinstance(detail.get('warning'), str) or not detail['warning'].strip()
            or not isinstance(detail.get('effects'), list) or not detail['effects']
            or not all(isinstance(item, str) and item.strip() for item in detail['effects'])
            or not isinstance(detail.get('qualification'), str) or not detail['qualification'].strip()
            or type(detail.get('ready')) is not bool or not isinstance(detail.get('reason'), str)):
        raise ValueError(n_('Refresh Agent preferences: this server cannot describe Grok worker compatibility safely'))
    return detail


def _row():
    return next((r for r in state.STATE['rows'] if r.get('id') == CAPABILITY), {})


def _redraw():
    for window in getattr(bpy.context.window_manager, 'windows', ()):
        for area in window.screen.areas:
            area.tag_redraw()
        refresh = getattr(window, 'mixar_refresh_popups', None)
        if refresh is not None:
            refresh()


def _failed(message):
    global _ERROR
    _ERROR = str(message)
    _redraw()


def _review(kind, proceed=None, validate=None, failed=None):
    if human_gate.script_running():
        return
    global _ERROR
    _ERROR = ''
    project, write_scope = _scope()
    def report_failure(message):
        _failed(message)
        if failed is not None:
            failed(str(message))
    def prepared(listing, error):
        if error:
            report_failure(error)
            return
        if human_gate.script_running() or _scope() != (project, write_scope) or (validate and not validate()):
            report_failure(n_('The project or scene changed: review Grok again'))
            return
        try:
            row = next(r for r in listing['capabilities'] if r.get('id') == CAPABILITY)
            detail = copy.deepcopy(_payload(row))
        except (KeyError, TypeError, StopIteration, ValueError) as exc:
            report_failure(str(exc) or n_('Refresh Agent preferences before reviewing Grok'))
            return
        state.update(listing)
        ticket = secrets.token_hex(16)
        _PENDING[ticket] = {'kind': kind, 'project': project, 'scope': write_scope,
                            'detail': detail, 'proceed': proceed, 'validate': validate}
        try:
            result = bpy.ops.lampway.grok_worker_compat_review('INVOKE_DEFAULT', ticket=ticket)
        except Exception:
            result = {'CANCELLED'}
        if 'CANCELLED' in result:
            _PENDING.pop(ticket, None)
            report_failure(n_('The Grok review could not open; try again from Agent preferences'))
    launch_notice._background(lambda: CLIENT_FACTORY().capabilities(project or None), prepared)


def review_enable():
    _review('enable')


def review_main(proceed, validate, failed=None):
    # Selecting MAIN never enables compatibility and always reviews the worker-only effects.
    _review('main', proceed, validate, failed)


def _valid(record):
    if not state.STATE['ok'] or state.STATE['inflight'] or _scope() != (record['project'], record['scope']) or (record['validate'] and not record['validate']()):
        return False
    try:
        return _payload(_row()) == record['detail']
    except ValueError:
        return False


def _note(layout, text, icon='NONE', *, translate=True):
    for index, line in enumerate(textwrap.wrap(iface_(text) if translate else text, width=70)):
        layout.label(text=line, icon=icon if index == 0 else 'NONE', translate=False)


def draw_status(layout, row):
    if _ERROR:
        _note(layout, _ERROR, 'ERROR')
    try:
        detail = _payload(row)
    except ValueError as exc:
        _note(layout, str(exc), 'ERROR')
        return
    _note(layout, detail['warning'], 'ERROR', translate=False)
    for effect in detail['effects']:
        _note(layout, effect, translate=False)
    _note(layout, detail['qualification'], 'INFO', translate=False)
    if not detail['ready']:
        if detail['reason']:
            _note(layout, detail['reason'], 'ERROR', translate=False)
        else:
            _note(layout, n_('Grok worker execution is unavailable until qualification'), 'ERROR')


class LAMPWAY_OT_grok_worker_compat_open(Operator):
    """Review worker compatibility; MAIN selection does not enable it"""
    bl_idname = 'lampway.grok_worker_compat_open'
    bl_label = 'Configure Grok workers'

    def execute(self, context):
        if human_gate.script_running():
            return {'CANCELLED'}
        review_enable()
        return {'FINISHED'}


class LAMPWAY_OT_grok_worker_compat_review(Operator):
    bl_idname = 'lampway.grok_worker_compat_review'
    bl_label = 'Review Grok worker compatibility'
    bl_options = {'INTERNAL'}
    ticket: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        record = _PENDING.get(self.ticket)
        if human_gate.script_running() or not record or not _valid(record):
            _PENDING.pop(self.ticket, None)
            return {'CANCELLED'}
        text = iface_(n_('Enable worker compatibility')) if record['kind'] == 'enable' else iface_(n_('Continue with native MAIN'))
        return context.window_manager.invoke_props_dialog(self, width=640, confirm_text=text)

    def draw(self, context):
        record = _PENDING.get(self.ticket)
        if not record:
            return
        _note(self.layout, n_('Grok MAIN uses its normal native configuration. This switch changes only Grok swarm workers.'))
        draw_status(self.layout, {'worker_compat': record['detail']})
        _note(self.layout, n_('This does not enable a network route, transfer a login, or qualify worker execution.'))
        if record['kind'] == 'main':
            _note(self.layout, n_('Continue selects native MAIN without enabling worker compatibility.'))
            self.layout.operator('lampway.grok_worker_compat_open', text='Configure workers separately')
        else:
            _note(self.layout, n_('Enable applies to this project only.') if record['scope'] else n_('Enable applies to every project.'))

    def execute(self, context):
        record = _PENDING.pop(self.ticket, None)
        if human_gate.script_running() or not record:
            return {'CANCELLED'}
        if not _valid(record):
            self.report({'ERROR'}, iface_('The project, scene or disclosure changed: review Grok again'))
            return {'CANCELLED'}
        if record['kind'] == 'main':
            record['proceed']()
            return {'FINISHED'}
        def saved(answer, error):
            from . import capabilities
            if error:
                _failed(error)
            elif _scope() == (record['project'], record['scope']):
                state.merge_row(answer)
            capabilities.request_refresh()
            _redraw()
        launch_notice._background(lambda: CLIENT_FACTORY().set_capability(
            CAPABILITY, enabled=True, options={'consent_version': CONSENT_VERSION,
                'effects_sha256': record['detail']['effects_sha256']}, project=record['scope']), saved)
        return {'FINISHED'}

    def cancel(self, context):
        _PENDING.pop(self.ticket, None)


classes = (LAMPWAY_OT_grok_worker_compat_open, LAMPWAY_OT_grok_worker_compat_review)
