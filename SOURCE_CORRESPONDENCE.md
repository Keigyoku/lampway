<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Source Correspondence

This document tracks the source-to-binary mapping for Lampway releases.

## Release rule

Release binaries are built from the exact public source tag, and the checksums published with them name that tag.

1. Finalise the version in `VERSION` and commit it.
2. Tag the commit in <https://github.com/Keigyoku/lampway>.
3. Build from the tag with `scripts/lampway/build_linux.sh` (or the platform's build script).
4. Publish checksums beside the artifacts.
5. Keep the tag, the binary version, the release notes and the downloads page in step.

No release exists yet. The first one is `v0.1.0`.

## Source package contents

A release includes the Lampway source for the tag, the build and packaging scripts used, the `upstream` submodule pointer with instructions for fetching Blender source, the licence files and SPDX metadata, and the scripts that regenerate generated build inputs.

Build configuration, signing credentials and private deployment details are not part of the public repository.

## Derived Works

Mixar's texture painting module is, in part, a derivative work of the open-source [ucupaint](https://github.com/ucupumar/ucupaint) addon by [ucupumar](https://github.com/ucupumar), licensed GPL-3.0-or-later.

Derived paths in this repository:

- `src/scripts/mixar/modules/paint/core/lib/lib.blend` — modified from ucupaint's `lib_281.blend`
- `src/scripts/mixar/modules/paint/core/io/connections/layer_connections_*.py` — adapt ucupaint's layer/channel connection patterns
- `src/scripts/mixar/modules/paint/core/layer/create_channels.py` — adapts ucupaint's channel creation logic
- `src/scripts/mixar/modules/paint/ui/lists/channel_uilist.py` — channel UI list patterns
- `src/scripts/mixar/modules/paint/ui/utils/ui_helpers_texture_sets_channels.py` — channel settings UI patterns

Attribution is recorded in [NOTICE.md](NOTICE.md) and per-file copyright in [REUSE.toml](REUSE.toml). All derivations are distributed under GPL-3.0-or-later, consistent with ucupaint's license.

Upstream ucupaint source: `https://github.com/ucupumar/ucupaint`.
