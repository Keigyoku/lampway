# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's ruling 6 (2026-10-06): the batch tools that lost their path when the free-text runner went get typed
server definitions, so the Way shows each one and nothing is lost. Every tool the runner registers
(src/scripts/mixar/modules/lampway_tools/runner.py ``TOOLS``) has a typed form: a Def whose ``batch`` is its name, or the
in-app Def the Way offers for it (``COVERED_BY``)."""

import re
from pathlib import Path

from lampway_server.agent.lampway_tools import DEFS

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "src/scripts/mixar/modules/lampway_tools/runner.py"
# batch tools whose typed form is the in-app tool the Way already offers (scripts/lampway/facelift/tool_specs.py FEATURES)
COVERED_BY = {"uv_score": "uv_score", "bake_maps": "bake_maps", "material_bake": "material_bake_export",
              "asset_catalog_export": "asset_catalog_export"}


def registered() -> list:
    return re.findall(r'_t\("([a-z0-9_]+)", "(?:blender|numpy|science)"', RUNNER.read_text(encoding="utf-8"))


def test_every_registered_batch_tool_has_a_typed_form():
    names = registered()
    assert len(names) >= 35, names
    batch = {d.batch for d in DEFS if d.batch}
    api = {d.api for d in DEFS if d.api}
    missing = [n for n in names if n not in batch and COVERED_BY.get(n) not in api]
    assert missing == [], f"batch tools with no typed form (the Way cannot show them): {missing}"


def test_the_forms_added_for_the_way_describe_every_field():
    """The forms this ruling added (agent/batch_forms.py); the older batch Defs are the schema ratchet's to pay down."""
    from lampway_server.agent.batch_forms import BATCH_FORM_DEFS
    for d in BATCH_FORM_DEFS:
        undescribed = [p.name for p in d.params if not (p.desc or "").strip()]
        assert undescribed == [], (d.name, undescribed)
