<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Tool and receipt contracts

Behavior pinned to [agent wrapper](https://github.com/Keigyoku/lampway/blob/6d51409ad2164b133a4eb17f9ac6b11a6b9559f0/server/lampway_server/agent/motion_tools.py) and [renderer](https://github.com/Keigyoku/lampway/blob/6d51409ad2164b133a4eb17f9ac6b11a6b9559f0/server/lampway_server/motion/__init__.py). This describes current behavior and identifies validation gaps; it does not introduce an alternate executable schema.

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
| `width`, `height` | Even integers, excluding booleans; 16–3840 × 16–2160; defaults 1920 × 1080 |
| `duration_s` | Numeric, excluding booleans, `(0,120]`; otherwise scene duration |
| `formats` | Nonempty unique list drawn from `mp4`, `webm`; missing means both; empty/null refused |
| `samples` | Optional nonempty list of 1–24 nonnegative numeric seconds, excluding booleans; positions rounded, deduplicated and clamped to final frame |
| `template` | Optional motion-graphics template `id` or `id@version`; unversioned resolves to a version |
| `variables` | Template variable object; defaults filled by prompt renderer; provenance only |
| `vault` | Declared boolean, default true; current runtime disables only literal false |
| `receipt` | Verify requires a saved project-contained receipt path |

Default audits cover first/last plus ten interior positions, deduplicated for short clips. `verify` reuses saved render inputs and returns early from the normal argument validator. Prefer a single `scene` or `html` source; current runtime chooses `html` when both are provided. Some declared types are coerced or truthiness-defaulted in direct calls (including non-object arguments), and sample finiteness is not separately checked. Strict JSON type, finite-number, source exclusivity and receipt-structure validation are open hardening work; callers should adhere to the declared shape.

## Outputs and refusal semantics

The agent wrapper returns `(JSON text, is_error)`. Render JSON includes `ok`, `run_id`, `out_dir`, `files` (requested videos/contact), `code_sha256`, `frames`, `frames_sha256_digest`, `outputs` (hash/bytes), `self_check` (fail/warn/findings), `network`, selected timing metrics and `vault`. A completed failure sets `is_error=true`; paths can still exist. Exceptions/refusals return `ok=false,error`, with no promise that no partial output exists.

Vault status includes `assets`, `spooled`, `filed`, optionally `error`. `ok=true` is render acceptance, not proof of successful Vault filing. Default Vault behavior does not apply when no Vault instance is available. No network or paid receipt is required.

Verify JSON includes `reproduced`, `frames_differing`, `mp4_equal`, `webm_equal`, `engine_matches`, normally receipt and frame count. An unrequested format has equality `null`. An engine mismatch reports false reproduction and an explanation before frame comparison. A negative reproduction is still a normal verify response (`is_error=false`); consumers must inspect `reproduced`. See [reproduction limits](motion_graphics.md#2-timeline-rendering-and-export).

## Receipt and artifact inventory

A completed receipt is `receipt.json`, with:

| Field group | Required meaning |
|---|---|
| Identity | `ok`, `tool=motion_graphics`, `run_id`, project-relative `out_dir`, `files` |
| Inputs | Effective scene/entry/name (supplied absolute scene/entry can persist), dimensions/fps/duration/formats/samples, resolved template and variables |
| Source | `code_sha256`, `scene_files` with relative paths and SHA-256 |
| Engine | Chromium product/flags, ffmpeg version, encoder threads/args, driver SHA-256 |
| Frames | Count, `frame_hash` description, `frames_sha256_digest` |
| Outputs | Per requested format SHA-256, bytes and ffprobe result |
| Audit | `self_check` counts/findings/samples; `determinism_probe` positions/differences/rendered frame count/timing |
| Operational | `network`, `timing_s`, optional forbidden-request error |

`frames.sha256` uses one `index t sha256` row per captured frame, five-digit minimum index, six-decimal timestamp, trailing newline; digest is SHA-256 of that UTF-8 file. Frame hash is SHA-256 of decoded RGB pixel bytes. Samples have PNG and JSON (frame/time/stats/authored audit/findings). `contact.png` labels sample index/time/finding count. Encoded hashes cover final metadata-cleaned files.

The receipt has no explicit schema version or strict receipt validator. Its frame/source/engine metadata are diagnostic provenance, not a signed attestation. Do not accept an untrusted receipt as a security authority. A versioned receipt contract and stricter validation require coordination with shared schema/registry owners.
