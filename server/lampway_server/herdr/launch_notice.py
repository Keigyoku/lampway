# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""B5 human launch disclosure. No credential reads, account persistence or grants."""
import hashlib
import json
import re
from pathlib import Path
import secrets
import threading
import time

from .. import egress as E
from ..connections import files as CF


class NoticeRequired(PermissionError):
    pass


def operation(body):
    return hashlib.sha256(json.dumps({k: v for k, v in body.items()
                                     if k not in ('notice_request', 'notice_nonce')},
                                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Notices:
    def __init__(self, root):
        self.path = Path(root) / 'launch-notices' / 'ack.json'
        self.pending = {}
        self.lock = threading.RLock()

    def _read(self):
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return set()
        except (ValueError, UnicodeError):
            raise PermissionError('Retained launch acknowledgement is invalid; inspect it before retrying.') from None
        if (not isinstance(data, dict) or set(data) != {'version', 'harnesses'}
                or type(data['version']) is not int or data['version'] != 1
                or not isinstance(data['harnesses'], list)
                or len(data['harnesses']) > 256
                or any(not isinstance(n, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', n)
                       for n in data['harnesses'])):
            raise PermissionError('Retained launch acknowledgement is invalid; inspect it before retrying.')
        return set(data['harnesses'])

    def acknowledged(self, harness):
        return harness in self._read()

    def require(self, harness):
        if not self.acknowledged(harness):
            raise NoticeRequired('Review this harness\'s native account notice from your launch dialog first.')

    def prepare(self, ad, owner, signature):
        E.preflight(ad.route)  # Route off refuses BEFORE even a supported native status command.
        if self.acknowledged(ad.id):
            return {'required': False}
        # No status command means UNKNOWN, without invoking a substituted or guessed command.
        try:
            status = ad.login_state() if ad.status_argv else None
        except Exception:
            status = None  # Never expose arbitrary native command output through an exception.
        state = getattr(status, 'state', 'unknown')
        if state not in ('signed_in', 'signed_out', 'unknown'):
            state = 'unknown'
        account = getattr(status, 'account_label', None)
        if not isinstance(account, str) or not account or len(account) > 200 or not account.isprintable():
            account = None
        nonce = secrets.token_urlsafe(32)
        with self.lock:
            now = time.monotonic()
            self.pending = {k: v for k, v in self.pending.items() if v[3] > now}
            if len(self.pending) >= 256:
                raise PermissionError('Too many pending launch notices; finish or cancel the earlier launch.')
            self.pending[nonce] = (ad.id, owner, signature, now + 300)
        return {'required': True, 'nonce': nonce, 'harness': ad.id, 'label': ad.label,
                'login_state': state, 'account': account,
                'message': 'This harness talks to its vendor directly on its own native login and plan. '
                           'Lampway does not see or log that traffic and does not transfer credentials.',
                'account_note': None if account else 'Account identity unavailable; inspect this harness\'s own pane before sending a prompt.'}

    def admit(self, ad, owner, signature, nonce=None):
        E.preflight(ad.route)
        with self.lock:
            if nonce is not None:
                row = self.pending.pop(nonce, None) if isinstance(nonce, str) else None
                if row is None or row[:3] != (ad.id, owner, signature) or row[3] <= time.monotonic():
                    raise PermissionError('Launch notice expired, used or belongs to another operation; review it again.')
                if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', ad.id):
                    raise PermissionError('Invalid harness for launch acknowledgement.')
                # Re-read under the shared process lock; an independent server must not lose an acknowledgement.
                with CF.locked(self.path.with_suffix('.lock')):
                    harnesses = self._read()
                    harnesses.add(ad.id)
                    CF.atomic_write_json(self.path, {'version': 1, 'harnesses': sorted(harnesses)})
            else:
                self.require(ad.id)


def admission(cockpit, ad, request, body, origin):
    """Called by the existing human routes before any bind, files or launch."""
    notices = cockpit.launch_notices
    if origin != 'user':
        if 'notice_request' in body or 'notice_nonce' in body:
            raise PermissionError('Only your local user launch dialog can review or confirm this account notice.')
        E.preflight(ad.route)
        notices.require(ad.id)
        return None
    owner = hashlib.sha256(request.headers.get('authorization', '').encode()).hexdigest()
    from ..agent.server_tools import project_root
    signature = operation({'endpoint': request.url.path, 'project_root': str(project_root()),
                           'payload': operation(body)})
    if body.get('notice_request') is True:
        return {'notice': notices.prepare(ad, owner, signature)}
    notices.admit(ad, owner, signature, body.get('notice_nonce'))
    return None
