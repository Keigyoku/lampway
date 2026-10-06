# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The MIXAR_ASSETS editor is the Asset Vault (lane vault-ui owns it in modules/asset_library): its Editor Type label and
its space type name say so, not Mixar's "Texturing Assets". The real-binary half is
tests/lampway_tools/test_lampway_vault_editor_live.py."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RNA_SPACE = ROOT / "src/source/blender/makesrna/intern/rna_space.cc"
SPACE_CC = ROOT / "src/source/blender/editors/space_mixar_assets/space_mixar_assets.cc"


def test_the_editor_type_label_is_asset_vault():
    item = re.search(r'\{SPACE_MIXAR_ASSETS,\s*"MIXAR_ASSETS",\s*\w+,\s*"([^"]+)"', RNA_SPACE.read_text(encoding="utf-8"))
    assert item and item.group(1) == "Asset Vault"
    assert 'STRNCPY_UTF8(st->name, "Asset Vault");' in SPACE_CC.read_text(encoding="utf-8")
