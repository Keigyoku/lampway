# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The pre-publish gate sees what it must (self-test plants one of each offender) and the hook and workflow point at the file that ships."""

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/lampway/prepublish_gate.py"


def test_the_gate_sees_every_planted_offender():
    p = subprocess.run([sys.executable, str(GATE), "--self-test"], capture_output=True, text=True)
    assert p.returncode == 0 and "every planted offender was seen" in p.stdout, p.stdout + p.stderr


def test_the_hook_and_the_workflow_run_the_shipped_gate_and_the_allow_list_has_reasons():
    assert "scripts/lampway/prepublish_gate.py" in (ROOT / ".githooks/pre-push").read_text()
    assert "scripts/lampway/prepublish_gate.py" in (ROOT / ".github/workflows/pii-gate.yml").read_text()
    for line in (ROOT / "scripts/lampway/pii_allow.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert "#" in line, f"an allow-list value without a reason: {line!r}"


def test_an_owner_pattern_comes_only_from_the_environment_and_nothing_owner_specific_is_tracked(tmp_path):
    (tmp_path / "x.txt").write_text("written by jdoe on the shared box\n")
    env = {"PATH": "/usr/bin:/bin"}
    clean = subprocess.run([sys.executable, str(GATE), "--tree", str(tmp_path)], capture_output=True, text=True, env=env)
    assert "0 finding" in clean.stdout and clean.returncode == 0, "with no owner patterns the gate has none to apply"
    hit = subprocess.run([sys.executable, str(GATE), "--tree", str(tmp_path)], capture_output=True, text=True, env={**env, "PII_OWNER_USER_RE": r"\bjdoe\b"})
    assert hit.returncode != 0 and "owner-username" in hit.stdout, hit.stdout
    src = GATE.read_text()
    assert 'os.environ.get("PII_OWNER_EMAIL_RE") or r"(?!)"' in src and 'os.environ.get("PII_OWNER_PATH_RE") or r"(?!)"' in src


def test_the_hook_and_the_workflow_wire_the_owner_patterns_without_values():
    hook = (ROOT / ".githooks/pre-push").read_text()
    wf = (ROOT / ".github/workflows/pii-gate.yml").read_text()
    assert "pii_owner.env" in hook and "set -a" in hook
    for name in ("PII_OWNER_EMAIL_RE", "PII_OWNER_USER_RE", "PII_OWNER_PATH_RE"):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in wf


def test_pii_findings_block_without_republishing_the_value(tmp_path):
    email = "privacy-fixture" + "@gmail.com"
    home = "/home/" + "privacy-fixture/private-project"
    secret = "sk-or-v1-" + "a1" * 20
    (tmp_path / "fixture.txt").write_text(email + "\n" + home + "\n" + secret)
    p = subprocess.run([sys.executable, str(GATE), "--tree", str(tmp_path)], capture_output=True, text=True)
    assert p.returncode == 1
    assert all(kind in p.stdout for kind in ("any-email", "home-path", "openrouter-key"))
    assert email not in p.stdout and home not in p.stdout and secret not in p.stdout
    assert "gmail.com" not in p.stdout, "finding output must not expose the private domain"


def test_commit_identity_blocks_without_republishing_the_email(tmp_path):
    email = "privacy-fixture" + "@example.org"
    git = ["git", "-C", str(tmp_path)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["-c", "user.name=Privacy fixture", "-c", f"user.email={email}",
                          "commit", "--allow-empty", "-qm", "synthetic identity plant"], check=True)
    p = subprocess.run([sys.executable, str(GATE), "--git", "HEAD"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 1 and p.stdout.count("commit-email") == 2
    assert email not in p.stdout and "example.org" not in p.stdout


@pytest.mark.parametrize("local,domain,expected", [
    ("noreply", "github.com", 0),
    ("personal-fixture", "github.com", 1),
    ("noreply", "github.com.example.org", 1),
])
def test_only_exact_public_provider_identity_is_safe(tmp_path, local, domain, expected):
    git = ["git", "-C", str(tmp_path)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["-c", "user.name=Synthetic provider", "-c", f"user.email={local}@{domain}",
                          "commit", "--allow-empty", "-qm", "synthetic provider identity"], check=True)
    p = subprocess.run([sys.executable, str(GATE), "--git", "HEAD"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == expected, p.stdout


def test_public_provider_identity_does_not_exempt_secret_content(tmp_path):
    git = ["git", "-C", str(tmp_path)]
    subprocess.run(git + ["init", "-q"], check=True)
    secret = "sk-or-v1-" + "a1" * 20
    (tmp_path / "plant.txt").write_text(secret)
    subprocess.run(git + ["add", "plant.txt"], check=True)
    email = "noreply" + "@github.com"
    subprocess.run(git + ["-c", "user.name=Synthetic provider", "-c", f"user.email={email}",
                          "commit", "-qm", "synthetic content plant"], check=True)
    p = subprocess.run([sys.executable, str(GATE), "--git", "HEAD"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 1 and "openrouter-key" in p.stdout
    assert secret not in p.stdout


def _gate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('prepublish_gate_matrix_tests', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _committed_matrix_line():
    # Exact multiline-payload line from tests/lampway_tools/test_native_complete_topology.py
    # at f13fa7d9de627bc9e47efa5d3b7c25083ffb8edd; source blob 7655712d34f0af165c11d0fc4c7b37d70b7e0209.
    # Keep the reproduction independent of that native implementation's publication.
    # Construct operator tokens separately; the resulting scanner input is byte-exact.
    return "@".join(('    expected=(arm.matrix_world', "arm.pose.bones['lowerarm_l'].head)-(arm.matrix_world", "arm.pose.bones['upperarm_l'].head)"))


def test_actual_committed_matrix_payload_is_not_an_email(tmp_path):
    gate = _gate_module()
    line = _committed_matrix_line()
    assert line.count('@') == 2
    # This line is executable code inside a multiline native-runner payload.
    (tmp_path / 'native.py').write_text("run('''\n" + line + "\n''')\n")
    assert gate.scan_tree(tmp_path) == []


@pytest.mark.parametrize('form', ['quoted', 'comment', 'non_python', 'invalid_python'])
def test_matrix_spelling_is_not_exempted_without_executable_python_syntax(tmp_path, form):
    gate = _gate_module()
    line = _committed_matrix_line().strip()
    path = tmp_path / ('plant.txt' if form == 'non_python' else 'plant.py')
    if form == 'quoted':
        line = 'value = ' + repr(line)
    elif form == 'comment':
        line = '# ' + line
    elif form == 'invalid_python':
        line = 'incomplete( ' + line
    path.write_text(line + '\n')
    assert any(f[1] == 'any-email' for f in gate.scan_tree(tmp_path))


def test_matrix_exception_is_match_specific_and_keeps_owner_email_rules(tmp_path):
    import re
    gate = _gate_module()
    line = _committed_matrix_line().strip()
    mail = 'privacy-fixture' + '@' + 'gmail.com'
    (tmp_path / 'mixed.py').write_text(line + '; contact = ' + repr(mail) + '\n')
    findings = gate.scan_tree(tmp_path)
    assert sum(f[1] == 'any-email' for f in findings) == 1
    assert all(mail not in str(f) for f in findings)
    (tmp_path / 'mixed.py').write_text(line + '\n')
    gate.CP.append(('owner-email', 'HIGH', re.compile(r'matrix_world' + '@' + r'arm\.pose')))
    assert any(f[1] == 'owner-email' for f in gate.scan_tree(tmp_path))


def test_scan_line_defaults_to_strict_and_handles_unicode_columns():
    gate = _gate_module()
    line = _committed_matrix_line().strip()
    assert any(f[0] == 'any-email' for f in gate.scan_line(line))
    assert gate.scan_line("label='é'; " + line, source_path='native.py') == []
    mail = 'reference-fixture' + '@' + 'gmail.com'
    assert any(f[0] == 'any-email' for f in gate.scan_line('value = ' + repr(mail), source_path='native.py'))


def test_git_added_python_payload_uses_syntax_but_message_and_other_files_stay_strict(tmp_path, monkeypatch):
    gate = _gate_module()
    git = ['git', '-C', str(tmp_path)]
    subprocess.run(git + ['init', '-q'], check=True)
    line = _committed_matrix_line()
    (tmp_path / 'native.py').write_text("run('''\n" + line + "\n''')\n")
    subprocess.run(git + ['add', 'native.py'], check=True)
    identity = ['-c', 'user.name=Synthetic provider', '-c', 'user.email=noreply' + '@' + 'github.com']
    subprocess.run(git + identity + ['commit', '-qm', 'matrix syntax fixture'], check=True)
    result = subprocess.run([sys.executable, str(GATE), '--git', 'HEAD'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
    (tmp_path / 'native.txt').write_text(line + '\n')
    subprocess.run(git + ['add', 'native.txt'], check=True)
    subprocess.run(git + identity + ['commit', '-qm', line.strip()], check=True)
    result = subprocess.run([sys.executable, str(GATE), '--git', 'HEAD~1..HEAD'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1 and result.stdout.count('any-email') == 2, result.stdout
    monkeypatch.chdir(tmp_path)
    assert sum(f[1] == 'any-email' for f in gate.scan_git('HEAD~1..HEAD')) == 4


def test_bare_email_and_matrix_lookalikes_are_not_proven_native_operands():
    gate = _gate_module()
    bare = 'contact = jane' + '@' + 'private.example'
    lookalike = 'value = jane.matrix_world' + '@' + 'private.example'
    different_receiver = 'value = arm.matrix_world' + '@' + "other.pose.bones['root'].head"
    for line in (bare, lookalike, different_receiver):
        assert any(f[0] == 'any-email' for f in gate.scan_line(line, source_path='plant.py'))


def test_python_lines_without_at_skip_ast_parsing_and_keep_other_rules(monkeypatch):
    gate = _gate_module()
    def unexpected_parse(*args, **kwargs):
        raise AssertionError('A line without @ must not invoke the Python parser')
    monkeypatch.setattr(gate.ast, 'parse', unexpected_parse)
    assert gate.scan_line('value = 1', source_path='native.py') == []
    home = '/home/' + 'privacy-fixture/private-project'
    assert any(f[0] == 'home-path' for f in gate.scan_line('path = ' + repr(home), source_path='native.py'))
