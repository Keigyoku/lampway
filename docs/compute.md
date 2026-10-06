<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Compute: renting a box, on your terms

Some work is heavy or you would rather not run it on the machine you are modelling on: headless Blender bakes, thumbnails, silhouette refinement, and later GPU model serving. Lampway rents that compute through **one provider-agnostic AXI command line**. You choose the provider; there is no default provider and none is enabled until you pick one.

Code: `server/lampway_server/compute/`. Contracts followed: egress consent first, then job receipts, then this wrapper. Everything here is opt-in, under caps, and logged.

## 1. What is built

| Piece | State |
|---|---|
| The runner (plan, approve, submit, status, list, cancel, reconcile), prefs, recipes, receipts, privacy gate | built, tested on fakes |
| **Boat** adapter (CPU boxes, through the installed `boat` CLI) | built; **tested live** within the caps (seven jobs, about $0.0016 in total; see [`docs/reports/compute-spend.md`](reports/compute-spend.md)) |
| **Modal**, **RunPod**, **fal** adapters (an endpoint is one request to a deployed endpoint) | built against fake transports only; every request shape is unverified; the live legs wait for a key and a provider decision |
| **Blender offload** job type (`blender_offload`) | built; ran live on Boat for a thumbnail, a silhouette and an ambient-occlusion bake |
| `probe` job type (a few facts about the box) | built; the live test of the wrapper |
| GPU **model-serving recipes** | not built: they wait for the maintainer's GPU provider decision |

## 2. The command

The same library serves the server and the CLI. Run it from the server directory, or with the server package installed:

```bash
export LAMPWAY_STATE_DIR=~/.local/share/lampway/server-state     # the launcher's state dir: share prefs and routes with the server
export LAMPWAY_PROJECT_ROOT=~/.local/share/lampway/projects      # inputs must be files inside this root
python -m lampway_server.compute            # the live state: backends, caps, spent today, recent jobs, what bills now
```

AXI (agent-ergonomic CLI) conventions apply: argparse, a live no-argument view, TOON output, explicit empties, a `help[]` of next steps after every output, structured errors, **exit 0 ok, 1 refused or failed, 2 usage**, no interactive prompts, unknown flags fail loudly.

| Command | What it does |
|---|---|
| `backends` | the providers, which are enabled, and their egress state |
| `recipes` | what can run on a box |
| `plan <recipe> --backend B --input PATH[:class]` | prices a job: worst case, caps, privacy verdict, whether a click is needed. Spends nothing |
| `submit <recipe> ... [--yes-price USD]` | runs it. Needs `--yes-price` equal to the plan's worst case when a click is required |
| `approve <plan_id>` | records your approval of a plan |
| `status KEY`, `list`, `cancel KEY` | read and stop jobs |
| `reconcile` | re-adopts, finishes and tears down; reports orphans and what still bills |
| `prefs [--set KEY=VALUE]` | caps, enabled backends, private-allowed backends, orphan action |
| `egress [ROUTE on|off]` | the compute routes and fal (the same switch is in the Privacy panel) |

Options for `plan` and `submit`: `--max-seconds` (default 300), `--max-usd`, `--type small|default|large` (Boat), `--param KEY=VALUE` (repeatable; a value that parses as JSON is JSON), `--key` (an idempotency key), `--origin user|agent|swarm`.

A first run:

```bash
python -m lampway_server.compute prefs --set backends=boat --set private_backends=boat
python -m lampway_server.compute egress compute:boat on
python -m lampway_server.compute plan blender_offload --backend boat --input piece.glb:private --param op=thumbnail
python -m lampway_server.compute submit blender_offload --backend boat --input piece.glb:private --param op=thumbnail --yes-price <the plan's upper_bound_usd>
```

## 3. Providers (adapters)

| Provider | Kind | Needs | Notes |
|---|---|---|---|
| `boat` | CPU boxes | the `boat` CLI installed and logged in by you (default path `~/.ascii/bin/boat`); Lampway never creates a Boat key | rates per hour from Boat's pricing page, dated: small $0.018, default $0.036, large $0.072; xlarge refused. Every box is made `--no-snapshots --no-env`, so the CLI sees only its own login and a stopped box is erased |
| `runpod` | serverless GPU endpoint | `RUNPOD_API_KEY` and an endpoint you deployed | the adapter only verifies the endpoint is idle-safe (min workers 0); deploying is your step |
| `modal` | serverless GPU endpoint | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | same |
| `fal` | queue gateway | `FAL_KEY` | also the `fal.py` gateway behind job receipts |

Endpoint settings (per recipe: `base_url`, `rate_usd_per_s`, `exec_timeout_s`, `idle_timeout_s`, `max_workers`, `kind`) live in the `endpoints` key of `<state>/compute_prefs.json`. Inline payloads above 10 MB are refused, not truncated.

## 4. Recipes

A recipe is data: its setup, its entry command, its declared outputs and the hardware it needs.

- `probe`: a few facts about the box (CPU count, Python version, which inputs arrived).
- `blender_offload`: headless Blender on the box (`bpy` from PyPI in a throwaway venv). `--param op=` selects `thumbnail` (a Workbench render, `thumbnail.png`), `silhouette` (an RGBA mask, `silhouette.png`) or `bake_ao` (CPU Cycles, `ao.png`). Inputs are a `.glb`, `.gltf`, `.blend` or `.obj`. An unknown op or a missing model exits with a message, never a silent default.

## 5. Caps, clicks and receipts

Defaults, all preferences: **$1 a job, $5 a day (local day), a click above $0.25**. The worst case is rate times (setup plus maximum seconds); if it is over the job cap or would pass today's cap the plan is refused. A watchdog stops a job at its cap using the estimate and the provider's meter, whichever is higher; the meter is read **before** teardown because an erased box answers 404. Provider counters can lag (Boat's balance counter did), which is why the cap is enforced from rate times elapsed and the meter, never from that counter. The full rules are in [spend](spend.md).

Every submit writes a write-ahead receipt first (`compute:<backend>` under `<project root>/jobs/`). The box id lives only in a 0600 file next to it, never in the receipt. A crash leaves `submission_pending`, which reconcile turns into `submission_unknown` and **never re-provisions**; a box created by a lost response is reported as a candidate for you to link, never adopted or stopped. The agent tool `lampway_compute` can only **plan**, `status`, `list` and read the `reconcile_report`; it cannot submit, approve or cancel.

## 6. Privacy

Compute inputs are **private unless you tag them** (`path:public`, `path:synthetic`, `path:private`). A private input goes only to a backend whose declaration is verified ephemeral, or conditional with its conditions met (Boat: snapshots off, no environment), **and** that you listed in `private_backends`. Otherwise the plan is refused with the reason and nothing is uploaded. Every upload and download passes the egress gate with the content class and a short hash of each input, so the log shows what went where. What Boat, Modal or RunPod do with content in flight is unread; their routes show "unknown" until someone reads the terms ([privacy](privacy.md)).

## 7. Reconcile and orphans

`compute reconcile` re-adopts jobs it started, finishes them, tears down verified, and lists anything still billing. Orphans are **reported and never stopped** unless you set `orphan_action=stop`, and even then a box is stopped, never deleted. Ownership is the receipt set: boxes that are not in your receipts (including your own other boxes) are never touched.

## 8. Facts measured live on Boat

- `boat exec <id> --json --no-update --timeout N "<one shell string>"`: the command is one argument; `--` and `sh -c` lose their quoting; `--detach` cannot combine with `--timeout`.
- Global flags (`--json`, `--no-update`) must come **before** the arguments.
- `exec --json` answers `{exitCode, stdout, stderr, success}`; `new --json` answers JSON lines with the box id; `usage` answers 404 after a no-snapshot box is erased.
- A failed job still tears its box down and verification reads the provider's own listing.
- The CLI cannot name a box, so ownership is the receipt set.
