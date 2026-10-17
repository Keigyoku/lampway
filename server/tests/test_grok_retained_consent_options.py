# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Malformed persisted Grok consent is refused without defaults or authorization changes."""
import pytest
from lampway_server import capabilities as CAP
from lampway_server.connections import files as CF

@pytest.mark.parametrize('options', [[1], 'x', 7, True, None, [], '', False, 0])
def test_retained_non_dict_grok_consent_options_fail_closed(tmp_path, options):
    store = CAP.Store(tmp_path / 'state')
    CF.ensure_dir(store.state_dir)
    record = {'global': {'grok.worker_compat': {'enabled': True, 'options': options}}, 'projects': {}, 'proposals': []}
    CF.atomic_write_json(store._path, record)
    original = store._path.read_bytes()
    on, why = store.effective('grok.worker_compat', '/project')
    assert on is False and 'renewed human consent' in why
    assert store._path.read_bytes() == original
    assert not store.effective('swarm', '/project')[0]
