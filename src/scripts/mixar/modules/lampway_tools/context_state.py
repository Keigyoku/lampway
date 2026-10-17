# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Context reads and writes run in workers; only take() publishes on the main thread."""
import threading

_LOCK = threading.Lock()
_INBOX = None
STATE = {'project': '', 'answer': None, 'error': '', 'inflight': False, 'operation': ''}


def reset():
    global _INBOX
    with _LOCK:
        _INBOX = None
        STATE.update(project='', answer=None, error='', inflight=False, operation='')


def _spawn(fn):
    threading.Thread(target=fn, daemon=True, name='lampway-context-settings').start()


def request(client_factory, project, values=None, reset_keys=None, spawn=None):
    """One operation at a time; writes contain only the user's explicit edits."""
    global _INBOX
    if not project:
        STATE['error'] = 'This file has no Lampway project: open a project, then Refresh Context'
        return False
    with _LOCK:
        if STATE['inflight']:
            return False
        if STATE['project'] != project:
            STATE['answer'] = None
        STATE.update(project=project, inflight=True, error='', operation='save' if values is not None or reset_keys is not None else 'load')
    def work():
        global _INBOX
        try:
            client = client_factory()
            answer = client.set_context(project, values=values, reset=reset_keys) if values is not None or reset_keys is not None else client.context(project)
            result = (project, answer, '')
        except Exception as exc:  # noqa: BLE001  (surface every refused or failed request)
            result = (project, None, str(exc) or exc.__class__.__name__)
        with _LOCK:
            _INBOX = result
    try:
        (spawn or _spawn)(work)
    except RuntimeError as exc:
        STATE.update(inflight=False, error=str(exc) or 'Could not start Context request')
        return False
    return True


def take():
    global _INBOX
    with _LOCK:
        result, _INBOX = _INBOX, None
        if result is None:
            return False
        STATE.update(inflight=False, operation='')
    project, answer, error = result
    if project == STATE['project']:
        STATE['error'] = error
        if answer is not None:
            STATE['answer'] = answer
    return True
