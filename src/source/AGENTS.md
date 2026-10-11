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

6. **Async popup refresh preserves handle ownership.** `Mixar_refresh_popups` retains operator-dialog refresh. Under
   `LAMPWAY` it also rebuilds `can_refresh` popovers without an attached button, such as the original Choices Context
   popout; button-attached popovers stay excluded so layout refresh cannot read a freed anchor. The client requests this
   rebuild only on its main-thread async publication path.

7. **Agent Bubble purge owns transient windows, not editor layouts.** Under `LAMPWAY`, purge closes only parented native
   Agent Bubble temporary windows or parented exact tracked bubble/pill runtime windows; it preserves the host and every
   main window even when its editor is `AGENT_BUBBLE`. After child destruction, context restoration uses a surviving live
   window and may select a main window containing that editor. A no-op purge does not clear unrelated survivor state.
   Preserve upstream OFF behavior. Source checks and compilation are distinct from matching-binary ownership acceptance;
   `tests/qa/bubble_purge_ownership_e2e.py` creates actual native children and checks host, draft and context survival.

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

| 2026-10-08 | original Context popout publishes async replies | two actual native original-panel REDs, with ready response cache and bounded real hover | area redraw never rebuilt the temporary popup and the existing helper excluded every popover | invariant 6: retain dialog refresh, add guarded refreshable unanchored popovers and keep button-attached handles excluded | callback RED/GREEN and native ON/OFF syntax; matching original-panel native proof required |
| 2026-10-10 | native bubble purge ownership | matching EFE native ownership RED: before two windows, after zero, context null; exact owned cleanup retained | editor-type-only admission destroyed the main window containing AGENT_BUBBLE | invariant 7: native parent/temp/runtime ownership, surviving host and live context, no-op state preservation, upstream OFF unchanged | actual RED receipt 5dd1a494d588b66a48cd68f45610d0b80726def4579310962576c8f923be37a5; 234 source checks and ON/OFF translation-unit syntax pass; normal matching build and native GREEN pending |
