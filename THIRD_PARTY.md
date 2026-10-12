<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Third-party software, models and fonts

This is the inventory of everything Lampway builds on, vendors, adapts, fetches or depends on, with its licence and where it is in the tree. [`NOTICE.md`](NOTICE.md) carries the upstream attribution and the full notices; per-file licensing is in SPDX headers and [`REUSE.toml`](REUSE.toml); licence texts are in [`LICENSES/`](LICENSES/) (`GPL-3.0-or-later`, `GPL-2.0-or-later`, `MIT`, `Apache-2.0`, `LicenseRef-ITF-FFL`).

Where a licence below was taken from a project's page or model card rather than from the licence file of the exact files distributed, it says so: re-read the licence of the exact release before you redistribute anything.

## 1. Base: the client Lampway is a fork of

| Component | Licence | Where | Notes |
|---|---|---|---|
| Mixar desktop client (<https://github.com/Mixar-AI/mixar-app>), Adeveda Enterprises Private Limited | GPL-3.0-or-later | most of `src/scripts/mixar/` and `src/source/` | upstream copyright notices are kept as the GPL requires. Lampway is not affiliated with, endorsed by or supported by Mixar, Mixar Inc or Adeveda. The Mixar name and brand assets are not shipped; see [`TRADEMARKS.md`](TRADEMARKS.md) |
| Blender 5.2 (blender.org) | GPL-2.0-or-later | the `upstream/` git submodule (pinned `v5.2.0`), overlaid at build time | Blender-derived files keep their own notices; the precompiled libraries (`lib/linux_x64`) carry their own licences inside upstream |
| Linux build, run and desktop-entry scripts; the X11 Agent Bubble backend | GPL-2.0-or-later (same tree) | `scripts/unix/`, the ghost X11 backend | adapted from commits of a community Linux fork of the Mixar client (credited in the commit messages), renamed to Lampway names. [UNVERIFIED]: that fork's own licence text was not separately read |

## 2. Adapted into the tree

| Component | Licence | Where | Notes |
|---|---|---|---|
| **ucupaint** (ucupumar) | GPL-3.0-or-later | `src/scripts/mixar/modules/paint/core/lib/lib.blend`, `paint/core/io/connections/`, `paint/core/layer/create_channels.py`, parts of `paint/ui/` | the layered-paint module's design lineage; substantially modified |
| **Mr. Mak Workspace** (character-sheet pipeline prompts) | MIT, Copyright (c) 2026 Mr. Mak Workspace contributors | `server/lampway_server/prompts/builtin/` (`sheet-*`, `part-*`, `turntable-360-locked`) | adapted from upstream commit `1e0c7c3`, `.agents/skills/character-sheet-pipeline/prompts/`; each template names its source file in its `provenance`. The licence text is `LICENSES/MIT.txt`. **Nothing is copied from the arena-viewer header**: its licence lineage is uncleared |
| **img2threejs pipeline** (vendored in the Mr. Mak Workspace), the `forge` clip-feature code | Apache-2.0, Copyright img2threejs contributors | `src/scripts/mixar/modules/lampway_tools/pipeline/clip_features.py` and `tests/lampway_tools/test_wave4b_clip_features.py` | translations of `forge/stage5_rig/clip_features.py` and its test; each file carries its upstream notice and a statement that it was modified. The licence text is `LICENSES/Apache-2.0.txt`. The default thresholds come from one subject on one rig (11 clips) |
| **UE5 Manny reference skeleton: measured facts** (Epic Games' Unreal Engine 5 mannequin) | facts only: no Epic asset, mesh, texture or code is included | `src/scripts/mixar/modules/lampway_tools/rig_convert/recipes/anim-profile-manny.json` | bone names, hierarchy and reference (rest) joint transforms, measured from the UE5 Manny reference skeleton in Unreal Engine 5.8 through the TITAN project, and ported with the O36 animation canon (lp/orphans). Kept in the repository by the captain's ruling of 2026-10-06; the provenance is restated in [`rig_convert/recipes/README.md`](src/scripts/mixar/modules/lampway_tools/rig_convert/recipes/README.md) |
| **TOON specification encode fixtures** (toon-format/spec) | MIT, Copyright (c) 2025-PRESENT Johann Schopplich | `server/tests/fixtures/toon/encode/*.json` | copied unchanged from `tests/fixtures/encode/` at commit `eee00a23` (spec 4.3); test data only, never shipped in the app. The licence text is `LICENSES/MIT.txt` |
| Other ideas from the same workspace (interior difference, the bounded retry ladder, intake tests, manifest verification, secret-prefix and magic-byte rules) | not copied | `pipeline/interior_diff.py`, `retry_policy.py`, `view_verify.py` and the ledger and receipt validators | the code is new; the headers say "the idea follows ..." |

## 3. Built or fetched by you, not distributed

| Component | Licence | How it enters | Notes |
|---|---|---|---|
| **AutoRemesher** (Jeremy Hu / Dust3D Project) | MIT, Copyright (c) 2026 Dust3D Project | `native/quadremesh/build.sh` fetches a pinned commit when *you* build the executable | `native/quadremesh/` is Lampway's own Qt-free command line around the quad-remeshing core. The sources are not in this repository. Anyone who redistributes a built executable must carry the MIT notice and the notices of its bundled TBB (Apache-2.0), Eigen (MPL-2.0), meshoptimizer (MIT) and isotropicremesher sources. Lampway runs it as a separate process and never downloads it |
| **libigl**, **robust_laplacian**, **scipy** | MPL-2.0, MIT, BSD-3-Clause (as published; [UNVERIFIED] against the exact wheels) | installed by you into the science Python (`LAMPWAY_PYTHON_SCIENCE`) | the robust weight-transfer engine; nothing is vendored |
| **CLIP ViT-B/32** (image tower), **bge-small-en-v1.5** (text) | MIT for both, from the model cards ([UNVERIFIED] for the exact files) | the Asset Vault fetches ONNX exports on your click, through the declared `model_download` route, and writes a `PROVENANCE.json` (URL, sha256, bytes) | **no weights are committed to this repository.** Sources: <https://github.com/openai/CLIP> and <https://huggingface.co/BAAI/bge-small-en-v1.5>. The ONNX export locations in `library/localmodels.py` were not downloaded and no checksum is pinned yet. Until the weights are fetched and `onnxruntime` is installed, the Vault uses deterministic descriptors instead |
| **WezTerm** (Wez Furlong) | MIT (the `LICENSE.md` text; GitHub's licence API reports `NOASSERTION`) | **planned**: an optional add-on, a pinned stable release (`20240203-110809-5046fc22`) downloaded on demand for the current platform through egress consent and verified against a SHA-256 pinned in Lampway's source | **not in the tree and never bundled.** The installed copy carries WezTerm's licence beside it. See [`docs/cockpit.md`](docs/cockpit.md) |
| **herdr**, the **Boat** CLI, `codex`, `claude`, `opencode`, `yt-dlp`, `ffmpeg` | their own licences and terms | programs you install and log in to yourself | Lampway starts them as separate processes on your action and never reads their credential files. They are not distributed here |

## 4. Algorithms and ideas implemented from published descriptions (no third-party code copied)

| Source | Where it shows | Notes |
|---|---|---|
| Abdrashitov, Raichstat, Monsen, Hill, "Robust Skin Weights Transfer via Weight Inpainting" (SIGGRAPH Asia 2023); the robust Laplacian (Sharp and Crane) | `scripts/rig/robust_weight_transfer.py` | written from the paper's description, **not** copied from the add-on of the same name (GPL-2.0-or-later) |
| TexTools-Blender, UniV, Mio3 UV (GPL-3.0-or-later add-ons); UniMate (MIT) naming conventions | `features/uv_layout.py`, `uv_rectify.py`, `uv_texel.py`, `pipeline/anim_labels.py` | reimplemented over bmesh from the operations' published descriptions; UniMate's vocabulary tables were not vendored. See [`docs/lampway/resource-audit.md`](docs/lampway/resource-audit.md) |
| Stefan's 3D AI wiki workflows | `mesh_prep`, `asset_acceptance`, `rig_armor` and the contracts built on them | notes, no code |
| The maintainer's own tool shelf | many modules under `lampway_tools/scripts/` | the maintainer's own code, ported with SPDX headers, the shelf path and a content hash in the header |

Audited and **not** incorporated: Robust Weight Transfer (the add-on), alpaca3d, NifTools, Auto-Rig Pro alternatives, kimodo-cpp (weights have restrictive licences), img2mat_pro. See the resource audit for each decision.

## 5. Python dependencies (installed by pip, not distributed)

The server's runtime dependencies are pinned in `server/requirements-lock.txt`: starlette and uvicorn (BSD-3-Clause), websockets (BSD-3-Clause), httpx (BSD-3-Clause), the Anthropic SDK (MIT), PyJWT (MIT), python-multipart (Apache-2.0), Pillow (HPND) and their transitive dependencies; tests add pytest (MIT) and pytest-timeout (MIT). The Asset Vault additionally imports numpy (BSD-3-Clause), which the lock does not yet list. The client bundles the packages in `scripts/python_requirements.txt` (keyring, truststore, websocket-client, httpx, mcp, mistune, Pillow, cryptography). Licences are as published on PyPI and were not re-read for this file.

## 6. Fonts

| Font | Licence | Where | Notes |
|---|---|---|---|
| **Clash Grotesk Regular** (Indian Type Foundry, via Fontshare) | [ITF Free Font License](src/release/datafiles/fonts/ClashGrotesk-LICENSE.txt) | upstream Cinema Mode button | font asset **absent** from this public tree; original licence and attribution retained, no Clash Grotesk font ships |
| Blender's bundled interface and monospace fonts | their own licences, inside upstream | the Blender submodule | not modified by Lampway |
| **Inter**, **IBM Plex Mono**, **Fraunces** | SIL Open Font License 1.1 (as published; to be confirmed when vendored) | **planned**, the client facelift | not in the tree yet; this table is updated when they are added and each licence text is placed in `LICENSES/` |

## 7. Brand art

No upstream artwork ships. The placeholder art is generated by `scripts/dev/lampway_placeholder_art.py` and replaced by the brand art in `scripts/dev/brand_art`, which is Lampway's own.
