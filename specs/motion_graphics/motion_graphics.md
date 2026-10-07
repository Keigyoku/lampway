<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Motion graphics specification

Status: newly authored on 2026-10-07 with the captain's authorization. This is not a recovered historical specification. The docs-only branch starts at main `eab73f5f5a77780a7690378eec6c5dd44b468589`; runtime descriptions refer to [PR3 implementation `6d51409a`](https://github.com/Keigyoku/lampway/tree/6d51409ad2164b133a4eb17f9ac6b11a6b9559f0/server/lampway_server/motion). Landing these documents alone does not land or certify that implementation.

Read [tool and receipt contracts](tool.md), [scene and workflow contracts](scene.md), and [acceptance and open requirements](acceptance.md) together. **Implemented** means inspected runtime behavior at that commit; **tested** requires the evidence listed in acceptance; **open requirement** needs implementation and a falsifier; **decision** needs the captain's choice. A requirement written here is not a passing test.

## 1. Scope and source of authority

The recovered BUILD_ORDER directive calls for a 10–15 second site teaser from site assets, followed by a reusable motion tool and templates for site clips, tutorials, releases, facelift demos, report cards, TITAN animatics and UI motion. Its approach is local HTML/Canvas/SVG/three.js, headless Chromium capture, ffmpeg encoding, deterministic timing and self-checks. The captain has clarified that detailed formal motion specs had never been written.

The [October article](https://aiblewmymind.substack.com/p/claude-opus-5-5-video-animations) supplies design inspiration: code-driven frames, browser rendering and visual checks. Its readable article body was inspected; the subscriber prompt library and embedded video assets were not inspected. Its optional external services do not authorize integrations, uploads, paid generation or additional features.

The delivered interface is one local server-side agent tool, `lampway_motion_graphics`, with `render` and `verify` actions. It is unavailable over MCP. Output is silent video. Audio, external generation, a video job service, timeline editor, sharding, arbitrary frame ranges and cross-platform support are outside the implemented contract. Any extension requires a separate scope decision.

## 2. Timeline, rendering and export

Implemented: capture `n = round(duration_s × fps)` frames, refusing `n < 1`. Capture sequentially from frame zero in one browser at `t = i / fps`, ending at `(n−1)/fps`. Never render frames independently or shard a scene: browser image caches can change bytes when frames are visited in another order. Stream captured PNG frames into ffmpeg; hash decoded RGB pixels, not PNG encodings.

The normal render performs a second, fresh-browser pass, again sequential from zero through the final probe position. It compares at most eight evenly spaced RGB frame hashes and repeats sampled audits at their original positions. This detects sampled divergence; it does not prove every frame is a pure function of time. Verification recaptures every frame using the saved inputs and encoder thread count, without an extra probe.

Each completed run owns `motion/out/<name>-<code8>-<unique-run>/`. Exclusive run allocation and pinned output directories prevent collisions and tested parent-directory swaps. Export the requested MP4 and/or WebM plus samples, contact sheet, frame list and receipt. Public ToolSpec prose currently omits the unique suffix: this is a documentation/schema synchronization gap, not an alternative path contract.

Implemented export settings: MP4 uses libx264, high profile, slow preset, CRF 18 and faststart; WebM uses libvpx-vp9, CRF 30, zero target bitrate, good deadline, cpu-used 2 and row-mt enabled. Both use yuv420p, BT.709 limited range and fixed default four encoder threads. Metadata and chapters are removed, bitexact flags set, and x264 settings SEI removed. A conditional stream-copy remux removes encoder tags on engines that add them; already-clean outputs retain their bytes. Verification reuses the recorded thread count because MP4 bytes depend on it. These are inspected settings, not cross-engine byte-equality guarantees.

Reproduction requires matching captured frames, frame-list digest and requested new encoded hashes against the trusted receipt, with matching Chromium product and ffmpeg version strings. Engine flags, driver hash, scene inventory and encoder arguments are recorded for diagnosis; current verify does not enforce all of them. It does not check the original video files still exist or match their receipt hashes. Do not label this tamper evidence or existing-artifact integrity verification.

## 3. Provenance and publication

Record scene file hashes, combined code hash, timing, engine versions/flags, driver hash, encoder parameters, output bytes/hashes, self-check findings and template provenance. Generated output paths and scene-file inventory paths are project-relative. Callers must use relative scene/entry/template-source paths and publication scans: accepted absolute scene/entry inputs and unsanitized variable strings can persist in receipt provenance. Hashing inventories scene files once; the renderer does not freeze a scene snapshot or detect all later asset mutation. Preserve scene and output files unchanged through verification and Vault filing.

With Vault enabled and available, an accepted render files automatically before manual visual review or verification; no dedicated later-filing action exists. Accepted renders use the Asset Vault as follows: MP4 is the primary video when present, otherwise WebM. The other video is `variant_of` primary; QA receipt and contact sheet are `derived_from` primary. Effective defaulted template variables and resolved `id@version` are retained. Vault unavailability may spool capture records. Spool replay currently omits subsequent relationship creation; filing is not an atomic transaction and a relationship error can occur after assets are stored.

Render descriptors close before Vault reads logical paths. There is no atomic seal or hash revalidation across that handoff. Treat stable files as an operating precondition and the race as an open hardening requirement. Coordinate changes to shared provenance with PR1's owner; do not claim all filing paths have the render's descriptor protections.

## 4. Containment and security

Implemented: project-contained scene/entry paths; checked regular opened inodes; scene-contained `file:` and `data:` asset loading; CDP interception before browser asset reads; guards on page, iframe and popup loaders; workers refused; forbidden requests from both rendering passes fail acceptance. Output ancestors reject symlinks and remain descriptor-pinned through encoding, remuxing and probing. Receipt/frame reads are checked before verification and frame-list replacement is checked afterward.

These controls protect the application asset loader. They are not an OS filesystem sandbox against a hostile same-user process, browser exploit or substituted executable. The runtime uses Linux `fcntl`, `/proc/self/fd`, Unix descriptor passing and bash; Windows/macOS operation is unverified. Stronger isolation and platform targets remain decisions.

Keep egress opt-in, logging-before-send and spend confirmation contracts from root AGENTS unchanged. This tool requires no paid provider or network assets; refuse forbidden scene requests rather than enable a host. Never publish private source assets, owner paths, credentials or raw private validation receipts. Retain metadata stripping and the prepublish gate for exported media.

## 5. Errors, cancellation and resources

Implemented: input/setup refusals report a corrective error; browser and encoder are closed/aborted on runtime failure. A completed failed self-check retains output and receipt with `ok=false`, and files nothing in Vault. A mid-run exception can leave partial samples/output without a receipt. Verification attempts cleanup of its temporary rerender directory; cleanup errors are ignored.

Cancellation of the asynchronous tool caller does not stop the `asyncio.to_thread` worker. It may continue to produce outputs and file them in Vault. No cancellation-complete, stopped-worker or no-post-cancel-publication guarantee is implemented. This is an open hardening requirement; retention and desired cancellation filing behavior need an owner decision.

Input bounds cap a main pass at 7200 frames. They do not impose a wall deadline, CPU/memory or disk quota, byte caps, queue policy or motion-specific concurrency limit. CDP inactivity waits are not an end-to-end deadline; ffmpeg writes/probes and complete file reads are not bounded by such a deadline. Exact caps and queue/retention policy are decisions, not values inferred from the teaser. Add adversarial hangs, oversized assets and cancellation tests before claiming resource enforcement.

## 6. Completion and ownership

Report separately: render/self-check result, visual inspection, reproduction, media publication scan, Vault capture/relations, exact-head CI, and reference aggregate acceptance. Warnings remain visible even when `ok=true`. Synthetic capture adapters establish logic regressions; they never substitute for live Chromium/video acceptance.

PR3 owns motion render/verify/probe, video metadata and templates. PR1 owns reference runner/PII/R04/REUSE, shared TOON and registry/schema changes; PR4 owns agent Modes/Choices. Coordinate shared provenance, prompt schemas, egress launch registry and tool registry before code edits. New gates and fixes need observed RED then GREEN with a retained falsifier. No merge, deployment or paid operation follows from these documents.
