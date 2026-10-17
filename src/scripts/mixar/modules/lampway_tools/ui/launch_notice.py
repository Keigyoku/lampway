# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Human native-login disclosure: requests off-thread, confirmation on the main thread."""
import queue
import secrets
import threading
import textwrap

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from .. import human_gate
from .onboarding import iface_, n_

_READY = queue.Queue()
_PENDING = {}
_WORKING = [0]


def _tick():
    while not _READY.empty():
        try:
            _READY.get_nowait()()
        except Exception:
            # One stale UI callback must not stop delivery to the other owned requests.
            continue
    return .2 if _WORKING[0] else None


def _background(call, done):
    _WORKING[0] += 1
    def work():
        try:
            result, error = call(), None
        except Exception:
            result, error = None, iface_('The account notice or launch request failed; refresh and try again.')
        def publish():
            _WORKING[0] -= 1
            done(result, error)
        _READY.put(publish)
    try:
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=.2)
        threading.Thread(target=work, name='lampway-launch-notice', daemon=True).start()
    except Exception:
        _WORKING[0] -= 1
        done(None, iface_('The account notice request could not start; refresh and try again.'))


def confirm(notice, launch, done, validate=None):
    """Only opens a dialog. The server nonce is sent only by its explicit human execute."""
    ticket = secrets.token_hex(16)
    _PENDING[ticket] = (notice, launch, done, validate)
    try:
        result = bpy.ops.lampway.native_launch_confirm('INVOKE_DEFAULT', ticket=ticket)
    except Exception:
        result = {'CANCELLED'}
    if 'CANCELLED' in result:
        _PENDING.pop(ticket, None)
        done(None, iface_('The account notice dialog could not open; review the launch again.'))


def request(prepare, launch, done, validate=None):
    def prepared(notice, error):
        if error:
            done(None, error)
        elif validate is not None and not validate():
            done(None, iface_('The scene changed; review the launch again.'))
        elif not isinstance(notice, dict) or type(notice.get('required')) is not bool:
            done(None, iface_('The account notice response is invalid; review the launch again.'))
        elif notice['required']:
            confirm(notice, launch, done, validate)
        else:
            _background(lambda: launch(None), done)
    _background(prepare, prepared)


class LAMPWAY_OT_native_launch_confirm(Operator):
    bl_idname = 'lampway.native_launch_confirm'
    bl_label = 'Review your agent account'
    bl_options = {'INTERNAL'}
    ticket: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if human_gate.script_running() or self.ticket not in _PENDING:
            _PENDING.pop(self.ticket, None)
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        row = _PENDING.get(self.ticket)
        if not row:
            return
        notice = row[0]
        self.layout.label(text=notice['label'])
        self.layout.label(text=iface_(n_('Native login: {state}')).format(state=notice['login_state']), translate=False)
        if notice.get('account'):
            self.layout.label(text=iface_(n_('Account: {account}')).format(account=notice['account']), translate=False)
        for message in (notice['message'], notice.get('account_note') or '',
                        iface_(n_('Continue acknowledges this notice; it does not enable a route or change your login.'))):
            for line in textwrap.wrap(message, width=70):
                self.layout.label(text=line)

    def execute(self, context):
        if human_gate.script_running():
            _PENDING.pop(self.ticket, None)
            return {'CANCELLED'}
        row = _PENDING.pop(self.ticket, None)
        if not row:
            return {'CANCELLED'}
        notice, launch, done, validate = row
        if validate is not None and not validate():
            done(None, iface_('The scene changed; review the launch again.'))
            return {'CANCELLED'}
        _background(lambda: launch(notice['nonce']), done)
        return {'FINISHED'}

    def cancel(self, context):
        _PENDING.pop(self.ticket, None)
