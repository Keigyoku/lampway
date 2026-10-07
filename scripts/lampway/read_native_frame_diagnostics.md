<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Read-only native frame diagnostic

Run the compiled owner binary on an already prepared disposable scene copy. The
nearest tool, `rig_inspect`, reports conventions but does not expose raw matrices
or serialization precision; this script only inspects those missing values.
It does not normalize, project, modify scene data, save the scene, read
credentials or contact a service. Use a fresh isolated profile as for other
headless QA runs, and disable automatic execution of embedded scene scripts.

Set these values to your local binary, disposable scene copy, repository checkout,
existing armature name and a new absolute private JSON path:

```bash
FRAME_DIAG_ARMATURE="$ARMATURE_NAME" FRAME_DIAG_OUTPUT="$PRIVATE_FRAME_JSON" \
  "$LAMPWAY_BIN" --background --disable-autoexec "$DISPOSABLE_BLEND" \
  --python-exit-code 1 --python "$CHECKOUT/scripts/lampway/read_native_frame_diagnostics.py"
```

The script intentionally reads the modules installed in that compiled binary. It
records their loaded file paths, SHA256 hashes and the actual `_bones` function
source in the private JSON, which can expose a stale overlay. Do not sync Python
before the first diagnostic of a failing runtime. The JSON includes object and
bone matrices, determinants, singular values, strict proper-rotation verdicts
and maximum Gram errors for raw world matrices, column-normalized matrices,
six- and twelve-decimal serializations, and the actual `rig_tools.read` result.
It includes all failing variants and the three previously reported native bones.

The output is created exclusively with mode0600. An existing path refuses without
overwriting it. Stdout contains only an aggregate schema/count marker or a
generic refusal with the exception class; private paths and object names are
kept in the JSON. Keep the JSON private and relay only the required numeric
diagnostics and source hashes for review. This is a read-only measurement, not
proof of normalization success or a modification to proper-rotation tolerances.

Validation: `python -m pytest -q tests/lampway/test_native_frame_diagnostics.py`
checks unchanged proper matrices, reflection/material-shear rejection, float32
and six-decimal precision differences, invalid shapes/values, strict JSON and
exclusive private output. The complete342 oblique native regression reproduces
the original normalization failure when the bounded serialization correction is
disabled, and verifies unchanged authored matrices with the correction enabled.
Actual owner frame tests accept an external read-only JSON receipt through
`LAMPWAY_FRAME_DIAGNOSTIC_RECEIPT`; absent measurements are explicit skips.
