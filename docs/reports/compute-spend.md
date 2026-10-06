<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Compute wrapper: live Boat test and spend ledger (2026-10-06)

The live Boat test the captain allowed within the caps ($1 a job, $5 a day, a click above $0.25). The wrapper called the installed `boat` binary (the CLI mode: no API key was created or used) through
`python -m lampway_server.compute`, on a scratch project and state folder, with `compute:boat` switched on by hand in that state's egress prefs. Nothing of the captain's was uploaded: the inputs are a
22-byte text file and a 26 KB generated icosphere.

## Ledger

| job (receipt key) | recipe | result | estimate (rate x seconds) | provider meter |
|---|---|---|---|---|
| b76bcdde9d20f255 | probe | provider_error: the exec call form was wrong (see findings); box torn down and verified | $0.0000074 | none |
| d1a6be6f87440656 | probe | provider_error: flags placed after the command string (see findings); box torn down and verified | $0.0000106 | none |
| a5a154e3ed293ee0 | probe | downloaded: `{"cpus": 4, "python": "3.12.3", "inputs": ["in.txt"]}` | $0.000107 | none (read after the delete: 404) |
| 1be52906e8835e6d | blender_offload (thumbnail) | downloaded: real `bpy` ran on the box (960 vertices, 320 faces) | $0.000298 | $0.0003 |
| 201a5040f15c308f | blender_offload (silhouette, 128 px) | downloaded: `silhouette.png` RGBA 128x128, alpha coverage 0.582 | $0.000278 | $0.00028 |
| 91f33d8829b761ab | blender_offload (bake_ao, 8 samples) | downloaded: `ao.png` 128x128, mean AO 0.885 | $0.000368 | $0.00038 |
| 7bcc02ae71029a66 | probe, SIGKILLed 6 s in | the CLI was killed after the box existed; `reconcile` re-adopted it, finished the job (downloaded), deleted the box | $0.000157 | $0.00016 |

Plus two boxes I made by hand to learn the CLI's argument forms (about 12 s of a `small` box each, under $0.0003 together). **Total about $0.0016 against the $5 spike cap.** The two meters agreed
within 5 % where both were read (the meter is now read BEFORE the teardown: an erased box answers 404).

`boat list --all` after every job showed only the account's two older stopped sandboxes, which were never touched (the wrapper only acts on ids in its own receipts). `boat limits` read 0 active
sandboxes before and after; its balance counter lags (1,999,091 s before and after the runs), which is the "counters disagree" fact from `specs/cloud/BOAT.md` again: the cap is enforced from
rate x elapsed and the meter, never from that counter.

## Findings that changed the code (each now pinned by the fake CLI so it cannot regress)

1. `boat exec <id> "<one shell string>"`: the command is ONE argument. `-- sh -c "..."` is re-joined without its quoting and breaks. `--detach` cannot be combined with `--timeout`.
2. Global flags (`--json`, `--no-update`) must come BEFORE the arguments: a trailing command string swallows anything after it (`mkdir: unrecognized option '--json'`).
3. `boat exec --json` answers `{"exitCode", "stdout", "stderr", "success"}`; `boat new --json` answers JSONL with `{"event":"created","id":...}`; `boat usage` answers `{"dollars","seconds",...}`
   and 404s after a no-snapshot box is erased. `boat list --all` no longer lists an erased box.
4. A failed job still tore its box down and verified it (two of the seven runs): cleanup runs on Exception, and the verification reads the provider's own listing.
5. The CLI cannot name a box, so ownership is the receipt set; a box left by a lost create is only ever a reported candidate.

Every sandbox the wrapper created is gone (`boat list --all`: the two foreign ones only). Spend by the compute wrapper stays well inside the day cap.
