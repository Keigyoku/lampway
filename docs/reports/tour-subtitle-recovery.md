<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Original tour subtitle recovery

The eight original dubbed subtitle files were recovered unchanged from the [official public Mixar 4.2.2 Windows release](https://github.com/Mixar-AI/mixar-app/releases/tag/v4.2.2). Its MSI SHA256 is `0c5e9fb2ddf5fb935cb820fd562f00d0a2f6c47bb9789ed6854e701143473f91`; the downloaded archive matched the release API digest. No application was installed or executed. MSI File/Component/Directory tables identify each payload under `Mixar/5.2/scripts/mixar/modules/onboarding/assets/tour/subtitles/`.

The [upstream REUSE declaration](https://github.com/Mixar-AI/mixar-app/blob/main/REUSE.toml) attributes onboarding assets to Open-source contributors under GPL-2.0-or-later. Existing matching repository attribution is retained. Authored bytes, cue counts and timing are preserved; these are not generated English-beat fallback tracks. The existing fifty-language validation checks nonempty text, valid nonoverlapping windows and the 137300 ms tour bound.

| Locale | Bytes | Cues | SHA256 |
|---|---:|---:|---|
| de | 3480 | 38 | `539fd52bc6df97673fdb1b1560a519807566263267e4c5fa1e0da73b54a45a52` |
| es | 3615 | 38 | `3fc3bb631bd203f9024172c13c5997f1beb1b3434ec8836fe8c5ebb31175693e` |
| fr | 3426 | 36 | `604490086218fa0d1c988d57798787d7f1f6b142c3fd4737d7608f677b8539da` |
| it | 3508 | 38 | `671341787da5fdd946822e87c1f498b87c43e74767d622847964a3640a9bd789` |
| ja | 4083 | 34 | `a47ce4e5842d28ec2055ec55f68bd72f6e8082e18fe9ba7521e85e9b47a2a8e7` |
| ko | 3724 | 34 | `bdf0998f2e8a74d0ff13f0e1539f305b93b0961424d292a47f04f7271a647c68` |
| pt | 3557 | 38 | `9580f902eecbbd2b96eef0963a482b2993715e8a5bef8b7e9b650fd97d514089` |
| zh | 3308 | 33 | `82e7f58be41654fa611b29df66073e72a63511aeeb159107b9feded53e681de4` |

The public source tree omits these original assets. The runtime tour-pack manifest supplies timing/video packs rather than subtitle files, so runtime retrieval cannot restore the missing bundled tracks. The other forty-one tracks use the existing checked-in authoring inputs and generator. No private asset transfer, runtime egress route or fabricated translation was used.
