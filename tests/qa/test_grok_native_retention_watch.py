# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The P4-17 CI watch: tracked expected-failing against the pinned Grok, loud on anything else, loudest when the original passes."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("grok_native_retention_watch", Path(__file__).with_name("grok_native_retention_watch.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

PASSED = {"name": "native hot reload replied", "passed": True}


def checks(*failed):
    return {"cases": [PASSED, *({"name": n, "passed": False} for n in failed)]}


def diagnosis(**failed):
    rows = [{"label": label, "status": "FAILED" if obligations else "MET", "failed_obligations": obligations or []}
            for label, obligations in failed.items()]
    return {"cases": [PASSED], "diagnostic_summary": {"status": "FAILED" if any(failed.values()) else "MET", "cases": rows}}


def test_the_expected_native_failure_is_tracked_not_red():
    status, annotation = W.verdict(1, checks(W.EXPECTED_CHECK))
    assert status == 0 and annotation.startswith("::warning::")


def test_the_original_passing_is_the_loud_removal_signal():
    status, annotation = W.verdict(0, checks())
    assert status == 1 and annotation.startswith("::error::") and "PASSES" in annotation and "remove the boundary" in annotation


@pytest.mark.parametrize("receipt", [checks("project source positive native control (no trust workaround)"),
                                     checks("http same-name native hot reload replied"),
                                     {"cases": [PASSED], "failure": "Traceback\nTimeoutError: deadline"},
                                     None])
def test_any_other_outcome_fails_loudly(receipt):
    status, annotation = W.verdict(1, receipt)
    assert status == 1 and annotation.startswith("::error::")


def test_the_expected_transport_diagnosis_is_tracked():
    receipt = diagnosis(**{"http-foreign_transport": None, "http-lampway_pane": ["canonical_survives", "owned_next_call"],
                           "sse-foreign_transport": None, "sse-lampway_pane": ["canonical_survives", "owned_next_call"]})
    assert W.verdict(2, receipt)[0] == 0


@pytest.mark.parametrize("receipt", [diagnosis(**{"http-lampway_pane": None, "sse-lampway_pane": None}),
                                     diagnosis(**{"http-lampway_pane": ["canonical_survives"], "sse-lampway_pane": ["canonical_survives", "owned_next_call"]}),
                                     diagnosis(**{"http-foreign_transport": ["hostile_contacted"], "http-lampway_pane": ["canonical_survives", "owned_next_call"],
                                                  "sse-lampway_pane": ["canonical_survives", "owned_next_call"]})])
def test_a_changed_transport_diagnosis_fails_loudly(receipt):
    assert W.verdict(2 if receipt["diagnostic_summary"]["status"] == "FAILED" else 0, receipt)[0] == 1


def test_main_runs_the_command_unchanged_and_reads_its_receipt(tmp_path, capsys):
    out = tmp_path / "out"
    script = "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); p.mkdir(); (p/'receipt.json').write_text(json.dumps(%r)); sys.exit(1)" % (
        checks(W.EXPECTED_CHECK),)
    assert W.main(["--output", str(out), "--", sys.executable, "-c", script, str(out)]) == 0
    assert "::warning::" in capsys.readouterr().out
    assert json.loads((out / "receipt.json").read_text())["cases"][-1]["name"] == W.EXPECTED_CHECK
