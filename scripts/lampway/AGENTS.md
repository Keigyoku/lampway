---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# scripts/lampway — build, launch, sync and the pre-publish gate

Lampway's own operator scripts: `build_linux.sh` (clone to runnable app in the build box), `lampway` (the one command: server plus
app on a copy of a file), `sync_python.sh` (a Python-only change into an installed build), `prepublish_gate.py` with
`pii_allow.txt` (what may never be published). Upstream's build machinery stays in `scripts/unix/` and `scripts/windows/`; these
wrap it. The procedures: the `lampway-coding-guidelines` skill (build and run) and the `lampway-release` skill (the gate).


`measure_fit_decisions.py` runs in an explicitly supplied disposable scene and project config, never saving the blend or selecting defaults. Receipts/views remain under the project root; failed jobs produce a nonzero exit.

Body-relative fit captures require explicit world-metre body context, fixed camera bounds and caller clearance limits. Keep execution success separate from all-vertex clearance acceptance; sampled diagnostics and isolated silhouettes cannot select physical defaults.

`test_all.py --shrink-baseline` removes only exact node IDs with affirmative pytest PASS receipts. Skipped or uncollected known-red rows remain and make the reference verdict unverified; absence from the failure summary is never a passing receipt.

## Invariants

1. **AXI refusals.** A refusal prints `error: <why>` and a `help[N]:` list of next commands on stdout and exits 1; an unknown flag
   exits 2; `--plan` / `--check-deps` print what a run would do and touch nothing. A new script follows the same shape.
2. **The build runs in the box, never on the host,** and never writes `.env`: a `.env` that contradicts the requested environment
   is refused, because `settings.sh` sources it after the environment and would silently win.
3. **The launcher never takes a secret as an argument and never prints one**; the OpenRouter key comes from the environment or a
   dotenv file the user points at, and the session budget is a hard ceiling. `--copy` opens a copy; the user's file is never
   opened for saving. The profile lives under `LAMPWAY_HOME`.
4. **The pre-publish gate holds no owner value.** The maintainer's patterns come from `PII_OWNER_*_RE` variables (a 0600
   `pii_owner.env` in the shared git directory locally, repository secrets in CI). `pii_allow.txt` holds only known-fake values,
   each with its reason on its line. Secrets are printed as their first four characters only; personal identifiers and commit email domains are fully redacted.
A Python matrix expression is executable code rather than a contact address only when the scanner proves its operator and structured operands. Quoted strings, comments, bare email-shaped expressions and owner-specific patterns remain blocking; no value/domain allowlist is added for code.

5. **The gate proves itself.** `prepublish_gate.py --self-test` plants one offender of each kind and fails if any goes unseen; a
   change to the patterns lands with its plant.

UE cube capture scripts run only in an explicitly disposable UE QA project, save no scene/material asset, and write generated DATA solely under that project's `Saved/LampwayCubeQA`. The read-only capability marker is not rendering proof. Exact native shaper provenance, engine/profile agreement, raw-input controls and disabled native tone-curve controls precede a cube sidecar; the initial capture records its 8-bit display precision. Offline `--plan` reports the full capture count and bounded runtime allowance without launching UE or choosing settings. Pure packing tests are synthetic; actual UE capture remains a separate owner-run receipt.

## Test

```bash
python -m pytest -q tests/lampway/test_build_linux.py tests/lampway/test_prepublish_gate.py
python -m pytest -q tests/lampway_tools/test_launcher.py tests/lampway_tools/test_linux_scripts.py
python -m pytest -q tests/lampway_tools/test_ue_cube_generator_probe.py tests/lampway_tools/test_ue_cube_generator_capture.py
python3 scripts/lampway/prepublish_gate.py --self-test
scripts/lampway/build_linux.sh --plan
```

Native frame diagnostics read loaded modules and authored matrices without projection or scene mutation. Write the complete owner-only receipt exclusively with restrictive permissions; print aggregate errors and source identities, never owner matrices.

Run the read-only supplemental UE surface probe before full cube capture. Missing LDR/material/neutral-grading APIs refuse; surface availability is not shader or pixel proof.

## Owner

The build script and the build box belong to the native-build lane (`lp/facelift` at the time of writing). The pre-publish gate is
the coordinator's final gate; widening what it allows is the captain's call. Changes to `prepublish_gate.py`, `build_linux.sh`,
`sync_python.sh` and `lampway` owe their skill an anneal row and a body change in the same commit (`rail/catalog.json` triggers).

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the scripts' refusal shape, secret handling and the gate's outside-the-tree patterns were known only from their headers | the five invariants, the test commands, and the scripts bound to their skills as rail triggers | captain ruling, 2026-10-05 |
| 2026-10-07 | PII diagnostics privacy | captain: fix PR privacy exposure | findings echoed identifiers and email domains into public logs | fully redact personal values while retaining every blocking rule and planted offender | prepublish privacy regression tests |
| 2026-10-07 | measured fit decision paths | captain: measure issue2 AC65 before defaults | configurable algorithm gaps and unmeasured proposals obscured required choices | `measure_fit_decisions.py` runs in an explicitly supplied disposable scene and project config, never saving the blend or selecting defaults. Receipts/views remain under the project root; failed jobs produce a nonzero exit. | native decision-pack fixture |
| 2026-10-07 | matrix code false positive | complete native topology regression push | adjacent matrix operator and structured bone attributes looked like an email | prove the Python operator and operands while retaining quoted, comment, bare-address and owner-pattern controls | planted matrix and email regressions |
| 2026-10-07 | body-relative decision receipts | captain: AC65 measured boot handoff | isolated cropped silhouettes and sampled counts hid actual body placement and implied acceptance | require explicit body context, fixed world bounds and limits; report all-vertex clearance separately with opening-band refusal and no default promotion | native body-context placement and threshold falsifiers |
| 2026-10-07 | affirmative baseline shrink receipts | issue 2 AC05 reference audit | subtracting failures treated skipped and uncollected known-red rows as passing and could delete them | require exact pytest PASS node IDs before shrinking, retain failures and unverified rows, and refuse an unverified green verdict | skipped, uncollected, teardown and parameter identity falsifiers |
| 2026-10-07 | genuine UE cube QA handoff | captain: provide actual UE tonemapper cube generation | external generator was absent and synthetic data could be mistaken for renderer proof | bounded QA-only scene captures with exact native shaper provenance, engine/profile agreement, readback controls and explicit display precision; pure tests remain distinct from physical UE proof | owner-run UE capability/capture receipt pending |
| 2026-10-07 | read-only native frame diagnostics | actual G4 numeric failure | loaded overlay and authored float32 matrices needed disambiguation | Native frame diagnostics read loaded modules and authored matrices without projection or scene mutation. Write the complete owner-only receipt exclusively with restrictive permissions; print aggregate errors and source identities, never owner matrices. | pure diagnostic controls and complete342 native unchanged-scene proof |
| 2026-10-07 | supplemental UE capture preflight | actual UE handoff | the initial probe omitted display readback and grading APIs | Run the read-only supplemental UE surface probe before full cube capture. Missing LDR/material/neutral-grading APIs refuse; surface availability is not shader or pixel proof. | missing API/property and complete mocked surface controls |
