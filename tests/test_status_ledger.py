# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ledger source identities and historical evidence cannot silently drift."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('status_ledger', Path(__file__).parents[1] / 'docs/gen_status_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)
SOURCE = '## wiki\n| contract | pri | status | lane | evidence | gap |\n|---|---|---|---|---|---|\n| private-test-identity | P0 | ORPHAN | | no implementation | complete mode pending |\n'


def fixture():
    rows = ledger.parse_source(SOURCE)
    supplied = [dict(rows[0], tools=['known_tool'], evid='retained implementation', live='S')]
    verdict = [dict(folder='wiki', contract='private-test-identity', verdict='WRONG', why='implementation exists')]
    return rows, supplied, verdict


def test_recount_preserves_identity_and_does_not_upgrade_sweep_to_live():
    _, supplied, verdict = fixture()
    a = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 8, 'mcp_tools': 3})
    assert a['rows'][0]['contract'] == 'private-test-identity'
    assert a['rows'][0]['rewritten_status'] == 'UNVERIFIED'
    assert a['rows'][0]['verification'] == 'current-complete-contract-not-verified'
    assert a['historical_verdict_counts'] == {'WRONG': 1}
    assert a['registry_counts'] == {'agent_tools': 8, 'mcp_tools': 3}
    public = ledger.public_report(a)
    assert 'ROW001' in public
    assert 'private-test-identity' not in public
    assert 'retained implementation' not in public


@pytest.mark.parametrize('plant', ['identity', 'gap', 'duplicate', 'verdict', 'bool-count'])
def test_recount_rejects_planted_source_or_evidence_drift(plant):
    _, supplied, verdict = fixture()
    source = SOURCE
    counts = {'agent_tools': 8, 'mcp_tools': 3}
    if plant == 'identity':
        verdict[0]['contract'] = 'invented'
    elif plant == 'gap':
        supplied[0]['gap'] = 'erased caveat'
    elif plant == 'duplicate':
        source += '| private-test-identity | P0 | BUILT | | | |\n'
    elif plant == 'verdict':
        verdict[0]['verdict'] = 'PASS'
    else:
        counts['agent_tools'] = True
    with pytest.raises(ValueError):
        ledger.recount(source, supplied, verdict, counts)


def test_current_evidence_checks_actual_files_and_registry_not_old_booleans(tmp_path):
    module = tmp_path / 'server/lampway_server/example.py'
    module.parent.mkdir(parents=True)
    module.write_text('implementation = True\n')
    row = {'tools': ['present', 'removed'], 'cites': [('SV', 'example.py', False),
           ('SV', 'missing.py', True)], 'evid': ''}
    scan = ledger.current_evidence(row, tmp_path, {'present'}, {'present'})
    assert scan['present_tools'] == ['present']
    assert scan['missing_tools'] == ['removed']
    assert list(scan['files_sha256']) == ['server/lampway_server/example.py']
    _, supplied, verdict = fixture()
    a = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 8, 'mcp_tools': 3},
                       lambda _: scan)
    assert a['rows'][0]['rewritten_status'] == 'UNVERIFIED'
    module.unlink()
    scan = ledger.current_evidence(row, tmp_path, set(), set())
    a = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 0, 'mcp_tools': 0},
                       lambda _: scan)
    assert a['rows'][0]['rewritten_status'] == 'UNVERIFIED'


def test_current_evidence_cannot_follow_citation_outside_repository(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (tmp_path / 'private.py').write_text('private content\n')
    row = {'tools': [], 'cites': [('T', '../private.py', True)], 'evid': '../private.py'}
    assert ledger.current_evidence(row, repo, set(), set())['files_sha256'] == {}


def test_manual_review_must_match_original_identity_and_record_gap():
    _, supplied, verdict = fixture()
    audit = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 8, 'mcp_tools': 3})
    review = dict(id='ROW001', contract='wiki/private-test-identity',
                  current_measured_capability='tested exact behavior', remaining_gap='full native repeat',
                  full_contract_verified=False)
    ledger.apply_manual_evidence(audit, [review])
    assert audit['rows'][0]['manual_review'] == review
    with pytest.raises(ValueError, match='identity'):
        ledger.apply_manual_evidence(audit, [dict(review, contract='invented')])
    with pytest.raises(ValueError, match='gap'):
        ledger.apply_manual_evidence(audit, [dict(review, remaining_gap='')])


def test_private_output_cannot_publish_inside_repository_or_symlink(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    with pytest.raises(ValueError, match='outside'):
        ledger.require_private_output(repo, repo / 'docs/private')
    alias = tmp_path / 'alias'
    alias.symlink_to(repo, target_is_directory=True)
    with pytest.raises(ValueError, match='outside'):
        ledger.require_private_output(repo, alias / 'private')
    ledger.require_private_output(repo, tmp_path / 'external')


def test_manual_source_hash_detects_a_changed_implementation(tmp_path):
    _, supplied, verdict = fixture()
    audit = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 8, 'mcp_tools': 3})
    path = tmp_path / 'implementation.py'
    path.write_text('first implementation\n')
    digest = ledger.hashlib.sha256(path.read_bytes()).hexdigest()
    review = dict(id='ROW001', contract='wiki/private-test-identity',
                  current_measured_capability='tested exact behavior', remaining_gap='native repeat',
                  source_sha256={'implementation.py': digest})
    ledger.apply_manual_evidence(audit, [review], tmp_path)
    path.write_text('changed implementation\n')
    with pytest.raises(ValueError, match='changed'):
        ledger.apply_manual_evidence(audit, [review], tmp_path)


def test_complete_recount_rejects_pending_review_and_changed_original_spec(tmp_path):
    _, supplied, verdict = fixture()
    audit = ledger.recount(SOURCE, supplied, verdict, {'agent_tools': 8, 'mcp_tools': 3})
    with pytest.raises(ValueError, match='reconciliation'):
        ledger.require_complete_reviews(audit)
    path = tmp_path / 'original.md'
    path.write_text('original contract clause\n')
    review = dict(id='ROW001', contract='wiki/private-test-identity', classification='PARTIAL',
                  current_measured_capability='tested exact behavior', remaining_gap='native repeat',
                  spec_path=str(path), spec_sha256=ledger.hashlib.sha256(path.read_bytes()).hexdigest(),
                  spec_refs=[{'section': 'original clause', 'line': 1}])
    ledger.apply_manual_evidence(audit, [review])
    ledger.require_complete_reviews(audit)
    review['audit_completion'] = 'PENDING full-text review'
    with pytest.raises(ValueError, match='reconciliation'):
        ledger.require_complete_reviews(audit)
    review.pop('audit_completion')
    path.write_text('silently changed contract\n')
    with pytest.raises(ValueError, match='specification evidence changed'):
        ledger.require_complete_reviews(audit)
