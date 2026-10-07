# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Recount an authorized external ledger without publishing its identities.

The supplied historical verdict is evidence, not current acceptance verification.
Current classification requires a manual specification/code/test reconciliation;
source claims and gaps remain private. Registry counts always come from code.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

FOLDERS = ('mixar_docs', 'wiki', 'resources', 'shelf', 'generation', 'prompts',
           'studios', 'asset_library', 'mrmak', 'cloud', 'client_facelift')
VERDICTS = {'OK', 'WRONG', 'FAILS-LIVE', 'PART-WRONG', 'UNVERIFIED'}


def parse_source(text):
    rows = []
    folder = None
    for line, textline in enumerate(text.splitlines(), 1):
        if textline.startswith('## '):
            folder = textline[3:].strip()
        if folder not in FOLDERS or not textline.startswith('| '):
            continue
        cells = [c.strip() for c in textline.strip().strip('|').split('|')]
        if cells[0] == 'contract':
            continue
        if len(cells) != 6:
            raise ValueError('malformed contract row')
        rows.append(dict(zip(('contract', 'pri', 'status', 'lane', 'evidence', 'gap'), cells),
                         folder=folder, line=line))
    keys = [(r['folder'], r['contract']) for r in rows]
    if not rows or len(keys) != len(set(keys)):
        raise ValueError('empty or duplicate contract inventory')
    return rows


def current_evidence(row, repo, names, offered):
    """Verify named code locations and tools, without inferring whole-contract success."""
    roots = {'SV': repo / 'server/lampway_server',
             'LT': repo / 'src/scripts/mixar/modules/lampway_tools', 'T': repo}
    files = {}
    for prefix, location, _old_exists in row.get('cites', []):
        root = roots.get(prefix)
        if root is None:
            continue
        path = root / location
        if path.is_file() and path.resolve().is_relative_to(repo.resolve()):
            files[str(path.relative_to(repo))] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Manual route/module evidence often has no formal citation triple.
    for location in re.findall(r'[A-Za-z0-9_./-]+\.py', row.get('evid', '')):
        for root in roots.values():
            path = root / location
            if path.is_file() and path.resolve().is_relative_to(repo.resolve()):
                files[str(path.relative_to(repo))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(present_tools=sorted(set(row['tools']) & names),
                missing_tools=sorted(set(row['tools']) - names),
                offered_tools=sorted(set(row['tools']) & offered), files_sha256=files)


def require_private_output(repo, destination):
    if destination.resolve().is_relative_to(repo.resolve()):
        raise ValueError('private ledger output must stay outside the repository')


def recount(source, supplied, verdicts, registry_counts, evidence_scan=None):
    rows = parse_source(source)
    keys = [(r['folder'], r['contract']) for r in rows]
    for data in (supplied, verdicts):
        other = [(r['folder'], r['contract']) for r in data]
        if keys != other:
            raise ValueError('source/recount identity or order mismatch')
    if set(registry_counts) != {'agent_tools', 'mcp_tools'} or any(
        type(n) is not int or n < 0 for n in registry_counts.values()
    ):
        raise ValueError('invalid generated registry counts')
    out = []
    for index, (row, evidence, verdict) in enumerate(zip(rows, supplied, verdicts), 1):
        if any(row[k] != evidence[k] for k in row):
            raise ValueError('source/recount content mismatch')
        v = verdict['verdict']
        if v not in VERDICTS:
            raise ValueError('unknown supplied verdict')
        scan = evidence_scan(evidence) if evidence_scan else None
        # Historical verdicts do not become present-day implementation claims.
        status = 'UNVERIFIED'
        out.append(dict(row, id=f'ROW{index:03d}', rewritten_status=status,
                        historical_verdict=v, historical_reason=verdict['why'],
                        supplied_evidence=evidence, current_evidence=scan,
                        verification='current-complete-contract-not-verified',
                        next_action='Verify the complete original contract and its retained gaps on the integrated candidate; historical route/refusal/sweep evidence is insufficient.'))
    return dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                row_count=len(out), registry_counts=registry_counts,
                original_status_counts=dict(Counter(r['status'] for r in out)),
                historical_verdict_counts=dict(Counter(r['historical_verdict'] for r in out)),
                rewritten_status_counts=dict(Counter(r['rewritten_status'] for r in out)),
                rows=out)


def apply_manual_evidence(audit, manual, repo=None):
    """Retain reviewed contract-specific capability/gap evidence by original ordinal."""
    indexed = {r['id']: r for r in audit['rows']}
    seen = set()
    for review in manual:
        identity = review['id']
        if identity not in indexed or identity in seen:
            raise ValueError('unknown or duplicate manual row')
        seen.add(identity)
        row = indexed[identity]
        if review['contract'] != row['folder'] + '/' + row['contract']:
            raise ValueError('manual contract identity mismatch')
        if not review.get('current_measured_capability') or not review.get('remaining_gap'):
            raise ValueError('manual capability and remaining gap required')
        if repo is not None:
            if not review.get('source_sha256'):
                raise ValueError('manual source hashes required')
            for location, digest in review['source_sha256'].items():
                path = repo / location
                if not path.resolve().is_relative_to(repo.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('manual source evidence changed or escaped repository')
        status = review.get('classification', 'PARTIAL')
        if status not in {'BUILT', 'PARTIAL', 'WAITING', 'FOLDED', 'ORPHAN', 'IN-LANE', 'UNVERIFIED'}:
            raise ValueError('unknown manual classification')
        row['manual_review'] = review
        row['rewritten_status'] = status
    audit['rewritten_status_counts'] = dict(Counter(r['rewritten_status'] for r in audit['rows']))


def public_report(audit):
    header = ['<!-- SPDX-' + 'FileCopyrightText: 2026 Lampway contributors -->',
              '<!-- SPDX-' + 'License-Identifier: GPL-3.0-or-later -->', '',
              '# Authorized ledger recount', '',
              f"Source SHA256: `{audit['source_sha256']}`. {audit['row_count']} original contract rows, in source order. Private identities and evidence remain in the authorized external ledger.", '',
              f"Generated registry counts: {audit['registry_counts']['agent_tools']} agent tools; {audit['registry_counts']['mcp_tools']} MCP tools.", '',
              'Historical verdict counts: ' + json.dumps(audit['historical_verdict_counts'], sort_keys=True) + '.', '',
              'Rewritten status counts: ' + json.dumps(audit['rewritten_status_counts'], sort_keys=True) + '.', '',
              'Each row records current named tools and cited/manual module hashes privately. Classification comes from its manual specification/code/test reconciliation, never from module or registry presence; rows without that review remain UNVERIFIED. Historical OK is not current acceptance. BUILT means implemented and tested within its retained scope; the per-row gap/verification record remains authoritative for live or full-contract claims. A route hit, refusal or sweep alone does not close a live contract. Additional shelf/runbook/reference tables are outside the original 231-row denominator and remain unchanged in the private source.', '',
              'Regenerate with [gen_status_ledger.py](../gen_status_ledger.py), providing the authorized source directory and an external private output directory. The registry header is obtained from the running repository helper, not the historical registry export.', '',
              '| Row | Source line | Original class | Historical verdict | Rewritten class | Current tools / files | Manual capability/gap review | Current full verification |',
              '|---|---:|---|---|---|---|---|---|']
    for r in audit['rows']:
        scan = r.get('current_evidence') or {}
        counts = f"{len(scan.get('present_tools', []))} / {len(scan.get('files_sha256', {}))}"
        reviewed = 'retained privately' if r.get('manual_review') else 'pending'
        header.append(f"| {r['id']} | {r['line']} | {r['status']} | {r['historical_verdict']} | {r['rewritten_status']} | {counts} | {reviewed} | pending |")
    return '\n'.join(header) + '\n'


def require_complete_reviews(audit):
    """A provisional placeholder is not a completed contract reconciliation."""
    for row in audit['rows']:
        review = row.get('manual_review') or {}
        if (not review.get('spec_refs') or not review.get('spec_sha256')
                or row['rewritten_status'] == 'UNVERIFIED'
                or 'PENDING' in review.get('audit_completion', '')):
            raise ValueError('complete ledger requires a specification reconciliation for every original row')
        path = Path(review.get('spec_path', ''))
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != review['spec_sha256']:
            raise ValueError('original specification evidence changed or is missing')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', required=True, type=Path)
    p.add_argument('--private-output-dir', required=True, type=Path)
    p.add_argument('--public-output', required=True, type=Path)
    p.add_argument('--manual-evidence', action='append', default=[], type=Path)
    p.add_argument('--require-complete-reviews', action='store_true')
    args = p.parse_args()
    from lampway_server.agent_files.generate import registry_counts, registry
    from lampway_server.mcp import offered_tools
    repo = Path(__file__).resolve().parents[1]
    require_private_output(repo, args.private_output_dir)
    names = {r['name'] for r in registry()}
    offered = {r.name for r in offered_tools()}
    source = (args.source_dir / 'STATUS.md').read_text()
    supplied = json.loads((args.source_dir / 'recount.json').read_text())
    with (args.source_dir / 'recount.tsv').open() as f:
        verdicts = list(csv.DictReader(f, delimiter='\t'))
    audit = recount(source, supplied, verdicts, registry_counts(),
                    lambda r: current_evidence(r, repo, names, offered))
    audit['implementation_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    manual = []
    for path in args.manual_evidence:
        manual.extend(json.loads(path.read_text()))
    apply_manual_evidence(audit, manual, repo)
    if args.require_complete_reviews:
        require_complete_reviews(audit)
    args.private_output_dir.mkdir(parents=True, exist_ok=True)
    (args.private_output_dir / 'ledger-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    private = ['# Recounted authorized ledger', '',
               'Generated from the unchanged source; original identities, gaps and evidence retained below.', '',
               'Registry: ' + json.dumps(audit['registry_counts']), '',
               '| Row | Contract | Original | Rewritten | Historical evidence | Remaining gap |',
               '|---|---|---|---|---|---|']
    for r in audit['rows']:
        cells = [r['id'], r['folder']+'/'+r['contract'], r['status'], r['rewritten_status'],
                 r.get('manual_review', {}).get('current_measured_capability') or r['historical_reason'] or r['supplied_evidence']['evid'],
                 r.get('manual_review', {}).get('remaining_gap') or r['gap']]
        private.append('| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ') for c in cells) + ' |')
    (args.private_output_dir / 'STATUS.recounted.md').write_text('\n'.join(private)+'\n')
    args.public_output.write_text(public_report(audit))
    print(json.dumps({k:v for k,v in audit.items() if k != 'rows'}, sort_keys=True))


if __name__ == '__main__':
    main()
