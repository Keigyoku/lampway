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
