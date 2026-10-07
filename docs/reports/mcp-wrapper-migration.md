<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# MCP wrapper and migration lane

Implementation source: the complete supplied MCP section (C0–C2, T1–T3), 27,896 UTF-8 bytes, SHA256 `2decc1a200d059fe1d1ff2f2afb022c17eaeb9d59fef5214c2364c670e8faa77`. The complete rendered-source archive was subsequently retrieved through the connected private Drive file: 207,757 bytes, SHA256 `f1904abaa4d598b6b0799a6bbb6578c52311b0018eb4cd463e0c541c413814ce`. All seven content hashes were verified; the 104,316-byte full text was read, and its MCP section matches exactly. This is a rendered DOM/text/accessibility capture, not a publisher export; external images are not bundled. Source and provenance receipts are retained at `/workspace/mcp-source`. The verified section is the requirements source; the captain's scope boundaries and decisions govern this lane.

Execution base: remote `lp/wave5`, fetched and independently verified at `287c9d63f5b8d0ed15a3bfcdfecad69d4961db26`. Local branch: `lp/mcp-wrapper-migration`. The initial pinned workspace commit was not used. No merge, deployment, desktop operation, provider spend or production asset change was performed. The captain subsequently authorized publishing this scoped branch at commit boundaries; remote SHA verification receipts are retained outside the tree. The integrator owns updates from `lp/wave5`; this lane never force-pushes.

Captain decisions: read-only OBSERVE declaration; one existing opt-in gates all pixels; TOON 4.3; pinned documentation ships with the server. In-app results remain JSON. Audit, Agent Mode migration and frontend sections are outside this lane.

| Contract | Implementation and evidence | Remaining acceptance |
|---|---|---|
| C0 shared pure TOON | Byte-identical client/server codec, AXI helpers and Studio parser integration; pinned official 4.3 fixtures: 160 encode, 385 decode, 160 roundtrip; regressions and deterministic property cases. Component run 739 passed; targeted existing Studio/compute run 79 passed. | No runtime TOON dependency or network. Full-suite outcome recorded separately. |
| C1 three-tool envelopes | TOON text and decoded-equivalent structuredContent, compact typed success/refusal schemas, strict unknown args before connection handling, 200-character truncation/full switch, metadata outside the document, help last. 21 focused envelope tests passed. | Legacy tools intentionally keep their existing transport. |
| C1 images | Configured project-root-relative PNG, byte cap, Pillow validation, anchored no-follow parent/file descriptors, regular files only, deletion after valid consumption; file and parent swap tests. | POSIX descriptor support is required; other platforms return `image_platform_unsupported`. Live pixel capture remains unverified. |
| C2 launcher guide | Live initialize instructions derive from offered tools; generated static fallback; real registry identifiers only and first inspect once present. 55 client and 20 server targeted guide tests passed. | Broader MCP client suite retains the two existing UI-context/SDK-child baseline failures. |
| T1 home/scene/objects/object | Raw read-only OBSERVE, session-bound scene, metre/world coordinates, canonical stamp disclosure, selection fallback, logical list paging/count/total, bounded fields/unknown-field refusal. Real isolated binary reads all 12 views without scene/selection changes. | Named acceptance assets and performance measurements were not supplied/run. |
| T1 mesh | Reuses shared topology primitives, exact transformed rim measurements, definitive holes, evaluated counts, 64-entry geometry/UV/world/scale cache; real binary proves cache invalidation by opening a synthetic cube face. | Cheap flipped-shell count is null with an explicit skipped owner dependency. Deep evaluated/scaled defects are skipped. |
| T1 UV | Shared UV metrics and mandated `UC._overlaps` per UDIM; exact metre seam before rounding; signed-area count of flipped faces, empty/degenerate states. | Existing overlap helper does not detect all self-overlap inside one island; shared engine owner must supply that capability. |
| T1 parts/layers | Existing segmentation and material-stack engines, world metre bounds and final rounding; no layer creation. | Cooperative engine budgets remain unavailable. |
| T1 relations/file/schema/help | AABB relation ordering with explicit precise-BVH skip; exact pinned Blender Lab file-summary helpers; project-relative/basename paths; generated typed per-view schemas with falsifier/check tests and rail registration; contextual templates carry filters and quote names. | Precise surface-distance/BVH relations require the owning engine interface. |
| T1 budget | Coarse deadline checks before/after hashing and between objects/pairs; exceeded work reported as skipped. | The required 100ms budget within 2x on 2M triangles is **not met or claimed**: current shared hash/metric/segmentation calls are not cooperatively interruptible. |
| T2 focus | Native framing, selection preservation, refusal before hidden mutation, explicit unhide owns one undo; pump suppresses automatic undo only inspect/view. Isolated real binary focus without pixels passed. | Live pixels and actual unhide undo history in GUI unverified. |
| T2 screenshot/render | Existing UI opt-in, capture masking, redraw barrier and resize/render guards; scene_render coordinator and asynchronous timer completion; exclusive project output files; typed render-busy refusals. | No desktop or live pixel/render acceptance run. Scene-tab screenshot switching refuses `capture_busy` rather than returning a stale framebuffer. |
| T3 offline docs | 4,327 pinned API/manual RST sources, provenance, licences and no runtime egress; search-to-get scoped manual flow; 63 targeted server tests and socket-prohibited offline checks passed. Final wheel contains every manifest hash. | Manual source is a pinned release-branch commit, not a release tag; core version and branded app version are separately recorded. See `mcp-wrapper-t3.md`. |

## Shared dependency boundaries

The geometry engine lane owns these proposed read-only interfaces; this lane does not change `features/defect_scan.py` or `workflows.py`:

- `defect_scan.measure_bmesh(bm, kinds, thin_threshold_m, max_candidates, budget/deadline)` takes the caller-owned evaluated world-metre bmesh, returns measurements without scene mutation, and checks the deadline cooperatively.
- `workflows.shell_orientation_bmesh(bm, ...)` exposes exact shell orientation counts on that same metre/evaluated representation with no mutation and a cooperative deadline.
- The precise relation engine must similarly accept caller-owned evaluated world-metre meshes and return BVH surface relationships under a deadline.

The full-source audit also identifies standalone launcher startup and operation leases as external-call dependencies owned by other crews. Its timings used workarounds and do not establish direct-MCP acceptance on this head. The lease interface is `begin(operation_id, session_id, timeout)`, propagation through `agent_ctx.mcp_operation_id`, and `end` in a finally block. Agent Mode bound-session and capability contracts are future caller interfaces, not implementation scope here.

Until those interfaces exist, skipped sections are explicit rather than presented as computed deep results. The existing base-world-scale-one defect scan can be reused without changing its algorithm.

## Integration and verification

Narrow routing changes are part of the wrapper side-effect contract: only inspect is read-only through the render gate; evaluated inspect refuses when rendering. Inspect and view suppress executor auto-undo; view still owns the single explicit unhide undo. View uses raw `Need` consumption, keeping OBSERVE exclusively read-only. Known executor refusal codes survive MCP translation.

RED evidence preceded codec, registration, guide, schema, measurement, image race/validation, and routing fixes. The final combined client component run passed 75 tests and retained one baseline documentary failure: `test_contract_doc_exists_and_is_linked` expects `docs/render-job-contract.md`, absent at the execution base. This lane does not invent that other contract. The broader initial exact-base MCP client run had 243 passes and three failures; C2 fixed guide length, leaving the UI-context regex and SDK child bpy-import failures outside scope.

The independent full server base run passed 1,605 tests with 32 explicit live/optional skips. The precommit current-tree full server run passed 1,654 tests with 32 skips and exit zero, using the same interpreter and explicit lane server import path. Reference test-environment verification passed after a local checkout of the exact upstream pin. Rail full check and documentation PII check passed; generated tools and schemas are fresh. Exact committed-head evidence is recorded by the final integration reviewer. Passing components do not imply live pixels, full acceptance assets, budget conformance or an all-green repository.

A final packaging review replaced inherited brand-marked GPL copies with verbatim licence texts from the pinned Blender source. The rebuilt local wheel is 6,979,645 bytes, SHA256 `b5705c8d5532f9827d1d7a0bc8deac4977f7eaeed931993f579d50f7af7dd06a`; all 4,327 corpus hashes and the exact GPL texts were checked inside the ZIP. This is a local packaging receipt, not a published release. Full REUSE lint has existing repository findings; the scoped bundled licence issue was corrected, with baseline-relative evidence retained outside the tree.

Staged whitespace validation passes for authored code and reports. The byte-preserved pinned documentation corpus and vendor helper retain upstream trailing whitespace/blank lines and RST heading underline sequences that Git flags as conflict markers. Those imported bytes were not rewritten, preserving the verified manifest hashes.
