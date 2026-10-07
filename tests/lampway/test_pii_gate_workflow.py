# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the workflow's real scan step with synthetic PR and merge commits."""
import os
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/pii-gate.yml'


def _run_step(root, base, head, event='pull_request'):
    source = WORKFLOW.read_text().split('- name: New commits and their diffs', 1)[1]
    script = textwrap.dedent(source.split('run: |', 1)[1].split('      - name: Media', 1)[0])
    # Render only trusted event SHA expressions; execute the actual checked-in shell body.
    script = script.replace('${{ github.event.pull_request.base.sha || github.event.before }}', base)
    script = script.replace('${{ github.event.pull_request.head.sha || github.sha }}', head)
    env = {**os.environ, 'PII_SCAN_BASE': base, 'PII_SCAN_HEAD': head, 'GITHUB_EVENT_NAME': event}
    for key in ('PII_OWNER_EMAIL_RE', 'PII_OWNER_USER_RE', 'PII_OWNER_PATH_RE'):
        env.pop(key, None)
    return subprocess.run(['bash', '-eu', '-c', script], cwd=root, env=env, text=True, capture_output=True)


def _fixture(root, bad_head=False):
    git = ['git', '-C', str(root)]
    subprocess.run(git + ['init', '-q'], check=True)
    safe = 'noreply' + '@' + 'github.com'
    unsafe = 'workflow-fixture' + '@' + 'example.org'
    def commit(message, email):
        subprocess.run(git + ['-c', 'user.name=Synthetic fixture', '-c', 'user.email=' + email,
                              'commit', '--allow-empty', '-qm', message], check=True)
        return subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
    base = commit('base fixture', safe)
    head = commit('authored head fixture', unsafe if bad_head else safe)
    commit('synthetic merge fixture', unsafe)
    scripts = root / 'scripts/lampway'
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/lampway/prepublish_gate.py', scripts / 'prepublish_gate.py')
    return base, head


def test_pr_scan_excludes_synthetic_merge_identity(tmp_path):
    base, head = _fixture(tmp_path)
    result = _run_step(tmp_path, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'commit-email' not in result.stdout


def test_pr_scan_still_blocks_bad_authored_commit_identity(tmp_path):
    base, head = _fixture(tmp_path, bad_head=True)
    result = _run_step(tmp_path, base, head)
    assert result.returncode == 1 and result.stdout.count('commit-email') == 2, result.stdout + result.stderr
    assert 'example.org' not in result.stdout


def test_push_scan_uses_explicit_event_head(tmp_path):
    base, head = _fixture(tmp_path)
    result = _run_step(tmp_path, base, head, event='push')
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_wires_event_endpoints_and_does_not_scan_merge_head():
    source = WORKFLOW.read_text()
    assert 'PII_SCAN_BASE: ${{ github.event.pull_request.base.sha || github.event.before }}' in source
    assert 'PII_SCAN_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}' in source
    assert '--git "$scan_base..$scan_head"' in source
    assert '$base..HEAD' not in source


def test_force_push_fallback_uses_event_head_as_merge_base_input(tmp_path):
    base, head = _fixture(tmp_path)
    subprocess.run(['git', '-C', str(tmp_path), 'update-ref', 'refs/remotes/origin/main', base], check=True)
    result = _run_step(tmp_path, '0' * 40, head)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_event_head_refuses_instead_of_scanning_another_commit(tmp_path):
    base, _ = _fixture(tmp_path)
    result = _run_step(tmp_path, base, '1' * 40)
    assert result.returncode == 1 and 'event head commit is unavailable' in result.stdout
