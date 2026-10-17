# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The native-cancel CI watch (captain, 2026-10-12): tracked only on the exact native failure, loud on anything else."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("grok_native_cancel_watch", Path(__file__).with_name("grok_native_cancel_watch.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)


def inline(*failed, recorded=True, completed=True, **extra):
    cases = [{"name": "warm-up", "passed": True}, *({"name": n, "passed": False} for n in failed)]
    receipt = {"cases": cases, "completed": completed, **extra}
    if recorded:
        receipt["recorded_native_cancel"] = W.INLINE_CHECK
    return receipt


def cancel(obligations=None, reply="cancelled", n=4, guard="clean exact HEAD confirmed"):
    obligations = [W.CANCEL_OBLIGATION] if obligations is None else obligations
    return {"final_source_guard": guard, "cases": [
        {"label": label, "failed_obligations": list(obligations), "prompt_reply": {"result": {"stopReason": reply}}}
        for label in ["native-503", "native-400", "restricted-503", "restricted-400"][:n]]}


def test_the_exact_native_ctrlc_failure_with_every_later_stage_complete_is_tracked():
    status, note = W.verdict_inline(0, inline(W.INLINE_CHECK))
    assert status == 0 and note.startswith("::warning::")


@pytest.mark.parametrize("receipt", [
    inline(),                                                                     # native Grok now closes it: remove the watch
    inline(W.INLINE_CHECK, "hard-close all owned worker descendants absent"),     # a later stage failed too
    inline("hard-close all owned worker descendants absent"),                     # another check failed instead
    inline(W.INLINE_CHECK, completed=False),                                      # a later stage never ran
    inline(W.INLINE_CHECK, recorded=False),                                       # raised, not recorded: later stages unproven
    inline(W.INLINE_CHECK, failure="Traceback\nTimeoutError: deadline"),          # the run raised
    inline(W.INLINE_CHECK, http_events=[{"path": "/foreign-http"}]),              # a hostile endpoint was contacted
    None,                                                                         # no receipt
])
def test_any_other_inline_outcome_fails_loudly(receipt):
    status, note = W.verdict_inline(1, receipt)
    assert status == 1 and note.startswith("::error::")


def test_the_inline_pass_names_the_removal():
    assert "remove" in W.verdict_inline(0, inline())[1]


def test_the_exact_native_cancel_failure_in_all_four_cases_is_tracked():
    status, note = W.verdict_cancel(1, cancel())
    assert status == 0 and note.startswith("::warning::")


@pytest.mark.parametrize("summary", [
    cancel(obligations=[]),                                                       # native Grok now closes it: remove the watch
    cancel(obligations=[W.CANCEL_OBLIGATION, "all_owned_absent_including_z"]),    # cleanup failed too
    cancel(obligations=["native_exchange"]),                                      # another obligation instead
    cancel(reply="end_turn"),                                                     # the cancel was not even acknowledged
    cancel(n=3),                                                                  # a case is missing
    cancel(guard=None),                                                           # the source guard did not confirm the head
    None,
])
def test_any_other_cancel_outcome_fails_loudly(summary):
    status, note = W.verdict_cancel(1, summary)
    assert status == 1 and note.startswith("::error::")


def test_main_runs_the_command_unchanged_and_reads_its_receipt(tmp_path, capsys):
    out = tmp_path / "out"
    script = ("import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); p.mkdir(); "
              "(p/'summary.json').write_text(json.dumps(%r)); sys.exit(1)") % (cancel(),)
    assert W.main(["--kind", "cancel", "--output", str(out), "--", sys.executable, "-c", script, str(out)]) == 0
    assert "::warning::" in capsys.readouterr().out
    assert json.loads((out / "summary.json").read_text())["cases"][0]["failed_obligations"] == [W.CANCEL_OBLIGATION]
