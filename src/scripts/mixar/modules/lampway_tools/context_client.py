# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bearer transport for project Hermes settings; no provider calls or client defaults."""
from urllib.parse import urlencode

from .studio_client import StudioClient


class ContextClient(StudioClient):
    def context(self, project):
        return self._call('GET', '/app/agent/context?' + urlencode({'project': project}), timeout=5)

    def set_context(self, project, values=None, reset=None):
        body = {'project': project}
        if values is not None:
            body['values'] = dict(values)
        if reset is not None:
            body['reset'] = list(reset)
        return self._call('PUT', '/app/agent/context', body, timeout=5)
