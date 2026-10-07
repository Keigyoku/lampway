<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# MCP wrapper and migration lane

Implementation source: the complete supplied MCP section (C0–C2, T1–T3), 27,896 UTF-8 bytes, SHA256 `2decc1a200d059fe1d1ff2f2afb022c17eaeb9d59fef5214c2364c670e8faa77`. The complete rendered-source archive was subsequently retrieved through the connected private Drive file: 207,757 bytes, SHA256 `f1904abaa4d598b6b0799a6bbb6578c52311b0018eb4cd463e0c541c413814ce`. All seven content hashes were verified; the 104,316-byte full text was read, and its MCP section matches exactly. This is a rendered DOM/text/accessibility capture, not a publisher export; external images are not bundled. Source and provenance receipts are retained outside the repository. The verified section is the requirements source; the captain's scope boundaries and decisions govern this lane.

Execution base: remote `lp/wave5`, fetched and independently verified at `287c9d63f5b8d0ed15a3bfcdfecad69d4961db26`. Original branch: `lp/mcp-wrapper-migration`; its published checkpoint `bc0a721` is preserved. The captain authorized a successor branch, `lp/mcp-wrapper-migration-main-20261007`, replayed onto fetched main `290ddd3a3a08ccc646ff4e3faa73326c09e1c154` on 2026-10-07. The initial pinned workspace commit was not used. No deployment, user desktop operation, provider spend or production asset change was performed. Later acceptance runs use isolated factory profiles and Xvfb. The captain subsequently authorized publishing this scoped branch at commit boundaries; remote SHA verification receipts are retained outside the tree. The integrator owns updates from `lp/wave5`; this lane never force-pushes.

Captain decisions: read-only OBSERVE declaration; one existing opt-in gates all pixels; TOON 4.3; pinned documentation ships with the server. In-app results remain JSON. Audit, Agent Mode migration and frontend sections are outside this lane.

| Contract | Implementation and evidence | Acceptance and verification |
|---|---|---|
| C0 shared pure TOON | Byte-identical client/server codec, AXI helpers and Studio parser integration; pinned official 4.3 fixtures: 160 encode, 385 decode, 160 roundtrip; regressions and deterministic property cases. Component run 739 passed; targeted existing Studio/compute run 79 passed. | No runtime TOON dependency or network. Full-suite outcome recorded separately. |
| C1 three-tool envelopes | TOON text and decoded-equivalent structuredContent, compact typed success/refusal schemas, strict unknown args before connection handling, 200-character truncation/full switch, metadata outside the document, help last. 21 focused envelope tests passed. | Legacy tools intentionally keep their existing transport. |
| C1 images | Configured project-root-relative PNG, byte cap, Pillow validation, anchored no-follow parent/file descriptors, regular files only, deletion after valid consumption; file and parent swap tests. | POSIX descriptor support is required; other platforms return `image_platform_unsupported`. Native pixel capture now has isolated GUI evidence; server image transfer retains targeted envelope/race tests. |
| C2 launcher guide | Live initialize instructions derive from offered tools; generated static fallback; real registry identifiers only and first inspect once present. 55 client and 20 server targeted guide tests passed. | Closed-app SDK fix is now green: synthesize pure config namespace; actual empty/saved-inspect profiles return generated fallback/resource/prompt with only offered identifiers. 26 targeted tests passed. |
| T1 home/scene/objects/object | Raw read-only OBSERVE, session-bound scene, metre/world coordinates, canonical stamp disclosure, selection fallback, logical list paging/count/total, bounded fields/unknown-field refusal. Real isolated binary reads all 12 views without scene/selection changes. | Pinned official named inputs now acquired; final chess home 80.01ms, bunny five-rim parity/no failures and three native object screenshots captured; all named tests 3 passed in 7.97s. Named screenshots and TOON replies have a completed side-by-side HTML evidence artifact. Functional component acceptance green; exact-head/package verification receipts are external. |
| T1 mesh | Reuses shared topology primitives, exact transformed rim measurements, definitive holes, evaluated counts, 64-entry geometry/UV/world/scale cache; real binary proves cache invalidation by opening a synthetic cube face. | Completion work now uses exact caller-owned world-metre shell orientation and uncapped deep defect scan, including evaluated/scaled inputs. Binary metric tests include 501 exact intersection rows, scaled/evaluated inputs and reflection; component acceptance green. |
| T1 UV | Shared UV metrics and mandated `UC._overlaps` per UDIM; exact metre seam before rounding; signed-area count of flipped faces, empty/degenerate states. | Completion work measures intra-island triangle overlap and sparse per-tile raster coverage. Final named helmet UV 1,648.36ms cold/17.60–20.25ms cached; canonical oracle confirms raw tile991 utilization 0 and overlap .999. Final serial named run has no failures. |
| T1 parts/layers | Existing segmentation and material-stack engines, world metre bounds and final rounding; no layer creation. | Cooperative shared segmentation/UV/topology checks implemented; component acceptance green, including two-shell/Suzanne/plane original cases (3 passed). |
| T1 relations/file/schema/help | AABB relation ordering and shared precise BVH surfaces with deadline checks; exact pinned Blender Lab file-summary helpers; project-relative/basename paths; generated typed per-view schemas with falsifier/check tests and rail registration; contextual templates carry filters and quote names. | Completion work supplies shared BVH surface-distance/closed-volume parity and unrounded classification with real synthetic falsifiers. No longer an accepted skipped dependency. |
| T1 budget | Cooperative deadline checks in shared engines, hashing and objects/pairs; exceeded work reported as skipped. | Completion receipt: 2M triangles, requested 100ms, cold/refusal 0.91ms and repeated refusal 0.16ms (<200ms), via conservative admission before hashing/BMesh plus cooperative traversal checks. Indivisible native evaluation/BVH work prevents a universal deadline guarantee. |
| T2 focus | Native framing, selection preservation, refusal before hidden mutation, explicit unhide owns one undo; pump suppresses automatic undo only inspect/view. Isolated real binary focus without pixels passed. | Real isolated GUI focus/capture green: center (3,4,5), Camera selection/active unchanged, one actual undo restores hidden state. All twelve inspect history checks green. |
| T2 screenshot/render | Existing UI opt-in, capture masking, redraw barrier and resize/render guards; scene_render coordinator and asynchronous timer completion; exclusive project output files; typed render-busy refusals. | Isolated Xvfb GUI green: three native editor PNGs ≤50,000 bytes, secret center [0,0,0], two 256px thumbnail PNGs with restored engine/resolution/filepath and busy refusal; subsequent default-current API render produces 320×240 current.png with full relevant settings unchanged (1 passed in 33.25s). Scene-tab screenshot switching refuses capture_busy rather than stale framebuffer. |
| T3 offline docs | 4,327 pinned API/manual RST sources, provenance, licences and no runtime egress; search-to-get scoped manual flow; 63 targeted server tests and socket-prohibited offline checks passed. Current local wheel rebuilt after documented privacy/provenance updates: 6,983,071 bytes, SHA256 `34a60fe61c4de63a5c78208fc2ad91c405104f9f2710f3e470ed7c48736b3605`; ZIP verification passes all 4,327 current RST hashes, three byte-identical licence texts and source/manual provenance; extracted-wheel home/API/manual run with sockets/subprocesses prohibited. Exact-head aggregate receipts remain external. | Captain clarification makes HEAD:upstream authoritative; source/manual commit provenance and version-derived backlinks are served separately. Official docs URLs returned 403 and are marked availability-unverified; no separate manual-tag blocker. See `mcp-wrapper-t3.md`. |

## Requirement completion review

The [complete requirement review](mcp-wrapper-requirements.md) maps C0–C2/T1–T3 against the completed original lane and the successor replay onto main `290ddd3a3a08ccc646ff4e3faa73326c09e1c154`. The acceptance column distinguishes tested component behavior from final exact-head aggregate and packaging verification. Required functionality is not waived or replaced by dependency skips. The captain requires completion of the full MCP scope; external engine ownership does not turn a skipped required measurement into acceptance. Completion fixes close premature rounding, discarded deep-scan totals, incomplete help fields and budget retry arguments; isolated GUI receipts close masking/focus/render/history gaps. The matrix records each closure: original synthetic cases and default-current render are green, named screenshot/reply presentation is completed, C2 and clarified documentation policy are resolved. Home now uses exact O(1) triangle counts per object and satisfies the O(objects) geometry traversal contract. Final exact-head aggregate/package/gate receipts are retained outside this report to avoid self-reference.

## Shared dependency boundaries

The completion work implements the required read-only engine interfaces in this scoped working tree; these are no longer proposed interfaces used to justify skipped MCP contracts:

- `defect_scan.scan_bmesh(bm, kinds, thin_threshold_m, budget)` takes the caller-owned evaluated world-metre bmesh, returns measurements without scene mutation, and checks the deadline cooperatively.
- `workflows.shell_orientation_bmesh(bm, ...)` exposes exact shell orientation counts on that same metre/evaluated representation with no mutation and a cooperative deadline.
- The shared `features/surface_relations.py` engine accepts evaluated world-metre surfaces and supplies BVH distance and closed-mesh parity under cooperative deadline checks.

Main now supplies the external MCP caller interfaces: operation begin/end and
`agent_ctx.mcp_operation_id` propagation. The successor retains main's
`McpServer._leased_script` rather than introducing another lease implementation;
all Blender-backed MCP tools, including inspect/view, use it. Offline docs stay
server-side. Earlier wording that treated leases as an absent interface is
superseded. The audit implementation remains main-owned; validating its caller
integration with required MCP behavior is in scope. Agent Mode bound-session and
capability contracts remain outside this implementation scope.

The earlier null/skipped cheap orientation, evaluated/scaled deep and precise
relation rows are superseded by measured results. Standalone closed-app SDK
initialization remains C2 scope; main's isolated-launcher fix is inherited.

## Reconciliation with main

The complete original matrix remains applicable after replay; no C0–C2/T1–T3
requirement is waived. Source inspection on the successor confirms the inspect,
view and offline documentation engines are unchanged from the original completed
lane, and `HEAD:upstream` remains `fbe6228777e7d9afefcd61a413844e790ae75db7`.
Prior timing, GUI and package receipts below describe the original checkpoint;
source equality does not constitute a rerun on the successor. Final successor
aggregate, binary and wheel receipts belong to the coordinator and are retained
outside this report to avoid embedding the containing commit's own hash.

| Main-owned audit finding | Retained implementation / scoped reconciliation |
|---|---|
| F1 isolated launcher | Inherited standalone bootstrap and [isolated-launcher test](../../tests/mcp/test_launcher_isolated.py); C2 retains generated fallback/live instructions. No second launcher path. |
| F2 operation leases | Main's begin → execute with operation id → end in finally remains in [MCP server](../../server/lampway_server/mcp.py) and [agent caller](../../server/lampway_server/agent/turns.py). [Server lease](../../server/tests/test_mcp_operation_lease.py) and [real client dispatch contract](../../tests/test_mcp_server_lease_contract.py) tests cover the inherited interface. Wrapper test doubles must model it. |
| F3 minimal guide repair | C2's registry-generated live guide/static fallback supersedes main's corrected inline text; canonical static-guide regeneration and identifier checks remain required after reconciliation. |
| F9 minimal TOON repair | C0's full byte-identical 4.3 codec supersedes main's limited encoder and retains the `dumps`/AXI compatibility interfaces. Main's [fixture regression](../../server/tests/test_toon_out_fixtures.py) remains alongside full official fixtures. |
| F20 failed-tool logging | Main's `pump.respond` failure log (tool/request/error/type) is retained. The wrapper changes only inspect/view automatic undo behavior; no second logging path. |

Main's batch-form registry, translated-asset canon handling, segmentation
`max_parts`/isolated-group safeguards, UV warning/paging changes, UI labels and
sandbox process-owned temp root are preserved. Inspection continues to use the
shared read-only primitives, without invoking the splitting or mutation paths.
The final verifier must exercise the combined registry, leased execution,
generated guide, shared codec and real native fixtures; an unchanged engine alone
does not establish integration acceptance.

Isolated successor component receipts are now available (before final
consolidation; these do not identify the eventual final head):

- `<evidence>/tests/rebased-budget/summary.json`: **21 passed, zero skips**
  (5 standalone, 13 binary, 3 named assets), factory background profiles without
  install synchronization. The 2M/100ms conservative admission refusal measured
  3.50ms cold and 0.19ms repeated; the latter is a repeated refusal, not a cache hit.
- Same named series: helmet mesh 265.05ms cold / 20.35–22.29ms cached, UV
  1,827.03ms cold / 19.28–29.38ms cached; all required thresholds pass.
  Full chess dashboard is 1.47ms, **49 objects / 1,498,828 triangles**, confirmed
  in `rebased-budget/ABeautifulGame.json`. Bunny mesh is 851.13ms with no failures.
- `<evidence>/tests/rebased-geometry/{translated_canonical,refused_file_counts}.json`:
  two new native cases pass. Translation preserves canon identity and changes
  world hole centroids while leaving normalization unchanged; refused imports
  preserve home/file datablock counts, while accepted imports update them.
- `<evidence>/tests/rebased-view/pytest.log`: **61 passed, one baseline failure**,
  40.98s. The failure still names the absent `docs/render-job-contract.md`; this
  run is not an all-green suite. Native view/GUI component assertions passed.
- Coordinator component receipts record **27 generated-guide checks passed**,
  preserving main's workflow with actual backend and client-local identifiers,
  under the 1,477-byte cap, plus **27 T3 checks passed**. The interim successor
  wheel is 7,159,089 bytes; final wheel identity and verification remain pending.
- Exact main baseline `<evidence>/tests/main-reconciliation-base/head-server.log`:
  **1,755 passed / 32 skipped**, pytest elapsed 148.23s. Successor server
  integration initially exposed stale lease test doubles (16 failures), then
  the corrected fixture series passed **54 tests** using main's actual
  `Agent._blender_script` and gated client. It enforces begin/execute/end order,
  session/operation identity, failure cleanup and retry; production leases are
  unchanged. Final consolidated-head rerun remains pending.
- `<evidence>/tests/rebased-reuse-comparison.json`: zero new findings in every
  REUSE category compared with exact main; existing repository findings remain.

Main alone owns standalone launcher bootstrap after reconciliation: the duplicate
lane change was removed from the diff. These receipts strengthen scoped
integration evidence but do not substitute for final consolidated-head verification.

## Integration and verification

Narrow routing changes are part of the wrapper side-effect contract: only inspect is read-only through the render gate; evaluated inspect refuses when rendering. Inspect and view suppress executor auto-undo; view still owns the single explicit unhide undo. View uses raw `Need` consumption, keeping OBSERVE exclusively read-only. Known executor refusal codes survive MCP translation.

RED evidence preceded codec, registration, guide, schema, measurement, image race/validation, and routing fixes. The previous checkpoint combined client component run passed 75 tests and retained one baseline documentary failure: `test_contract_doc_exists_and_is_linked` expects `docs/render-job-contract.md`, absent at the execution base. This lane does not invent that other contract. The historical initial exact-base MCP client run had 243 passes and three failures; C2 first fixed guide length. The UI-context regex remained a baseline finding; the SDK child bpy-import finding has since been fixed as described next. Subsequent requirement review establishes that the SDK child failure blocks C2’s required closed-app fallback, so the narrow standalone namespace fix was completed in scope, with 26 targeted tests green; it is not excluded by audit launcher ownership.

The independent full server base run passed 1,605 tests with 32 explicit live/optional skips. The previous checkpoint full server run passed 1,654 tests with 32 skips and exit zero, using the same interpreter and explicit lane server import path. Reference test-environment verification passed after a local checkout of the exact upstream pin. Rail full check and documentation PII check passed; generated tools and schemas are fresh. Exact committed-head evidence is recorded by the final integration reviewer. Current live component receipts establish pixels, named assets and the required budget case separately. They do not imply an all-green repository baseline; final exact-head aggregate results are independent external receipts.

The previous checkpoint packaging review replaced inherited brand-marked GPL copies with verbatim licence texts from the pinned Blender source. That earlier local wheel was 6,979,645 bytes, SHA256 `b5705c8d5532f9827d1d7a0bc8deac4977f7eaeed931993f579d50f7af7dd06a`; all 4,327 corpus hashes and the exact GPL texts were checked inside the ZIP. This is a local packaging receipt, not a published release. Full REUSE lint has existing repository findings; the scoped bundled licence issue was corrected, with baseline-relative evidence retained outside the tree.

Staged whitespace validation passes for authored code and reports. The byte-preserved pinned documentation corpus and vendor helper retain upstream trailing whitespace/blank lines and RST heading underline sequences that Git flags as conflict markers. Imported bytes were preserved except three documented privacy substitutions; original and packaged hashes are recorded separately in the manifest and NOTICE.

Completion packaging receipt: the current local rebuild produced `lampway_server-0.0.1-py3-none-any.whl`, **6,983,071 bytes**, SHA256 `34a60fe61c4de63a5c78208fc2ad91c405104f9f2710f3e470ed7c48736b3605`. It includes the current documented corpus substitutions and derived source/manual provenance. This build receipt supersedes the earlier wheel identity; ZIP validation verified all **4,327 current RST hashes**, including publication derivatives, three byte-identical licence texts and authoritative 5.2 source/manual provenance. Extracted-wheel home, Object.location lookup and Bevel manual search passed with sockets/subprocesses prohibited. The package-verification receipt and final exact-head aggregate/gate results are independently retained outside the tree; the latter are not claimed all green in this report. This is not a published release.

Final aggregate verification exposed two lane regressions before handoff. The packaging-only provenance Git reader is now explicitly accounted for as a local launch in the existing egress audit (read-only rev-parse/config/show, no fetch). The majority-winding binary fixture now uses distinct UV islands: its previous coincident islands qualified as canon 13 stacked mirrors. Its integer/count assertion remains unchanged, alongside the dedicated stacked-mirror-zero falsifier. Neither correction relaxes a gate or changes the canonical winding rule. Exact-head rerun receipts are retained outside the repository.

The merged refusal-name audit exposed a registry interface mismatch: local MCP scene/UI aliases are offered by the launcher, outside server agent `TOOLS`. Its lookup now unions agent names with `agent_files.generate.mcp_local_tool_names()`, which reads the actual local schema and alias tables at packaging/test time. It adds no per-name exemptions; a planted unregistered refusal remains rejected. This limited shared gate integration preserves the audit owner’s rule. Wrapper envelope fixtures now enforce main’s actual begin/script/end lifecycle rather than using an unleased placeholder socket; production lease code is unchanged.

Final verification of the first reconsolidated checkpoint found 23 missing descriptions on new parameters; all were supplied from these contracts without raising the schema ratchet. A separate library failure was reproduced on exact main with identical files: PYTHONHASHSEED=6 makes two fake CC0 maps collide, while seed 0 passes. Its proof remains external; no library implementation or test was changed. Main’s new default Gitleaks scan also reported 32 manifest values: verified public SHA256 digests and a public SPDX licence identifier. Manifest v2 preserves all 16 legacy metadata fields exactly through the runtime normalizer, using separate path/hash and scope/identifier records; the unchanged scanner reads the new data with zero findings. No allowlist, workflow, secret rule or security setting was changed. Both published checkpoints remain preserved; the final clean v2 successor is reconsolidated directly on the same fetched main so its introduced history contains the corrected serialization.
