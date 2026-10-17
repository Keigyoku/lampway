# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dedicated native proof job must be schedulable before its runner exists."""
import os
from pathlib import Path
import re
import subprocess

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / '.github/workflows/byoa-worker-validation.yml'


def test_job_environment_uses_only_available_expression_contexts():
    job = yaml.safe_load(WORKFLOW.read_text())['jobs']['owned-offline-worker']
    # GitHub's jobs.<job_id>.env context table excludes runner and env.
    # https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability
    available = {'github', 'inputs', 'matrix', 'needs', 'secrets', 'strategy', 'vars'}
    for value in job.get('env', {}).values():
        for expression in re.findall(r'\$\{\{(.*?)\}\}', str(value)):
            contexts = set(re.findall(r'\b([A-Za-z_]\w*)\s*\.', expression))
            assert contexts <= available, f'Unavailable job env contexts: {contexts - available}'


def test_build_directory_is_exported_before_the_pinned_build(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['owned-offline-worker']['steps']
    consumer = next(i for i, step in enumerate(steps) if 'scripts/lampway/herdr_env.py' in step.get('run', ''))
    exports = [(i, line) for i, step in enumerate(steps) for line in step.get('run', '').splitlines()
               if 'LAMPWAY_HERDR_BUILDS' in line and 'GITHUB_ENV' in line and 'LAMPWAY_HERDR_BIN' not in line]
    assert len(exports) == 1, 'Runner-local build directory needs exactly one explicit environment export'
    index, command = exports[0]
    assert index < consumer
    runner_temp = tmp_path / 'owned runner temp'; runner_temp.mkdir()
    environment_file = tmp_path / 'github-env'
    subprocess.run(['bash', '-e', '-c', command], check=True, env={
        'PATH': os.environ['PATH'], 'RUNNER_TEMP': str(runner_temp), 'GITHUB_ENV': str(environment_file)})
    assert environment_file.read_text().splitlines() == [
        'LAMPWAY_HERDR_BUILDS=' + str(runner_temp / 'grok-worker-herdr')]


def test_loopback_namespace_has_private_devices_without_host_device_bind():
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['owned-offline-worker']['steps']
    command = next(step['run'] for step in steps if 'Full helper' in step.get('name', ''))
    assert '--bind / / --dev /dev -- python' in command
    assert '--dev-bind' not in command
