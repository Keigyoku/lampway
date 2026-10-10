<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Tool and receipt contracts

Behavior follows the [agent wrapper](../../server/lampway_server/agent/motion_tools.py) and [renderer](../../server/lampway_server/motion/__init__.py) on this branch. This describes current behavior and remaining boundaries; it does not introduce an alternate executable schema.

## Inputs

The declared JSON object rejects additional properties. Render properties are:

| Property | Declared value and runtime behavior |
|---|---|
| `action` | `render` (default) or `verify` |
| `scene` | Scene folder inside project; convention is project-relative. Runtime also accepts contained absolute paths. |
| `html` | Inline HTML instead of folder, needs `name`; written to `motion/scenes/<name>/index.html`. A differing existing entry is refused. |
| `entry` | Scene-contained HTML entry; default `index.html` |
| `name` | Lowercase kebab-case; defaults to scene directory name |
| `fps` | Integer, excluding booleans, 1–60; default 30 |
| `width`, `height` | Even integers, excluding booleans; long edge 16–3840, short edge 16–2160 (3840 × 2160 and 2160 × 3840 both allowed); defaults 1920 × 1080 |
| `duration_s` | Numeric, excluding booleans, `(0,120]`; otherwise scene duration |
| `formats` | Nonempty unique list drawn from `mp4`, `webm`; missing means both; empty/null refused |
| `samples` | Optional nonempty list of 1–24 finite nonnegative numeric seconds, excluding booleans; positions rounded, deduplicated and clamped to final frame |
| `template` | Optional motion-graphics template `id` or `id@version`; unversioned resolves to a version |
| `variables` | Finite JSON template variable object with string keys; defaults filled by prompt renderer; provenance only |
| `vault` | Boolean only, default true; false disables filing |
| `receipt` | Verify requires a saved project-contained receipt path |

Default audits cover first/last plus ten interior positions, deduplicated for short clips. Both render and verify validate supplied values before work. Arguments must be an object; scene/html are mutually exclusive; supplied text values must be nonempty strings, variables JSON-shaped and numeric samples finite. Omitted optional values retain their defaults; explicit null wire values are refused. Saved receipt inputs and nested engine/output/source/frame fields are checked before renderer launch. The current internal normalized representation uses null for omitted optional values; it is not an alternate wire schema.

## Outputs and refusal semantics

The agent wrapper returns `(JSON text, is_error)`. Render JSON includes `ok`, `run_id`, `out_dir`, `files` (requested videos/contact), `code_sha256`, `frames`, `frames_sha256_digest`, `outputs` (hash/bytes), `self_check` (fail/warn/findings), `network`, selected timing metrics and `vault`. A completed failure sets `is_error=true`; paths can still exist. Exceptions/refusals return `ok=false,error`, with no promise that no partial output exists.

Vault status includes `assets`, `spooled`, `filed`, optionally `partial` and `error`. Cancellation returns `ok=false,cancelled=true` after owned cleanup, with committed assets and filing state; no further filing operation is admitted. `ok=true` is render acceptance, not proof of successful Vault filing. Default Vault behavior does not apply when no Vault instance is available. No network or paid receipt is required.

Verify JSON includes `reproduced`, `frames_differing`, `mp4_equal`, `webm_equal`, `engine_matches`, normally receipt and frame count, plus `integrity_matches`/per-format checked original-media results and `provenance_matches`/source-driver-flags results. An unrequested format has equality `null`. An engine mismatch reports false reproduction and an explanation before frame comparison. A negative reproduction is still a normal verify response (`is_error=false`); consumers must inspect reproduction, integrity and provenance separately. See [reproduction limits](motion_graphics.md#2-timeline-rendering-and-export).

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
| Audit | `self_check` counts/findings/samples; `determinism_probe` positions/differences/rendered frame count/timing |
| Operational | `network`, `timing_s`, optional forbidden-request error |

`frames.sha256` uses one `index t sha256` row per captured frame, five-digit minimum index, six-decimal timestamp, trailing newline; digest is SHA-256 of that UTF-8 file. Frame hash is SHA-256 of decoded RGB pixel bytes. Samples have PNG and JSON (frame/time/stats/authored audit/findings). `contact.png` labels sample index/time/finding count. Encoded hashes cover final metadata-cleaned files.

The receipt has no explicit schema version; verification strictly validates required shapes, finite numbers, saved bounds, frame-row count/canonical digest and source inventory digest. Untouched older generated receipts remain verifiable; Vault filing requires the trusted generated contact hash. Its frame/source/engine metadata are diagnostic provenance, not a signed attestation. Do not accept an untrusted receipt as a security authority. A versioned receipt contract and stricter validation require coordination with shared schema/registry owners.
