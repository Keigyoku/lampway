<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Reference suite handoff

Use a settled clean checkout with its actual upstream gitlink and the repository's test environment instructions. Supply the complete original read-only shelf, including its scratch fixtures; two preflight files alone do not establish full-suite readiness. Set both shelf variables. Use a disposable copy of a genuine installation with its original build-produced `BUILT_FROM` above `bin/`, and make rsync available. A synchronized Python overlay cannot establish native build provenance. Never restamp a build or substitute empty fixtures.

```bash
export LAMPWAY_TEST_PYTHON='<reference-venv>/bin/python'
export LAMPWAY_SHELF_DIR='<actual-read-only-shelf>'
export LAMPWAY_SHELF_SCRATCH='<actual-read-only-scratch>'
export LAMPWAY_BIN='<disposable-genuine-install>/bin/mixar'
export LAMPWAY_INSPECT_BIN="$LAMPWAY_BIN"
export TMPDIR='<unique-writable-run-directory-outside-repo-and-shelf>'
export LAMPWAY_TEST_OUT="$TMPDIR/receipts"
mkdir -p "$TMPDIR"
scripts/lampway/test_all.sh --verify-env
```

After preflight succeeds, independently check the native gate before launching the full suite:

```bash
"$LAMPWAY_TEST_PYTHON" - <<'PY'
import importlib.util, os
from pathlib import Path
p = Path('scripts/lampway/test_all.py').resolve()
s = importlib.util.spec_from_file_location('runner', p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
state, detail = m.binary_gate(m.ROOT, os.environ['LAMPWAY_BIN'])
print(state, detail)
raise SystemExit(0 if state == 'gated' else 1)
PY
scripts/lampway/test_all.sh
```

Run the final command only after both preceding checks pass. Retain the command, exit, source/build hashes, `summary.json`, `client.log` and `server.log`. Review `baseline_now_passing` before a separate `--shrink-baseline` run; retain its before/after diff. Exact affirmative PASS receipts are required. Failed, skipped or uncollected entries remain, and unverified baseline entries refuse GREEN. Process errors refuse GREEN; flaky classification requires a successful retry with an exact PASS receipt.

The four alleged stale cases still fail in the retained base/current isolated comparison, so all122 baseline entries remain. Cloud component tests do not establish a reference-suite result. Actual reference acceptance requires zero new reds, zero unverified rows, no retained proven-pass baseline rows, a gated native build and no shelf writes.
