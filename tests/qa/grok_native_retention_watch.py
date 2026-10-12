# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI watch over the ORIGINAL native Grok worker validation (issue #11 P4-17, captain's ruling 2026-10-12).

Runs the command after ``--`` unchanged (tests/qa/grok_worker_validation.py or its transport diagnostics, against the pinned
Grok artifact) and reads the receipt it writes under ``--output``. Against Grok 1.0.50 the original fails where native Grok drops
the canonical lampway_pane after a hostile same-name HTTP update; Lampway's ACP boundary (server/lampway_server/
grok_acp_boundary.py) covers that until native Grok retains the server itself.

* the expected failure, and only it -> a warning annotation, exit 0 (tracked, expected-failing);
* the original passes, or its first failure is anything else -> an error annotation, exit 1, loudly: native behaviour changed.
  If the expected check now passes, that is the signal to remove the boundary (its module docstring's REMOVAL note) and to make
  the original the gate again.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

#: What the original reports against the pinned artifact, per receipt kind.
EXPECTED_CHECK = "http same-name reload retains exact canonical ready admission"
EXPECTED_DIAGNOSTIC = {"http-lampway_pane": ["canonical_survives", "owned_next_call"],
                       "sse-lampway_pane": ["canonical_survives", "owned_next_call"]}
REMOVE = ("the ORIGINAL native check now behaves differently from the pinned Grok 1.0.50 failure the Lampway ACP boundary "
          "covers: re-run it, and if canonical retention passes natively, remove the boundary (see grok_acp_boundary.py REMOVAL)")


def first_failure(receipt: dict):
    failed = [c.get("name") for c in receipt.get("cases", []) if not c.get("passed")]
    summary = receipt.get("diagnostic_summary")
    if isinstance(summary, dict) and not failed:                       # transport diagnostics: its obligations, per case
        return ("diagnostic", {c["label"]: c.get("failed_obligations") for c in summary.get("cases", []) if c.get("status") != "MET"}
                or None)
    if receipt.get("failure") and not failed:
        return ("exception", receipt["failure"].strip().splitlines()[-1])
    return ("check", failed[0] if failed else None)


def verdict(rc: int, receipt) -> tuple:
    """(exit status, annotation) for the watched command's result."""
    if receipt is None:
        return 1, f"::error::P4-17 watch: the original wrote no receipt (exit {rc}); nothing can be compared"
    kind, failure = first_failure(receipt)
    if rc == 0 and not failure:
        return 1, "::error::P4-17 watch: the ORIGINAL native Grok validation now PASSES: " + REMOVE
    if kind == "check" and failure == EXPECTED_CHECK:
        return 0, f"::warning::P4-17 watch: expected failure against the pinned Grok ({EXPECTED_CHECK}); Lampway's ACP boundary covers it"
    if kind == "diagnostic" and failure == EXPECTED_DIAGNOSTIC:
        return 0, "::warning::P4-17 watch: expected transport diagnosis against the pinned Grok (same-name lampway_pane HTTP/SSE)"
    return 1, f"::error::P4-17 watch: the original's first failure changed (exit {rc}): {failure!r}; " + REMOVE


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True, help="the --output directory the watched command writes")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    command = options.command[1:] if options.command[:1] == ["--"] else options.command
    rc = subprocess.run(command).returncode
    receipt_path = options.output / "receipt.json"
    try:
        receipt = json.loads(receipt_path.read_text())
    except (OSError, ValueError):
        receipt = None
    status, annotation = verdict(rc, receipt)
    print(annotation, flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
