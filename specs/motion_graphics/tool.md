<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Tool and receipt contracts

Behavior follows the [agent wrapper](../../server/lampway_server/agent/motion_tools.py) and [renderer](../../server/lampway_server/motion/__init__.py) on this branch. This describes current behavior and remaining boundaries; it does not introduce an alternate executable schema.

## Entry points

- The agent tool `lampway_motion_graphics` takes the JSON inputs below and returns JSON.
- The AXI CLI `python -m lampway_server.motion` ([cli.py](../../server/lampway_server/motion/cli.py)) is a thin layer over the same `_work` (the same checks, receipt and Vault filing). The project is `LAMPWAY_PROJECT_ROOT` or the working directory.
  - With no arguments it prints `bin`, a one-line `description`, `project`, `scenes[N]{name}` and the newest ten `runs[N]{run_id,ok,warn}` (`0 scenes`/`0 runs` when there are none).
  - `render --scene <dir> [--width --height --fps --duration --template id@v --var k=v --no-vault --full]` and `verify --receipt <path> [--full]`.
  - Output is TOON (`compute/toon_out.py`) with minimal default fields (findings as `{frame,check,severity}`, at most ten rows with a `_shown` count); `--full` adds every row, finding details, hashes, outputs and timings. Every output ends in `help[]`.
  - Errors print `error:` and `help[]` on stdout and exit 1 (a refusal, a failing self-check, a render that does not reproduce); a usage error (unknown flag, missing argument) exits 2. There are no prompts.
- Every refusal from either entry point carries `help` next steps: no browser points at BUILD-LAMPWAY.md section 8, a size out of bounds gives the bounds.

## Inputs

The declared JSON object rejects additional properties. Render properties are:

| Property | Declared value and runtime behavior |
|---|---|
| `action` | `render` (default) or `verify` |
| `scene` | Scene folder inside project; convention is project-relative. Runtime also accepts contained absolute paths. |
| `html` | Inline HTML instead of folder, needs `name`; written to `motion/scenes/<name>/index.html`. A differing existing entry is refused. |
| `entry` | Scene-contained HTML entry; default `index.html` |
| `name` | Lowercase kebab-case; defaults to scene directory name |
| `fps` | Integer, excluding booleans, 1–60; default: `__scene.fps`, then 30 (templates set no fps) |
| `width`, `height` | Even integers, excluding booleans; long edge 16–3840, short edge 16–2160 (3840 × 2160 and 2160 × 3840 both allowed); default: template, then `__scene`, then 1920 × 1080 |
| `duration_s` | Numeric, excluding booleans, `(0,120]`; default: template, then `__scene.duration_s` |
| `formats` | Nonempty unique list drawn from `mp4`, `webm`; missing means both; empty/null refused |
| `samples` | Optional nonempty list of 1–24 finite nonnegative numeric seconds, excluding booleans; positions rounded, deduplicated and clamped to final frame |
| `audit_every_s` | Optional seconds in (0, 120], rounded to whole frames (at least one): `window.__audit()` is also recorded at every such frame and the last one, in `audit.jsonl` (`{frame, t, audit}` per line, hashed as `artifact_hashes.audit`), with no PNG and no pixel checks. The probe audits the same frames. Receipts without it verify as before |
| `safe_zone` | Optional `[x0, y0, x1, y1]`, four finite fractions in 0..1 with x0 < x1 and y0 < y1, no booleans: visible text outside it fails (`safe_zone`) at samples and in the audit stream. Recorded in the receipt inputs; receipts without it verify as before |
| `template` | Optional motion-graphics template `id` or `id@version`; unversioned resolves to a version. Its `defaults` (`resolution` + `aspect_ratio` → width × height, `duration` → `duration_s`) rank below explicit arguments and above `__scene` |
| `variables` | Finite JSON template variable object with string keys; defaults filled by prompt renderer; provenance. A `*_dir` or `*_source` value without whitespace that names nothing under the project (or lies outside it) adds a `warnings` line and a `help` line |
| `vault` | Boolean only, default true; false disables filing |
| `receipt` | Verify requires a saved project-contained receipt path |

Default audits cover first/last plus ten interior positions, deduplicated for short clips. Both render and verify validate supplied values before work. Arguments must be an object; scene/html are mutually exclusive; supplied text values must be nonempty strings, variables JSON-shaped and numeric samples finite. Omitted optional values retain their defaults; explicit null wire values are refused. Saved receipt inputs and nested engine/output/source/frame fields are checked before renderer launch. The current internal normalized representation uses null for omitted optional values; it is not an alternate wire schema.

## Outputs and refusal semantics

The agent wrapper returns `(JSON text, is_error)`. Render JSON includes `ok`, `run_id`, `out_dir`, `files` (requested videos/contact), `code_sha256`, `frames`, `frames_sha256_digest`, `outputs` (hash/bytes), `self_check` (fail/warn/findings), `network`, selected timing metrics and `vault`. A completed failure sets `is_error=true`; paths can still exist. Exceptions/refusals return `ok=false,error`, with no promise that no partial output exists.

Vault status includes `assets`, `spooled`, `filed`, optionally `partial` and `error`. Cancellation returns `ok=false,cancelled=true` after owned cleanup, with committed assets and filing state; no further filing operation is admitted. `ok=true` is render acceptance, not proof of successful Vault filing. Default Vault behavior does not apply when no Vault instance is available. No network or paid receipt is required.

Verify JSON includes `reproduced`, `frames_differing`, `mp4_equal`, `webm_equal`, `engine_matches`, normally receipt and frame count, plus `integrity_matches`/per-format checked original-media results and `provenance_matches`/source-driver-flags results. An unrequested format has equality `null`. An engine mismatch reports false reproduction and an explanation before frame comparison. A negative reproduction is still a normal verify response (`is_error=false`); consumers must inspect reproduction, integrity and provenance separately. See [reproduction limits](motion_graphics.md#2-timeline-rendering-and-export).

Progress: render and verify report each phase (`render`, then `probe`; verify's re-render is `render`) on its first and last frame and at most every 5 s between, as `{phase, frame, frames, elapsed_s, eta_s}` (the ETA is the phase's own). The agent tool logs each row to the server log (`lampway.motion`) and hands it to an optional `progress` callable on the render thread; the answer carries `progress`, one `{phase, frames, seconds}` per phase. The CLI writes each row to stderr as one TOON line (`progress: "render 120/450 frames, 48.1 s, eta 132.3 s"`), at most every 10 s (`--progress-every`, 0 for none), so stdout stays the one answer. Progress is wall-clock only: it never reaches a frame, a hash or the receipt. Live rows in the chat's tool bubble need the turn runner (`agent/turns.py`) to pass the callable: that file belongs to PRs #1 and #4.

## Receipt and artifact inventory

A completed receipt is `receipt.json`, with:

| Field group | Required meaning |
|---|---|
| Identity | `ok`, `tool=motion_graphics`, `run_id`, project-relative `out_dir`, `files` |
| Inputs | Effective relative scene/entry and name, dimensions/fps/duration/formats/samples, resolved template and variables |
| Source | `code_sha256`, `scene_files` with relative paths and SHA-256 |
| Engine | Chromium product/flags, ffmpeg version, encoder threads/args, driver SHA-256 |
| Frames | Count, `frame_hash` description, `frames_sha256_digest` |
| Outputs | Per requested format SHA-256, bytes and ffprobe result; artifact_hashes.contact covers the generated PNG, whose tiles keep the render's aspect (long edge 640 px; 16:9 stays 640 × 360) |
| Audit | `audit_stream` (`every_frames`, `audits`; null without `audit_every_s`); `self_check` counts/findings/samples; `determinism_probe` positions/differences/rendered frame count/timing |
| Operational | `network`, `timing_s`, optional forbidden-request error |

`frames.sha256` uses one `index t sha256` row per captured frame, five-digit minimum index, six-decimal timestamp, trailing newline; digest is SHA-256 of that UTF-8 file. Frame hash is SHA-256 of decoded RGB pixel bytes. Samples have PNG and JSON (frame/time/stats/authored audit/findings). `contact.png` labels sample index/time/finding count. Encoded hashes cover final metadata-cleaned files.

The receipt has no explicit schema version; verification strictly validates required shapes, finite numbers, saved bounds, frame-row count/canonical digest and source inventory digest. Untouched older generated receipts remain verifiable; Vault filing requires the trusted generated contact hash. Its frame/source/engine metadata are diagnostic provenance, not a signed attestation. Do not accept an untrusted receipt as a security authority. A versioned receipt contract and stricter validation require coordination with shared schema/registry owners.
