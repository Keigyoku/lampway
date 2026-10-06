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
   each with its reason on its line. Secrets are printed as their first four characters only.
5. **The gate proves itself.** `prepublish_gate.py --self-test` plants one offender of each kind and fails if any goes unseen; a
   change to the patterns lands with its plant.

## Test

```bash
python -m pytest -q tests/lampway/test_build_linux.py tests/lampway/test_prepublish_gate.py
python -m pytest -q tests/lampway_tools/test_launcher.py tests/lampway_tools/test_linux_scripts.py
python3 scripts/lampway/prepublish_gate.py --self-test
scripts/lampway/build_linux.sh --plan
```

## Owner

The build script and the build box belong to the native-build lane (`lp/facelift` at the time of writing). The pre-publish gate is
the coordinator's final gate; widening what it allows is the captain's call. Changes to `prepublish_gate.py`, `build_linux.sh`,
`sync_python.sh` and `lampway` owe their skill an anneal row and a body change in the same commit (`rail/catalog.json` triggers).

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the scripts' refusal shape, secret handling and the gate's outside-the-tree patterns were known only from their headers | the five invariants, the test commands, and the scripts bound to their skills as rail triggers | captain ruling, 2026-10-05 |
