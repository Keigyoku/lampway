<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# MCP wrapper requirement review

This review maps the complete C0–C2/T1–T3 specification to the completed original
lane and its successor `lp/mcp-wrapper-migration-main-20261007`, replayed onto main
`290ddd3a3a08ccc646ff4e3faa73326c09e1c154` on 2026-10-07. The original published
checkpoint `bc0a721` is preserved. Live receipts below describe that original
checkpoint; the reconciliation section distinguishes successor source checks
from final exact-commit tests, which remain the coordinator's responsibility. The requirements source is the supplied
[artifact](https://claude.ai/artifact/72F22QoSzhaWMqNpRhJsnD), whose complete
MCP section has SHA256 `2decc1a200d059fe1d1ff2f2afb022c17eaeb9d59fef5214c2364c670e8faa77`.
The captain's decisions supersede the proposal: OBSERVE, one opt-in for all
pixels, TOON 4.3 and bundled authoritative documentation. In-app replies remain
JSON. Audit and Agent Mode implementation are excluded; required MCP acceptance
measurements remain part of MCP scope.

“Present” below means the cited code implements the requirement; it does not
mean this review reran its tests. “Open” means the requirement is unfinished or
its required evidence has not been obtained. A dependency explanation does not
close an open requirement. Prior run receipts are in
[migration report](mcp-wrapper-migration.md) and [T3 report](mcp-wrapper-t3.md).

## C0: shared TOON

| Requirement | Code and tests | Review |
|---|---|---|
| Pure shared codec; no bpy or runtime third-party dependency; unchanged AXI call interfaces | [client codec](../../src/scripts/mixar/modules/common/toon/codec.py), [server codec](../../server/lampway_server/compute/toon_out.py), [AXI](../../src/scripts/mixar/modules/lampway_tools/axi.py), [codec tests](../../tests/toon/test_codec.py) | Present; byte identity is tested. |
| `encode(value, delimiter, indent_size)`; strict decoder for Studio/tests | Same codec; [Studio reader](../../server/lampway_server/studios/toon.py) | Present. |
| Pin 4.3 following captain decision; official fixture licensing/provenance | [fixture receipt](../../tests/toon/fixtures/PROVENANCE.md), [REUSE](../../REUSE.toml) | Present; fixture source commit `eee00a23c2bdd0d4ae3324529fbbb7c3d3fd1359`. |
| Shortest round-trip numbers; integral floats; no invented nulls/nonuniform tables; nested/keyed tables; primitive/list forms | Codec; official fixtures and codec regressions | Present in covered fixture cases. |
| NaN/Inf→null, −0→0, tuples/sets and mathutils sequences→arrays, unsupported→null, surrogate refusal | Codec normalize; [roundtrip tests](../../tests/toon/test_roundtrip.py) | Present; mathutils normalization is source-level, not demonstrated here on a real binary. |
| Quoting keywords/numbers/comments/colon/dash and nonidentifier keys; lowercase escapes | Codec and fixtures | Present in covered fixture cases. |
| Empty `key: []`; no trailing newline/spaces; CLI stdout behavior | AXI and codec tests | Present. |
| Hypothesis JSON-model roundtrip including falsifier inputs | Roundtrip and codec tests | Present; 1,000 deterministic generated examples configured. |
| Studio parses every driver output after switch | Studio integration tests cited in migration report | Prior component evidence; this review did not enumerate/run every runtime driver. |

## C1: envelopes and AXI rules

| Requirement | Code and tests | Review |
|---|---|---|
| Only three new tools opt in; content[0] TOON, same structuredContent, outputSchema | [envelope](../../server/lampway_server/mcp_envelope.py), [MCP](../../server/lampway_server/mcp.py), [envelope tests](../../server/tests/test_mcp_envelope.py) | Present; numerical canonicalization uses decode of encoded bytes. |
| Codex gets text-only through existing presentation | [presentation](../../src/scripts/mixar/modules/mcp_bridge/core/presentation.py) | Existing presentation path; live Codex client not rerun. |
| Minimal 3–4 default fields, explicit named fields and `*`, unknown fields refused | [inspection orchestrator](../../src/scripts/mixar/modules/lampway_tools/inspect/__init__.py), [schema](../../src/scripts/mixar/modules/lampway_tools/inspect/schema.py) | Present for primary lists; scene projection and optional camera/light fields are disclosed in the scene row below. |
| Strings max 200 with total/full hint; full restores strings; lists limit 50 | Envelope truncate; orchestrator paging; envelope/binary tests | Present for ordinary data; help intentionally exempt from truncation. |
| Precomputed totals, count/total for paged lists; definitive empty arrays | Orchestrator, view engines, schemas and tests | Present; deep uses uncapped caller-owned `scan_bmesh`, preserves per-kind totals and pages only at the wrapper boundary. |
| Every refusal `isError`, code, error, help; additionalProperties false; unknown args before Blender | Envelope argument_error/result, tool input schemas, envelope tests | Present. Render/native refusal propagation has targeted tests. |
| Read-only idempotence, unhide idempotence, no prompt | Inspect/view, canon door and API routing | Real GUI selection/active and all twelve inspect history checks are green; one unhide undo restores hidden state. No prompt or automatic confirmation path. |
| No-arg live data plus tool/description; inspect first | Inspect dashboard, view runtime, docs handler, guide generation | Present. |
| Help last; call templates retain fixed args and placeholders, quote spaces | Envelope and inspect template | Budget retry preserves supplied arguments and larger-budget placeholder. Successful metric paths no longer return the former owner-dependency skips. |
| Per-view/action help returns arguments, defaults, fields and refusals | Inspect run(help), api_view(help), docs handler | Inspect field reference now derives from view schema using `reference_fields`; tests added. T2 help now includes action-specific output-field reference; targeted checks recorded in completion tests; acceptance implemented and checked, with exact-head aggregate receipt external. |
| Image jail, PNG validation, max_bytes 750,000 default, image after text, delete temp | Envelope `_image`, view capture; race/invalid PNG/cap tests | Present on descriptor-capable POSIX. Other platforms explicitly refuse; native GUI images/masks are green, while actual server transfer has separate bounded PNG/race tests. |
| Existing tools stay legacy; in-app stays JSON | MCP new names; server dispatcher tests | Present. |

## C2: launcher guide

| Requirement | Code and tests | Review |
|---|---|---|
| Initialize instructions from generated server registry; first step inspect | [generator](../../server/lampway_server/agent_files/generate.py), MCP initialize | Present. |
| Client uses live initialize result; generated static fallback while app closed | [stdio server](../../src/scripts/mixar/modules/mcp_bridge/core/stdio_server.py), [generated guide](../../src/scripts/mixar/modules/mcp_bridge/core/generated_guide.py) | Closed: standalone namespace fix allows pure brand import; actual SDK empty-profile and saved-inspect-profile initialization return generated fallback, resource and prompt. Receipt `<evidence>/c2-stdio-closed-receipt.txt`. |
| Every tool-like identifier exists in tools/list; remove eight obsolete names | Server/client guide tests cited in migration report | Actual SDK closed-app tests now verify every instruction identifier is in tools/list, ≤2048 UTF-8 bytes, and inspect first when saved inspector catalog exists; absent inspector is omitted. Targeted C2/installation/startup run totals 26 passed. |

## T1: input, engine and outputs

| Requirement | Code and tests | Review |
|---|---|---|
| Agent `lampway_inspect`; API inspect; appended DEFS; one api.call script; no egress/spend | [Def](../../server/lampway_server/agent/inspect_tools.py), [API](../../src/scripts/mixar/modules/lampway_tools/api_inspect.py), MCP/schema/registration tests | Present. |
| View enum/default home; name/names/collection/match/fields semantics | Input schema and orchestrator `_objects`, `_named` | Present; names cap 200; recursive collection all_objects; selection fallback; casefold substring. |
| limit 1..1000 default 50; offset≥0; full/evaluated/deep booleans | Input schema; server parity test | Present. |
| methods shells/sharp/uv_islands/materials; angle 1..179 default 40 | Schema, [parts](../../src/scripts/mixar/modules/lampway_tools/inspect/parts.py) | Present. |
| texture_size power-of-two 256..16384 default 2048; tolerance 0..1 default .005; budget 100..60000 default 2000 | Schema | Present. |
| Invalid values bad_argument with range; unknown args/fields structured refusal | Validators, orchestrator and envelope tests | Present for schema-bound arguments; view-specific required-name error has next-step template. |
| Compact MCP envelope; generated per-view JSON schemas accessible through schema | Schema generator, [schema tests](../../tests/lampway_tools/test_inspect_schema.py), docs/schemas/inspect | Present; per-view types are tested but runtime MCP validates compact envelope only. |
| World space/Z up/metres after unit scale; prescribed rounding | [objects](../../src/scripts/mixar/modules/lampway_tools/inspect/objects.py), mesh/UV/parts/relations | Relations now use unrounded world bounds in `relations.measure`, closing tiny-gap classification loss. Object size now uses unrounded `world_bounds` before final rounding; targeted precision regression passes (1 test). |
| Home file/unsaved/units/counts/tris_total/selection/active/warnings, O(objects) dashboard | [home](../../src/scripts/mixar/modules/lampway_tools/inspect/home.py) | Triangle count is now exactly `len(mesh.loops) - 2*len(mesh.polygons)` using O(1) RNA lengths; valid Blender polygons partition loops and contain at least three loops. A RED fixture forbids polygon iteration/bulk reads; GREEN 1 passed in 0.21s. Named chess acceptance measured 478ms RED then 109ms GREEN; final serial receipt `<evidence>/tests/named-final-precommit/ABeautifulGame.json` measured 80.01ms (<200ms), 49 objects and 1,498,828 triangles, no failures. Object traversal now meets O(objects), with no per-polygon read. |
| Scene collection tree; camera lens/sensor/clip; light type/power/color/size; world, frames/render | home.scene_data and generic paging | All specified fields are computed and schema/help-disclosed. Per C1 default 3–4-column rule, scene rows return four fields; optional camera clip_end and light color/size are returned with named fields or `fields=["*"]`. This is the disclosed default projection, not a claim that default rows contain every optional column. |
| Objects default name/type/tris/parent; all named optional fields | objects.row, schema projection | Present; computes every optional field before projection and before pagination, creating unmeasured scalability cost. |
| Object detail all object fields + typed modifiers/constraints/materials/collections/children/layer count/top/canon | objects.detail, orchestrator layer summary | Present. |
| Mesh counts, manifold, shells; reuse DS._shells/_open_loops/_descriptor; holes sorted rim descending | [mesh](../../src/scripts/mixar/modules/lampway_tools/inspect/mesh.py), measurement/binary tests | Present for counts/shells/open-loop facts, transformed rim/centroid. |
| Cheap defects degenerate/isolated_tri/flipped_shells | Mesh | Present: cheap shell orientation uses caller-owned world-metre bmesh through `workflows.shell_orientation_bmesh`; new metric-bmesh binary tests. |
| Deep intersections/thin_regions on evaluated world-metre mesh | Mesh and orchestrator | Present: `DS.scan_bmesh` accepts the evaluated/transformed world-metre bmesh, with budget; new deep/scaled/evaluated metric-bmesh tests. |
| Deep list totals/truncation and no missing measurements disguised as zero | Mesh DS.run adapter | Closed in source: scan_bmesh supplies uncapped candidates; intersections_total and thin_regions_total retain exact per-kind counts before wrapper paging. |
| UV layers, islands_total/utilization/overlap/flipped/seam/density/tiles/crossing/islands; largest first | [UV](../../src/scripts/mixar/modules/lampway_tools/inspect/uv.py), binary metric tests | Present for covered metrics. Shared overlap engine now counts triangles within each island; new binary self-overlap tests. Final serial helmet UV 1,648.36ms cold and 17.60–20.25ms cached; mesh 251.38ms cold and 23.12–32.11ms cached, all under required thresholds. Raw negative-V tile991 has utilization 0 for tile1001; independent canonical oracle confirms this and actual overlap .999. |
| No UV → layers [] and unwrap next step | UV and orchestrator | Present; original real-binary Suzanne case is green: source no-UV layers[]/unwrap help, then new existing-tool unwrap output has UV layers/islands, with source unchanged. |
| Parts read segmentation labels/merge only; material groups; fields/bounds/centroid | Parts | Present; no split/hide. |
| Layers existing LM inspect, no creation; no paint→[] plus init help | [layers](../../src/scripts/mixar/modules/lampway_tools/inspect/layers.py) | Present. |
| Relations nearest pairs, ≤200 input objects; AABB gap/classification/ratios/overlap/alignment | [relations](../../src/scripts/mixar/modules/lampway_tools/inspect/relations.py), [pure tests](../../tests/lampway_tools/test_inspect_relations.py), orchestrator | Present for pure tested AABBs and real cube/plane; unrounded world bounds fix is green. Both pair orientations are not emitted; classification follows scene/name order. |
| Deep relations use BVH surface distance and closed-mesh ray parity | Orchestrator | Present in source: new shared `features/surface_relations.py` supplies BVH distance/containment with deadlines; real synthetic relation binary tests added. Real synthetic tests include closed cube parity, both relation orientations, surface crossings, edge-interior minima, metres and evaluated modifiers; synthetic acceptance is green; exact-head aggregate receipt is external. |
| File path age/backups/datablocks/missing/libraries/usage, vendored Lab main bodies, safe paths | [filemeta](../../src/scripts/mixar/modules/lampway_tools/inspect/filemeta.py), inspect/_vendor | Present, pinned vendor with preserved attribution/REUSE. |
| L2 cache key name/data/evaluated/hash; 64-entry memory LRU; scene edits invalidate | [cache](../../src/scripts/mixar/modules/lampway_tools/inspect/cache.py), binary cube-face invalidation | Present for geometry/UV/material indices/seam/world/scale/options; no files. Full edit-kind freshness not proven by one face-deletion test. |
| Budget skipped rows object/section/reason + retry with greater budget; 2M tris/100ms ≤200ms | Budget/orchestrator; schema tests | Required 2M-triangle 100ms case measured cold 0.91ms and repeat-refusal 0.16ms (<200ms) after conservative work admission before hashing/BMesh. Cooperative checks added through engines/hash; deadline retry now preserves supplied args. Native evaluation/BVH calls are still indivisible, so this is the named requirement receipt, not a universal hard-deadline guarantee. |
| Session scene binding; raw reads OBSERVE; render read-only exemption, evaluated render refusal | API/canon door/executor routing; contract tests | Present by source and targeted routing tests. |
| App closed/signed out existing launcher refusal; not_found/wrong_type next steps | MCP connection handling, orchestrator | Present. Live signed-out launcher receipt not rerun. |
| No scene change/files/undo; cache memory only | Inspect engines; binary test | Binary state checks plus real GUI marker-history tests cover all twelve views: one undo after each view returns marker 1, then marker 0, with unchanged selection. A planted extra undo fails that test. Full scene fingerprint beyond specified history/state is not claimed. |
| Real cube open face 4-edge hole; closed cube []/0; two shells; raw imported GLB; plane on-top | Binary and pure tests | Open-face/closed cube tests present; named helmet/chess tests now import real GLB and assert successful inspection. Bunny receipt `<evidence>/tests/named-acceptance-after-rim/StanfordBunny.json` matches five (edge count, rim length) pairs one-for-one: (22,.0302), (39,.0598), (40,.0636), (42,.0722), (80,.1137). Original real-binary cases now green: 3 passed in 3.44s in `test_inspect_original_binary_cases.py`. TwinCubes has two closed six-face shells; no-UV Suzanne inspects empty, existing unwrap creates a new nonempty-UV object while source stays unchanged; actual cube/plane API reports on_top_of gap 0. |
| Every view TOON/structured fixture equivalence | Envelope tests + binary JSON/schema tests | Final named fixture validates all eleven requested views. Independent actual mcp_envelope.result check on native home plus eleven views: 12 passed, text decode equals structuredContent, compact outputSchema valid, isError false; receipt `<evidence>/c1-all-view-native-envelope-receipt.txt`. |
| Named assets/performance/screenshots | External pinned native acceptance receipts and tests | Pinned assets and native GUI object screenshots/TOON/JSON captured for all three named assets; source receipt `<evidence>/t2-named/`. Final named serial run: 3 passed in 7.97s, no failures; precise timings below. Side-by-side native object/reply HTML `<evidence>/t2-named/inspection-audit.html` is completed and visually checked by coordinator. |

## T2: view and image actions

| Requirement | Code and tests | Review |
|---|---|---|
| Name/API/Def, action enum; no-arg live editors/camera/last capture | [Def](../../server/lampway_server/agent/view_tools.py), [API](../../src/scripts/mixar/modules/lampway_tools/api_view.py), [runtime](../../src/scripts/mixar/modules/lampway_tools/view/runtime.py) | Present. |
| object xor data; unhide false; area VIEW_3D or AreaUIType/WINDOW; shot true | Def/API/runtime | Present for visible types; schema area is free string rather than vendored enum; nonexistent type returns no_area. |
| max_bytes 50k..900k/default750k downscale; preset current/thumbnail; out relative unique still names | Def/API, [helpers](../../src/scripts/mixar/modules/lampway_tools/view/__init__.py), view contract tests | Present. |
| Focus operator on bound scene/tab VIEW_3D; restore selection/active; return bounds/image | Runtime.focus; [binary test](../../tests/lampway_tools/test_view_binary.py), mocks | Real GUI focus with shot=true produced a bounded PNG, moved view center to (3,4,5) and restored Camera selection/active. Edit-mode behavior beyond specified fixture is not claimed. |
| Hidden refusal before mutation; explicit unhide one named undo, idempotent | Runtime.focus, executor suppress auto-undo; mock test | Real GUI one undo restored Cube hidden state and retained Camera selection; repeated inspect history checks also passed. |
| One pixel opt-in for screenshot/focus image; observe native secret masking/capture_busy; crop area | Runtime.pixel_gate/capture, helper crop; mock/PNG tests | Real native GUI captures VIEW_3D, IMAGE_EDITOR and ShaderNodeTree all ≤50,000 bytes; synthetic password widget center measured black [0,0,0]. Unmasked planted regression fails. |
| Render asynchronous coordinator/scene_render background; resize/render guards; no main-thread render | [render adapter](../../src/scripts/mixar/modules/lampway_tools/view/rendering.py), scene_render jobs; mocked adapter tests | Real GUI adapter completed two asynchronous thumbnail stills and restored engine/resolution/filepath; busy second start refused render_in_progress. Subsequent default-current GUI run is green (1 passed in 33.25s): omitted preset via actual api.call produces current.png 320×240 and preserves full relevant settings. Receipt `<evidence>/t2-current-green.txt`; retained native result `<evidence>/t2-current-final/project/receipt.json` contains current PNG 320×240/61,261 bytes, CYCLES CPU one sample and unchanged formats/frame/full relevant settings. |
| render_still job/help; finished job relative path; no overwrite twice | Render adapter, reserve-output tests | Real GUI completed still.png and still-2.png as 256×256 PNGs (37,389 bytes each). Existing job tool's argument is job, so help uses job rather than proposal's illustrative id. |
| Hidden/no_area/render_in_progress/path_outside_project refusals and next step | Runtime/API/tests | Present for tested cases; the original isolated GUI receipt verifies native render-busy refusal through the existing coordinator. Successor rerun remains coordinator-owned. |
| Text+image content, image dimensions/bytes, action/object/area/bounds/unhidden/job | Runtime/render/envelope | Present where applicable; render_still intentionally starts a job and carries no immediate image. |
| No spend/egress; settings restored; idempotent unhide | Source integrations | No new egress/spend; GUI test confirms engine/resolution/filepath restoration after both thumbnails. |

## T3: offline documentation

| Requirement | Code and tests | Review |
|---|---|---|
| Server specs tool, no app/runtime network; views home/get/search/help | Server specs + [index](../../server/lampway_server/blender_docs/index.py), [tests](../../server/tests/test_blender_docs.py) | Present; targeted offline sockets-prohibited prior receipt. |
| identifier/wildcard, query, scope api default/manual, limit1..50/default10, context0..10, full | Specs/input validation/index | Present in tested cases. |
| Home versions/index sizes/examples; get identifier/kind/signature/doc/children; search rank/title/snippet/count/total | Index/spec handler/tests | Present; namespace get children have top-level count/total for paging. |
| Unknown ID definitive []/0 + search help; Object.location type/description | Tests/full corpus | Present. |
| Manual bevel modifier first; search-to-get scoped next step | Tests/index | Present. |
| Vendored Lab search/parser/lookup, GPL attribution and REUSE | index/vendor, manifest, REUSE/notice | Present, Lab v1.0.3 commit `2cea8d566dde07fbac28a61d698909d69724e853`. |
| API generated by own binary/pinned generator; matching 5.2 manual release tag; under server data | Manifest and [T3 receipt](mcp-wrapper-t3.md) | API source pin `fbe6228777e7d9afefcd61a413844e790ae75db7` is official Blender `refs/tags/v5.2.0`, independently confirmed by coordinator `git ls-remote`; `build_linux.sh` reads `HEAD:upstream`. This is distinct from the manual source. Manual immutable release-branch commit `4a3be8f9ed3b66b24913e0a0d491d3429a70ea08`. The captain subsequently made repository runtime/source pin authoritative, superseding a separate manual-tag requirement; manual revision remains explicit, without inventing a tag. |
| Data version equals bpy.app.version_string | Manifest/tests | Present: manifest `blender_version_string` is 0.1.0, matching the branded binary; `core_version` is separately 5.2.0. Branded runtime identity must not be mistaken for core documentation identity. |
| Bundled authoritative corpus/licences/hash manifest; no first-use download | Manifest/corpus/wheel receipts | Present; source manifest now records three privacy-sanitized RST replacements with upstream/packaged hashes and NOTICE provenance; 27 docs tests pass and docs corpus gate has 0 findings; provenance is derived/checkable from HEAD:upstream and served with separate source/manual immutable commit backlinks. Official version-derived docs URLs returned 403 and are explicitly marked access-unverified, not missing-version. Current wheel rebuild after replacements/provenance: 6,983,071 bytes, SHA256 `34a60fe61c4de63a5c78208fc2ad91c405104f9f2710f3e470ed7c48736b3605`; ZIP verification passes all 4,327 current RST hashes, three byte-identical licence texts and source/manual provenance; extracted-wheel home/API/manual lookup passed with sockets/subprocesses prohibited. Receipt `<evidence>/tests/resumed-wheel-verification.json`. |
| API GPL-2.0-or-later/manual CC-BY-SA-4.0 licence texts/annotations | REUSE, corpus notice and licence texts | Present; whole-repository REUSE baseline not claimed green. |

## Findings and completion follow-up

1. Relation rounding is closed in source: `relations.measure` computes on unrounded
   transformed bounds. `objects.row` now derives size from unrounded world bounds; precision regression
   passes (1 test, `<evidence>/tests/object-size-green.log`).
2. Deep truncation is closed in source: mesh uses uncapped caller-owned scan_bmesh
   and preserves exact per-kind totals. Final aggregate tests must use this tree.
3. Inspection help fields now derive from view schemas. T2 output-field reference
   now documents every action; targeted regression added by coordinator.
4. Budget retries now preserve supplied arguments. The required 2M/100ms receipt
   is green via admission before expensive work; native modifier/BVH calls remain
   indivisible. No general hard deadline is claimed from a conservative refusal.
5. Real GUI marker-history and unhide undo tests close the missing history evidence;
   named tests import actual GLBs. Final named helmet run and original synthetic cases are now green;
   final exact-tree aggregate and packaging checks remain coordinator-owned.
6. Home per-polygon work is closed: exact valid-mesh triangle identity uses two
   O(1) RNA lengths. The forbidden-iteration/bulk-read fixture has RED and GREEN
   receipts (`<evidence>/tests/home-constant-{red,green}.log`). Named chess home
   final serial acceptance is 80.01ms with 49 objects / 1,498,828 triangles.
7. The initial C2 SDK failure was a required integration gap, not excluded audit
   startup: config.brand triggered bpy-dependent config initialization before
   fallback instructions. The narrow standalone namespace fix is now GREEN.
   Receipt `<evidence>/c2-stdio-closed-receipt.txt`: 17 guide/SDK/connector/catalog
   tests plus 9 installation/runtime-startup tests pass. Both empty and saved
   inspector profiles initialize; generated instructions match resource/prompt,
   list only offered tools and keep inspect first when offered.

The initial report's SDK-child exclusion was withdrawn because it blocked C2.
This is a completed C2 fix. The successor inherits main's isolated launcher and
operation leases; their audit implementation remains main-owned, while required
MCP integration with those interfaces must be verified on the successor. Historical RED is retained as evidence,
not represented as a current failure.

## Successor reconciliation

The [migration report](mcp-wrapper-migration.md#reconciliation-with-main) records
ownership and source boundaries for main's F1/F2/F3/F9/F20 fixes. The complete
matrix above is retained; none of its requirements is replaced by a main audit
finding or a dependency skip. Inspect/view/docs engine source has no diff from
`bc0a721`; the source pin remains the same official Blender 5.2 commit.

C0 retains full official conformance plus main's encoder regression tests. C1/T1/T2
now reach Blender through main's operation lease caller, preserving scoped
refusal/envelope, read-only render admission and undo behavior. C2 retains one
registry-generated guide and closed-app fallback; the coordinator owns canonical
GUIDE regeneration and merged identifier validation. T3 remains server-side and
offline, with authoritative source/manual provenance unchanged. Main's F20 log,
batch-form registry, canon translation behavior, segmentation safeguards, UV
warnings/paging, UI labels and sandbox temp jail are retained rather than
reimplemented.

All original component closures remain historical evidence. Successor exact-head
server/client, isolated native/GUI/named-asset and package verification receipts
are required before the coordinator claims current-head acceptance; they are
retained externally. This review does not promote prior receipts to successor
reruns or claim an aggregate result that has not arrived.

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

## Acceptance asset identity

The verified source names DamagedHelmet, Stanford bunny and ABeautifulGame; its
method appendix identifies Khronos glTF Sample Assets and Stanford bunny. It
contains no immutable model revision/file hash, Stanford bunny variant, exact
import transforms/normalization, or recipe/hash for the “41 MB chess scene”. The
names therefore do not establish the original audit's exact assets.

The coordinator resolved a reproducible fixture selection on 2026-10-07:

| Input | Immutable source / member | Bytes | SHA256 |
|---|---|---|---|
| DamagedHelmet | [Khronos binary GLB](https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/edc7c9e67c639d230715049ee31f9a96a6babbbe/Models/DamagedHelmet/glTF-Binary/DamagedHelmet.glb) | 3,773,916 | `a1e3b04de97b11de564ce6e53b95f02954a297f0008183ac63a4f5974f6b32d8` |
| ABeautifulGame | [Khronos binary GLB](https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/edc7c9e67c639d230715049ee31f9a96a6babbbe/Models/ABeautifulGame/glTF-Binary/ABeautifulGame.glb) | 42,977,928 | `bd7133b4b322aae97c589b8839dae8155ad2546acb35ae32a127e722a959d007` |
| Stanford zippered bunny | [official archive](https://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz), member `bunny/reconstruction/bun_zipper.ply` | 3,033,195 extracted | `b1acc63bece78444aa2e15bdcc72371a201279b98c6f5d4b74c993d02f0566fe` |

Both GLBs are pinned at Khronos commit
`edc7c9e67c639d230715049ee31f9a96a6babbbe`. The Stanford archive is pinned
by SHA256 `a5720bd96d158df403d153381b8411a727a1d73cff2f33dc9b212d6f75455b84`
(4,894,286 bytes). Local download receipts are retained outside the repository.
These establish the selected acceptance input bytes, not the original audit's
undocumented scene recipe. Final receipts still need import options/transforms,
licence acknowledgement, scene recipe and binary/native pin. Assets are local
acceptance fixtures and are not bundled with the product.

Completed live receipts: 2M triangles/100ms conservative refusal ≤200ms;
native masked editor/focus PNGs; two completed thumbnail stills with settings
restoration; one unhide GUI undo; all twelve inspect views preserve undo history;
closed-app C2 SDK initialization and fallback (26 targeted tests); named assets
serial run (3 passed in 7.97s) and all twelve native view C1 envelopes (12 passed).

Final serial named receipt `<evidence>/tests/named-final-precommit/` records:

| Asset / measurement | Cold | Cached | Required |
|---|---|---|---|
| ABeautifulGame home | 80.01ms | n/a | <200ms |
| DamagedHelmet mesh | 251.38ms | 23.12–32.11ms (three calls) | <2s cold / <50ms cached |
| DamagedHelmet UV | 1,648.36ms | 17.60–20.25ms (three calls) | <2s cold / <50ms cached |
| Stanford bunny mesh | 699.28ms | n/a | five holes match defect scan one-for-one |

Helmet UVs are imported raw in negative-V tile991, so tile1001 utilization 0 is
correct; the canonical independent oracle confirms overlap .999. Prior provisional
metric receipts are superseded by this final serial run. `<evidence>/t2-named/`
contains native GUI PNG/TOON/JSON for each named object. `<evidence>` denotes
private local evidence retained outside this published report.

Original two-shell/Suzanne unwrap sequence/plane fixture is green (3 passed in
3.44s). Default current-render settings fixture is green (1 passed in 33.25s),
producing 320×240 current.png through omitted-preset api.call while preserving
full relevant settings. Side-by-side named presentation is completed at
`<evidence>/t2-named/inspection-audit.html`. Original-checkpoint functional component acceptance is
complete; its package build identity is recorded above. Successor verification
is distinguished in the reconciliation section. Package integrity/offline checks passed; final exact-head aggregate tests and publication
gates are coordinator verification, with external receipts to avoid a report
embedding the hash of the commit containing itself. The captain's
clarified documentation policy follows HEAD:upstream with separate manual source
provenance; there is no independent manual-tag approval blocker. Official docs
backlink requests returned 403, so availability is explicitly unverified; pinned
offline lookup remains functional.
