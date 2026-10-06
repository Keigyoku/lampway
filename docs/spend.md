<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Spend: receipts, caps and clicks

Lampway is built so that nothing costs you money you did not agree to. Three mechanisms work together: **clicks** (a spend waits for you), **caps** (a limit nothing can exceed) and **receipts** (a record written before the money can move). This page describes what the code enforces today.

The law, in one line: **an agent can plan a spend and read what was spent; only you can confirm one.**

## 1. Clicks

A spend that waits for you shows as a card in the **Studios (online)** panel of the Lampway tab: the action, the price read back from the service ("N credits, read back from Studio") and **Confirm and spend** / **Reject**.

- **The price must match.** A confirm carries the price you were shown (`POST /app/studio/approvals/<id>/confirm {price}`); if it differs from the price on the card the confirm is refused.
- **One shot, and it expires.** An approval is single use and expires after 600 seconds; an expired job tells you to submit again so the price is read back fresh.
- **Only you.** The server takes the actor from the route, never from the request body. No agent tool has a confirm path. In the Client the confirm operator refuses while any script is running (the agent's script, a swarm worker, the live bridge's `exec_code`), so a script cannot press it.
- **Questions are clicks too.** Higgsfield's "unlimited" option comes back as a second approval needing your Yes or No; it is never answered for you.
- **A hung job is never re-clicked.** A Studio job that hangs stays hung until you acknowledge it (`POST /app/studio/jobs/<id>/acknowledge-hung`).
- **Unknown price.** A price the policy cannot read is never waved through: it needs a click unless the provider's policy is `off`.

### The click policy per provider

The **Providers** dialog sets a spend policy per provider (`server/lampway_server/spendpolicy.py`): `click` is `off`, `above` or `always`; `above` is the price over which a click is needed; `job_cap` and `session_cap` are limits in the provider's own unit (dollars for OpenRouter, credits for Higgsfield, the Studios and Hyper3D).

| Provider | Default click | Unit |
|---|---|---|
| `openrouter` | `off` (the session budget and the per-job caps are the limits) | dollars |
| `higgsfield` | `always` | credits |
| `studios` (the Studio actions) | `always` | credits |
| `hyper3d` | `always` | credits |

The policy decides **whether** a job waits for you; it never lets anyone else click. The project decision for OpenRouter dollars is a click above $0.25 (the same threshold as the compute wrapper); until your build carries it, set `click: above` and `above: 0.25` for `openrouter` in the Providers dialog.

## 2. Caps

| Cap | Default | Scope | Enforced |
|---|---|---|---|
| OpenRouter session budget | $3 (`LAMPWAY_OPENROUTER_BUDGET_USD`, launcher `--budget`) | main agent, swarm and image backend share one ledger | before the call is sent; past the ceiling every OpenRouter call is refused |
| OpenRouter `max_tokens` | 4096 per request | each request | always sent |
| Video job cap | $2 (`video_max_job_usd`) | one video job | before submit, with the ledger's remaining budget |
| Per-provider job and session caps | unset | the provider's own unit | `SpendPolicy.check` before a spend; refusals name the cap |
| Compute job cap | $1 | one compute job's worst case | planning, then the runner |
| Compute day cap | $5, per local day | all compute jobs | planning, then the runner |
| Compute click | above $0.25 | a compute job's worst case | submit refuses without `--yes-price` |
| Receipts folder cap | 20 GiB | `<project root>/jobs` | a new receipt is refused over the cap |

All are preferences you can change; none can be raised by an agent. A video estimate that fits no price SKU is "price unknown" and is refused unless you accept it. Estimates are conservative: HeyGen's formula read twice the bill at 480p and 5 s ($0.10 estimated, $0.05 billed); the formula was left as it is.

## 3. Receipts

`server/lampway_server/jobreceipts.py` writes a **write-ahead receipt** for every paid provider job before the first byte is sent: `<project root>/jobs/<provider>/<key>/receipt.json`, created with an exclusive link so a second submitter of the same key gets the existing receipt and never a second job. Files are 0600 in 0700 directories and every update is atomic.

States: `planned`, `submission_pending`, `submitted`, `submission_unknown`, `running`, `completed`, `downloaded` or `result_saved`, `provider_error`, `cancelled`, `abandoned`.

- `submission_pending` is written before the call. A process that dies there leaves it, and the next reconcile turns it into **`submission_unknown`**. Nothing resubmits an unknown job.
- Only the **user** can resolve one: *acknowledge* (it did not run, so it becomes `abandoned`) or *link* (here is the provider's job id, so it resumes). The receipt API refuses any other actor. At the time of writing no server route or Client button calls these two methods, so resolving an unknown job today means the Python API; the Client shows the job as "Maybe sent: check the provider's own history".
- At server start (and every minute) reconcile resumes `submitted` and `running` jobs through the provider's adapter by id, downloads results that completed while you were away, and finishes a job whose provider forgot it from the saved `result.json`.
- Downloads are https only, no userinfo, at most 512 MB per file, written to a `.part` file and renamed when whole, with a sha256 per file.
- A payload that still holds an unresolved `{{variable}}` or the placeholder host is refused before anything is written.
- Receipt, ledger and report forms drop signed URLs and secret-looking keys (`export_safe`); values with secret prefixes (`sk-`, `ghp_`, `AKIA`, `AIza`) and URLs with userinfo are rejected.
- The agent tool `lampway_job_receipt` is a read-only view.

A route that is off refuses a job **before** its receipt is created, so a refused job never reads as "maybe sent" ([privacy](privacy.md)).

## 4. The ledger

One append-only file, `<project root>/ledger/runs.jsonl`, records every generation and experiment run, and the prompt run log is a view of the same file. A row is never edited: a correction is a new row with `supersedes`. Cost is four separate quantities and they are never summed into one number: subscription text, generation credits, developer-API dollars and work seconds. A credit price needs the source it was read back from. An agent can never `choose` a spend result; only you (or a rule) do. Appends take an exclusive file lock, so threads and worker processes lose no row.

The agent tools `lampway_ledger_list`, `_compare`, `_receipt` (what a piece cost) and `_record` read and append; `lampway_credit_balance` (offered to MCP apps) reports what the local ledger says was spent, by provider and unit, the job states and the configured caps. It never reads a studio's own balance and never reads a secret. Server routes: `/app/ledger`, `/app/ledger/compare`, `/app/ledger/receipt`.

## 5. Compute

The compute wrapper ([compute](compute.md)) plans every job into a priced card: the worst-case dollar amount (rate times maximum seconds, from a measured or documented rate, never from a provider counter that lags), the caps, the privacy verdict and whether a click is needed. A submit above $0.25 needs your approval of exactly that number (`--yes-price`). A failed job still tears its box down, verified against the provider's own listing, and a reconcile reports (never deletes) orphans and what still bills.

## 6. What has been spent, measured

These are recorded figures, not promises: an OpenRouter agent pass under $1 in total; one 5 second HeyGen clip $0.05 billed against a $0.10 estimate; one image $0.067; a dictation check $0.000483; the compute wrapper's live Boat test about $0.0016 against its $5 spike cap ([`docs/reports/compute-spend.md`](reports/compute-spend.md)). No Tripo, Higgsfield, Meshy, Hi3D or Hyper3D generation has been run by the project's builds, so those prices are read-backs and list prices, not bills.
