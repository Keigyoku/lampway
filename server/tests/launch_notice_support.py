# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit prior human disclosure for downstream launch fixtures, never a production guard bypass."""
import pytest
from lampway_server.connections import files as CF
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr.host import Cockpit

def _retain_disclosure(monkeypatch):
    """Install minimal prior disclosure only in the requesting test's owned cockpit root."""
    original = Cockpit.__init__
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        path = self.launch_notices.path
        if not path.exists():
            CF.atomic_write_json(path, {'version': 1, 'harnesses': list(HN.ids())})
    monkeypatch.setattr(Cockpit, '__init__', initialize)


@pytest.fixture(autouse=True)
def prior_human_disclosure(monkeypatch):
    """Entire downstream suites; fresh admission lives in test_byoa_launch_notice."""
    _retain_disclosure(monkeypatch)


@pytest.fixture
def retained_human_disclosure(monkeypatch):
    """Explicit dependency for post-disclosure tests in a module with fresh refusal cases."""
    _retain_disclosure(monkeypatch)
