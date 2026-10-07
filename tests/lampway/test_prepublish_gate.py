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
