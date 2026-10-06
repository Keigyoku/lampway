---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# src/source — the native overlay and Lampway's fork patches

The C/C++ half of the overlay: each file here replaces the upstream file at the same path when `scripts/unix/overlay.sh` builds
`source/` (upstream's files plus the overlay's, then CMake). Most of it is upstream Mixar's own native code (editor spaces, the
chat renderer, overlays); Lampway's changes to it are the fork patches recorded in
[`docs/reports/fork-patches.md`](../../docs/reports/fork-patches.md).

## Invariants

1. **A behaviour patch is guarded and marked.** It sits under `#ifdef LAMPWAY` / `#ifndef LAMPWAY` (the CMake option `LAMPWAY` is ON
   by default, `cmake/mixar_overrides.cmake`) with a `LAMPWAY:` comment, so a build with `-DLAMPWAY=OFF` behaves as upstream's and
   the divergence is found by its marker. Measured at adoption: three files carry such guards, each with its marker
   (`creator/creator.cc`, `creator/creator_startup.cc`, `blender/editors/space_agent_bubble/agent_ui_chip_fit.hh`).
2. **No native login gate, no upstream host.** The startup login dialog is compiled out under `LAMPWAY`; the backend URL is read
   from `LAMPWAY_BACKEND_URL` before the baked default; plain `http://` is accepted only for loopback hosts
   (`creator/creator.cc`, `creator/creator_startup.cc`).
3. **User-visible native strings come from the brand header** (`blender/blenlib/BLI_lampway_brand.h`), unguarded; the brand gates
   in `tests/lampway` hold them.
4. **Never edit `source/`.** It is regenerated every build; a change made there is lost and never reaches review.
5. **Build only in the build box, through `scripts/lampway/build_linux.sh`.** Python-only changes reach a built app through
   `scripts/lampway/sync_python.sh`; a native change needs the build and its log.

## Test

```bash
python -m pytest -q tests/lampway/test_lampway_cpp_gate.py tests/lampway/test_brand_cpp.py   # source-level pins, no compiler
scripts/lampway/build_linux.sh                                                               # in the build box: the compile
```

The source-level tests pin each patch's shape; only a build proves it compiles, and only a run of the binary proves behaviour
(`build/<env>/bin/mixar --background --python-exit-code 1 ...`). Report which of the three a claim rests on.

## Owner

The native build tree and the build box belong to the native-build lane (`lp/facelift` at the time of writing); another lane's
native change goes through that lane or is raised as a decision. Divergence from upstream is the captain's call when it is not
a brand, host or login patch.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the fork-patch conventions lived in one report and the tests that pin them | the guard-and-marker rule, the login and host invariants, the build owner and the three grades of native evidence | captain ruling, 2026-10-05 |
