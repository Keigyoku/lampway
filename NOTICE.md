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
