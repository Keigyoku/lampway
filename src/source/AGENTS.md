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

Bounded native translation units extract existing click, slot-content, slide and cursor helpers with declarations and CMake registration, preserving runtime behavior. Lampway palette patches use the shared documented tokens under LAMPWAY guards. Keep dynamic GlassWash, actual capture-helper guards and buffer lifetime behavior; source-level passes require a separate authorized build-box compilation before native behavior acceptance.


Lampway full-window screenshot readback uses the maintained offscreen composition even when the GPU reports frontbuffer-read capability; redraw/swap can discard frontbuffer pixels. The windowmanager target owns its conditional PRIVATE LAMPWAY definition. Preserve GPU context push/pop on success and allocation failure, keep the upstream OFF path, and retain separate opt-in/masking/busy guards on UI observation. Compiled dispatcher controls are not an actual rebuilt screenshot acceptance receipt.

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

Native targets with fork-only consumers own a conditional `PRIVATE LAMPWAY` compile definition after target creation. A cache flag or creator-local definition does not enable sibling editor libraries. Verify the actual consumer compile command after buildbox reconfiguration; retain the upstream branch for OFF builds. Source gates cannot replace native build or physical operator evidence.

Native UI inspection reads the active edit buffer when present, with password redaction before selection and unchanged upstream OFF behavior. Save preserves an already selected format suffix, including leading-dot filenames and case; format changes still replace it. Compiled extracted routines are boundary controls, never a substitute for the maintained full build and physical rerun.

Lampway Linux bubble and pill windows register with the existing floating-dock registry on creation and restoration, before chrome/map operations. Reopened splash suppression must cover already existing islands; retain macOS marking, Windows behavior and Linux OFF behavior through a target-owned private definition.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the fork-patch conventions lived in one report and the tests that pin them | the guard-and-marker rule, the login and host invariants, the build owner and the three grades of native evidence | captain ruling, 2026-10-05 |
| 2026-10-07 | native inherited UI maintenance | captain: resolve inherited reds | oversized modules and stale palette/source pins obscured current UI and capture contracts | preserve helper bodies during bounded extraction, use guarded shared palette roles and retain live theme/capture lifetime checks | source corruption controls plus required separate build-box compile |
| 2026-10-07 | compiled profile and viewport fork guards | captain: physical AC34 reported upstream URL operators | creator-local LAMPWAY definitions did not propagate to interface or viewport targets | each guarded editor owns its conditional private definition, with actual compile-command and physical verification | ON/OFF target guards and corruption controls |

| 2026-10-08 | native screenshot offscreen readback | actual753 audit black operator frames and isolated hash-identical llvmpipe reproduction | native capability-selected frontbuffer reads returned all-zero images after screenshot redraw | route Lampway full-window reads through existing offscreen composition with drawable restoration and target-owned fork definition; retain upstream OFF and real pixel rerun requirements | compiled actual dispatcher ON/OFF RED/GREEN and exact black-frame reproduction; full native rebuild remains owed |
| 2026-10-08 | native filename and active edit observation | additional914 audit I02 | leading-dot save names duplicated their suffix and uncommitted visible text was absent from observation | preserve selected suffix and inspect active edit buffers after secret refusal, retaining OFF behavior and full-build limits | compiled actual selectors/save routine RED/GREEN plus old-binary current-overlay exact filename reopen |
| 2026-10-09 | Linux reopened splash dock registration | additional914 provisional overlap isolated reproduction | suppression depth1 enumerated zero docks because all marking calls were Apple-only | mark created/restored Linux bubble and pill under target-private LAMPWAY before mapping; retain OFF platform behavior and rebuilt-native rerun | mapped island RED with symbol-pinned empty registry, compiler platform/suppression GREEN; full build still owed |
