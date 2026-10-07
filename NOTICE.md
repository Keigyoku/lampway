<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Notices

Lampway is a fork of the Mixar desktop client, which is published under
GPL-3.0-or-later by Adeveda Enterprises Private Limited and is itself built on top
of Blender. Lampway is not affiliated with, endorsed by, or supported by Mixar,
Mixar Inc or Adeveda Enterprises Private Limited.

## Upstream

The Mixar desktop client (<https://github.com/Mixar-AI/mixar-app>) is developed by:

- **Adeveda Enterprises Private Limited** — a company incorporated in India, the copyright
  holder of the Mixar source code and brand assets.
- **Mixar Inc** — a company incorporated in the United States, operator of Mixar's hosted
  backend services.

Upstream copyright notices in this repository are retained as the GPL requires. Lampway's
own changes are copyright 2026 Lampway contributors and are published under the same
GPL-3.0-or-later license. File-level SPDX metadata and [REUSE.toml](REUSE.toml) are the
authoritative source for per-file licensing.

Blender is free software. Blender-derived files and upstream materials retain their own
notices and licenses.

## Brand removal

The Mixar name, Mixar logo, Mixie name and related brand assets are trademarks or pending
trademarks of Adeveda Enterprises Private Limited and were licensed separately from the
source. Lampway ships none of them: every brand asset has been replaced by placeholder art
and every user-facing name and link has been changed. See [TRADEMARKS.md](TRADEMARKS.md).

Mixar's hosted backend services are not part of this repository and Lampway does not talk
to them: the client is configured for a Lampway server (`src/scripts/mixar/config/brand.py`).

## Third-Party Software Acknowledgements

### ucupaint

The texture painting module builds on the open-source [ucupaint](https://github.com/ucupumar/ucupaint)
addon by [ucupumar](https://github.com/ucupumar), used under the terms of the GNU General
Public License version 3 or later.

Specifically:

- **Asset library** — `src/scripts/mixar/modules/paint/core/lib/lib.blend` is a modified version
  of ucupaint's `lib_281.blend`, containing layer/channel node groups derived from the original.
- **Layer and channel architecture** — files under `src/scripts/mixar/modules/paint/core/io/connections/`,
  `src/scripts/mixar/modules/paint/core/layer/create_channels.py`, and parts of the UI under
  `src/scripts/mixar/modules/paint/ui/` adapt ucupaint's patterns for channel handling,
  normal/height layer composition, and connection topology. The adaptations have been
  substantially modified, but the design lineage is ucupaint's.

ucupaint's license is GPL-3.0-or-later (see [LICENSES/GPL-3.0-or-later.txt](LICENSES/GPL-3.0-or-later.txt)).
The adaptations of ucupaint code are also distributed under GPL-3.0-or-later. Per-file SPDX
metadata and [REUSE.toml](REUSE.toml) record per-file copyright attribution.

### Clash Grotesk

The Cinema Mode button uses Clash Grotesk Regular by Indian Type Foundry,
obtained from [Fontshare](https://www.fontshare.com/fonts/clash-grotesk) under
the [ITF Free Font License](LICENSES/LicenseRef-ITF-FFL.txt). The font is used
for application UI only and is excluded from public source snapshots.

### Audited, not incorporated

The third-party Blender add-ons and tools reviewed for the feature pass (Robust Weight Transfer, TexTools-Blender, UniV,
AutoRemesher, NifTools) are not part of Lampway: no code from them was copied. The decisions and licences are in
[docs/lampway/resource-audit.md](docs/lampway/resource-audit.md).

### Hermes Agent (Lampway's agent engine, pinned)

`third_party/hermes-agent` is a git submodule pinned to a release of Hermes Agent (<https://github.com/NousResearch/hermes-agent>,
MIT License, Copyright (c) 2025 Nous Research). Lampway runs it as a separate process, its agent engine in Mode 1
(`docs/reports/agent-modes-spec.md` E1), built by `scripts/lampway/engine_env.py` into its own environment. Anyone who
redistributes that environment must carry Hermes's MIT notice and the notices of the packages its lock file installs.

### AutoRemesher (built on request, not distributed)

`native/quadremesh/` is Lampway's own Qt-free command line around the quad-remeshing core of AutoRemesher
(<https://github.com/huxingyi/autoremesher>, MIT, Copyright (c) 2026 Dust3D Project). The AutoRemesher
sources are not part of this repository: `native/quadremesh/build.sh` fetches the pinned commit when a user
builds the executable, and Lampway's retopo tool runs that executable as a separate process (configured by the
`autoremesher_bin` setting; the app downloads nothing). Anyone who redistributes a built executable must carry
the MIT notice and the notices of its bundled TBB (Apache-2.0), Eigen (MPL-2.0), meshoptimizer (MIT) and
isotropicremesher sources.

### Mr. Mak Workspace (character-sheet prompts)

The character-sheet and part prompt templates in `server/lampway_server/prompts/builtin/` (`sheet-*`, `part-*`, `turntable-360-locked`) are adapted from the character-sheet pipeline of Mr. Mak Workspace
(MIT, Copyright (c) 2026 Mr. Mak Workspace contributors; upstream commit 1e0c7c3, `.agents/skills/character-sheet-pipeline/prompts/`). The licence text is `LICENSES/MIT.txt`; each template names its
source file in its `provenance`. Nothing is copied from the upstream arena-viewer header (its licence lineage is uncleared).

### img2threejs (clip classification)

`src/scripts/mixar/modules/lampway_tools/pipeline/clip_features.py` and its test `tests/lampway_tools/test_wave4b_clip_features.py` are translations of `forge/stage5_rig/clip_features.py` and
`forge/tests/test_clip_features.py` from the img2threejs skill vendored in the Mr. Mak Workspace clone (Apache-2.0; the licence text is `LICENSES/Apache-2.0.txt`). Each file carries its upstream notice and a
statement that it was modified. The default thresholds come from one subject on one rig (11 clips) and are reported as such.

### TITAN (the canonical rig and animation converter)

`src/scripts/mixar/modules/lampway_tools/rig_convert/` (`animation_canon.py`, `canon.py`, `skin_bind.py`, `axi_common.py`,
`editor_runner.py`, the Blender recipes and the reference profiles under `recipes/`), `src/scripts/mixar/modules/lampway_tools/ue_recipes/`
and the suites `tests/lampway_tools/test_rig_convert_*.py` are ported from the TITAN project, same author, on the owner's word; GPL-3.0-or-later
in Lampway. Each ported file names its source path and sha256. The wire schema ids (`titan.animation/1`, `titan.animation-profile/1`,
`titan.canonical-mesh/1`, `titan.native-bind-skin/1` and the rest) are a stable contract shared with TITAN and are kept unchanged. The
`anim-profile-*.json` files are measured bone tables (names, parents, bind and reference transforms) of two UE skeletons: data the
converter needs, not engine content. Skin and morph (`skin_bind.py`) ship as WIP tooling.

### MB UE5 Rig Creator Pro (bone-name tables)

`src/scripts/mixar/modules/lampway_tools/rig_tools/families/*.json`: bone-name tables derived from MB UE5 Rig Creator Pro 3.1.0
(MagicBoneTools), GPL-3.0-or-later (`MagicBoneTop_Panel.py` `rigs_liss_my_op`, slot names from `CreateRig.py`). Data only; no MB code is
ported. The rigify table is verified against a Rigify rig generated headless (tests/lampway_tools/test_rig_tools.py); the mixamo table
against MB's own table and the canon golden R01 only.

## Third-party models (Asset Vault)

The Asset Vault runs three open-weights models locally, on the CPU, through ONNX Runtime. No weights are committed to this repository. The client build fetches them into the
install (`scripts/lampway/fetch_models.py`, called by `scripts/lampway/build_linux.sh`), each file pinned to a repository commit and checked against the sha256 below; a
`PROVENANCE.json` beside each model records what was fetched. An install without them can fetch them with one click (public files; nothing of the user's is sent). Until the
weights and `onnxruntime` are both present, the Vault uses its deterministic descriptors instead. The pins live in `server/lampway_server/library/models.json`.

| model id | role | licence | source | export (repository @ commit) |
|---|---|---|---|---|
| `clip-vit-b-32` | image embeddings (the CLIP ViT-B/32 image tower) | MIT (see below) | <https://github.com/openai/CLIP> | `Xenova/clip-vit-base-patch32` @ `d15189d7028b43f1d3e65039190477f6af591c2a` |
| `clip-vit-b-32-text` | text queries into the same space as the image tower (CLIP's text tower) | MIT (see below) | <https://github.com/openai/CLIP> | `Xenova/clip-vit-base-patch32` @ `d15189d7028b43f1d3e65039190477f6af591c2a` |
| `bge-small-en-v1.5` | text embeddings (CLS pooling) | MIT | <https://huggingface.co/BAAI/bge-small-en-v1.5> | `BAAI/bge-small-en-v1.5` @ `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |

| file | sha256 |
|---|---|
| `clip-vit-b-32/model.onnx` (onnx/vision_model.onnx, 351 685 709 bytes) | `fd6e1402a588279d1723c7534d4bcba5bc0b14b47dfab0e46f8c47b8270d7d40` |
| `clip-vit-b-32-text/model.onnx` (onnx/text_model.onnx, 254 058 553 bytes) | `3f6571f5bad13a97c469c1622e1cfc4d9aef78b79fdbfcff804ca357bfada8cc` |
| `clip-vit-b-32-text/vocab.json` | `5047b556ce86ccaf6aa22b3ffccfc52d391ea4accdab9c2f2407da5b742d4363` |
| `clip-vit-b-32-text/merges.txt` | `9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a` |
| `bge-small-en-v1.5/model.onnx` (onnx/model.onnx, 133 093 490 bytes) | `828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35` |
| `bge-small-en-v1.5/vocab.txt` | `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3` |

Licences, as read on 2026-10-05: `BAAI/bge-small-en-v1.5` carries `license: mit` in its model card and README. The `openai/CLIP` repository's `LICENSE` is the MIT License
(Copyright (c) 2021 OpenAI); neither the `openai/clip-vit-base-patch32` nor the `Xenova/clip-vit-base-patch32` Hugging Face card carries a licence tag, so the MIT terms are
taken from the upstream repository. [UNVERIFIED] that the repository's MIT text is meant to cover the released weights; OpenAI's CLIP model card describes the model as a
research output. The three `.onnx` sha256 values equal the Hugging Face LFS object ids of the pinned commits.
