# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI watch over the native Grok cancellation diagnostics (captain's rulings, 2026-10-12).

Native Grok (1.0.50, and the stable 1.0.52) never closes an in-flight model request when a turn is cancelled, from the pane's
Ctrl+C or over ACP ``session/cancel``. The captain kept the route-card promise (Lampway does not see or log the user's harness
traffic), so no Lampway relay closes it, and ruled that these diagnostics run as a tracked watch like P4-17. The command after
``--`` runs unchanged and the watch reads what it wrote under ``--output``:

* ``--kind inline`` (tests/qa/grok_worker_inline_diagnostics.py ``--record-native-cancel``): the native Ctrl+C turn-request close is
  recorded instead of raised, so every later stage (HUP/TERM cleanup, hard-close, owned cleanup, the native deny intersection) still
  runs and must pass. Tracked only when the run completed, that one check is the only failure and no hostile endpoint was reached.
* ``--kind cancel`` (tests/qa/grok_worker_cancel_diagnostics.py): tracked only when all four cases (plain native and Lampway's
  restricted worker, HTTP 503 and 400) were acknowledged ``cancelled`` and fail exactly the eight-second peer close, on the
  confirmed head.

Anything else is an error annotation and exit 1. If the native close starts to pass, that is loud too: the watch is then removed,
``--record-native-cancel`` is dropped and the diagnostics run directly again.
"""
import argparse
import json
import subprocess
from pathlib import Path

INLINE_CHECK = "CtrlC closes pending owned fixture request before pane close"
CANCEL_OBLIGATION = "peer_closed_within_original_eight_seconds"
REMOVE = ("native Grok now closes the cancelled turn's model request: remove this watch, drop --record-native-cancel and run "
          "the diagnostics directly again")
CHANGED = "the native cancel diagnostic no longer fails only where native Grok fails; investigate before anything else"


def verdict_inline(rc: int, receipt) -> tuple:
    if receipt is None:
        return 1, f"::error::native cancel watch: the inline diagnostic wrote no receipt (exit {rc})"
    if receipt.get("failure"):
        return 1, "::error::native cancel watch: the inline diagnostic raised: " + receipt["failure"].strip().splitlines()[-1]
    contacted = sorted({e.get("path") for e in receipt.get("http_events") or [] if str(e.get("path", "")).startswith("/foreign-")})
    if contacted:
        return 1, f"::error::native cancel watch: a hostile endpoint was contacted {contacted}"
    failed = [c.get("name") for c in receipt.get("cases", []) if not c.get("passed")]
    if not failed and receipt.get("completed") is True:
        return 1, "::error::native cancel watch: " + REMOVE
    if failed != [INLINE_CHECK] or receipt.get("recorded_native_cancel") != INLINE_CHECK or receipt.get("completed") is not True:
        return 1, f"::error::native cancel watch: {CHANGED} (failed {failed!r}, completed {receipt.get('completed')!r})"
    return 0, ("::warning::native cancel watch: expected native failure against the pinned Grok (" + INLINE_CHECK + "); every "
               "later stage completed and passed")


def verdict_cancel(rc: int, summary) -> tuple:
    if summary is None:
        return 1, f"::error::native cancel watch: the cancellation diagnosis wrote no summary (exit {rc})"
    if summary.get("final_source_guard") != "clean exact HEAD confirmed":
        return 1, "::error::native cancel watch: the source guard did not confirm the exact head"
    cases = summary.get("cases") or []
    if len(cases) != 4:
        return 1, f"::error::native cancel watch: {len(cases)} of 4 cases ran"
    if all(c.get("failed_obligations") == [] for c in cases):
        return 1, "::error::native cancel watch: " + REMOVE
    unexpected = [c.get("label") for c in cases if c.get("failed_obligations") != [CANCEL_OBLIGATION]
                  or ((c.get("prompt_reply") or {}).get("result") or {}).get("stopReason") != "cancelled"]
    if unexpected:
        return 1, f"::error::native cancel watch: {CHANGED} (cases {unexpected!r})"
    return 0, ("::warning::native cancel watch: expected native failure against the pinned Grok (all four cases cancelled, "
               "none closed the request within eight seconds)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", choices=["inline", "cancel"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="the --output directory the watched command writes")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    command = options.command[1:] if options.command[:1] == ["--"] else options.command
    rc = subprocess.run(command).returncode
    path = options.output / ("receipt.json" if options.kind == "inline" else "summary.json")
    try:
        written = json.loads(path.read_text())
    except (OSError, ValueError):
        written = None
    status, note = (verdict_inline if options.kind == "inline" else verdict_cancel)(rc, written)
    print(note, flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
