<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Roadmap

The plan is a set of **waves**; each wave ends in a pushed `lp/*` branch, a report in [`docs/reports/`](reports) and a build path. Every wave is written test-first (the commit body carries the RED line), and an integrator merges the branches `--no-ff`, runs the full suites and the pre-publish gate, and only then moves `main`.

Status words: **done** = built and tested on the integration branch; **in progress** = a lane is working on it now; **planned** = specified, not started; **waiting** = blocked on a decision only the maintainer can make. "Done" does not mean "run live": the "evidence" column and each doc's status box say what ran against a real service.

The complete per-contract coverage (about 230 contracts, each classified built, partial, in a lane, folded, waiting or owed) is kept by the maintainers in a local audit; this page is the public summary.

## Waves

| Wave | What | State | Report | Evidence |
|---|---|---|---|---|
| 0 | Correctness defects in shipped tools: the identity gate that always passed, a rigid-stretch check that could not fail, the 7.3 cm cuirass seam tear the acceptance gate now catches, `auto_rig` mutating its source, flipped open shells and a UV-blind hash, free regen actions, `detail_normals` with no caller | done | [wave0](reports/wave0.md) | each fix observed RED on the shipped code first; mutants run |
| 1 | Prompt library, job-service registry, asset lineage, one experiment ledger, workflow graph | done | [wave1](reports/wave1.md), [prompts](reports/prompts.md) | real-binary tests |
| 2 | The armour pipeline to the engine set (plates, seeds, audits, UV scoring, defect scan, silhouette compare, placement, openings, parts critique, palette fit, studio texture flow, bake, PBR pack, the 15-step sequencer); remainder: model compare, view verify, scanner amendments, secret rejection, magic-byte uploads | done | [wave2](reports/wave2.md) | live on shelf pieces for palette fit, parts critique, bake and the sequencer; no credit spent |
| 3 | Fit, bind and export to the engine: body package, weight audit and cleanup, robust weight transfer, clearance, bind, validate, export, skeleton and engine import checks | done | [wave3](reports/wave3.md) | live check on the real MetaHuman body for the body package and weight audit; **synthetic pieces** otherwise |
| 3b | The herdr cockpit: isolated launcher, durable session registry, one idempotent reconcile, activity observers, the Blender panel; the Codex app-server provider; agent ops | done (cockpit window and WezTerm add-on: see lanes) | [wave3](reports/wave3.md) | crash survival exercised against the real herdr binary |
| 4 | Animation: reference render, clip plan, two-view motion fit, check, loop export, retarget, video presets and gates; clip classify, URL ingest, fal gateway | done | [wave4](reports/wave4.md) | **synthetic** clips and figures only |
| 5 | Upstream parity: retopology with AutoRemesher, UV rectify and layout, scene cleanup, batch export, camera shots, 12 procedural materials, layered material, material bake export, image segmentation; Studio REST drivers (Meshy, Hyper3D, Hi3D, Tripo); MCP inventory; agent files and skills; the decision judge | done | [wave5](reports/wave5.md) | real-binary tests; REST drivers on fakes |
| 5 (cloud) | Job receipts, egress consent, the compute wrapper and Blender offload | done | [wave5](reports/wave5.md), [compute-spend](reports/compute-spend.md) | Boat live within the caps; the rest on fakes |
| 5b | The Asset Vault | **partial**: the library modules are done; wiring and the rest are in progress | [asset vault](asset-vault.md) | library tests; not wired into the server |
| 6 | Cloth and garment simulation, characters, modular characters, secondary rigs, face-rig validation, cinematic planning, playblast, level blockout, traversal checks, splats, print prep, LOD chains, GLB optimisation, vehicle rigs, profile revolve, material and motion experiments, text-to-motion | **waiting** on the maintainer's scope decision | | |

## Lanes in progress

Three implementer lanes work beside the integrator, each on its own branch and its own copy of the application binary.

| Lane | Branch | Work |
|---|---|---|
| vault-ops | `lp/vault-ops` | Asset Vault: thumbnails and renders (`asset_render`), video as a kind (`asset_video`), embedding-model selection and the bundled models (`asset_embed_models`), the rest of the shelf import (`asset_seed_captain`), the procedural armour materials (`asset_seed_procedural`), selective CC0 import (`asset_seed_cc0`), the gates (`asset_gates`) |
| vault-ui | `lp/vault-ui` | Asset Vault: place into the scene (`asset_place`), the MCP and agent tool family (`lampway_vault_*`), the dockable editor and pop-out (`asset_ui_editor`), the views (`asset_ui_views`), and report cards |
| facelift | `lp/facelift` | The client facelift: themes Night and Paper from one token file, splash and first run with every route off, window chrome, agent chat, honest Parallel Agents cards, Providers and Studios, tool panels as a lit path, generation, the cockpit window, model compare, the privacy face with the wire colour, the spend card, icons, a visual harness, and the Lampway WezTerm add-on |

The facelift keeps the same information with better hierarchy and stronger at-a-glance cues. The wire indicator uses a dedicated colour; the cockpit's first terminal surface is a themed chromeless browser window, with the optional WezTerm add-on (a pinned stable release, an on-demand checksum-verified download through egress consent, current platform only) alongside it ([cockpit](cockpit.md)).

## Decisions only the maintainer can make

These block the rows named. They are recorded as `needs_decision` stubs in the code, not guessed.

1. **Fit**: the gasket collar's flange length; the boots scale anchor; whether a fitted example is still an input or only the native body; the fit-state route; the material role per part; the pose degrees of freedom for the non-chest pieces.
2. **Body tracking**: MetaHuman Animator needs Windows; choose a Windows host, a paid tracking service, or a local exception (SAM 3D Body reads about 80 % on the leg-identity gate against an 85 % threshold).
3. **GPU provider** for the serverless adapters; no paid probe runs until one is named. Modal and RunPod are written against fake transports.
4. **Installs**: libigl and robust-laplacian in the science Python (approved and used for weight transfer), an AutoRemesher build or download.
5. **Providers in scope**: a text-to-motion host, further studios, Meshy and Hi3D logins for the live tests.
6. **Scope** of wave 6.
7. **Thresholds** only the maintainer owns: thin-wall, the silhouette IoU floor, clearance targets, the part budget table, the loop limit (0.5 or 1 degree, measured on one rig so far).

## Open items that are not decisions

Known defects and owed work in the code on the integration branch, stated here so nobody has to rediscover them:

- The Asset Vault library is not wired into the server (see [asset vault](asset-vault.md)), needs Python 3.14 (`uuid.uuid7`) and imports numpy without declaring it.
- 18 of the client's 21 generation job types have no backend; only `image_gen`, `video_gen` and `video_upscale` are served.
- A `submission_unknown` job can be acknowledged or linked only through the receipt API; no route or button calls it ([spend](spend.md)).
- The engine editor leg (AnimSequence publish, engine import validation, UE-frame bind comparison) is not built.
- No studio generation (Tripo, Meshy, Hi3D, Hyper3D, Higgsfield) has run live; every request shape for the REST studios, fal, Modal and RunPod is unverified.
- Windows and macOS are unbuilt.

## How to follow along

Each wave's report in [`docs/reports/`](reports) names what was built, how it was tested (RED first, mutants, live runs and their costs) and what was left honestly open.
