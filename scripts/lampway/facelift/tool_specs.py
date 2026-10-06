#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the typed tool specs the client's tool panels draw from (facelift contract 07: no free-text tool runner).

The agent already calls every Lampway tool through a typed definition (server/lampway_server/agent/lampway_tools.py,
``DEFS``); the sidebar uses the same definitions, so a tool's form and the agent's schema cannot drift. This writes the
batch tools and the feature tools among them to ``src/scripts/mixar/modules/lampway_tools/tool_specs.json``. Generated:
never edit the JSON by hand.

    python3 scripts/lampway/facelift/tool_specs.py           # write
    python3 scripts/lampway/facelift/tool_specs.py --check   # exit 1 when the committed file is stale
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "src/scripts/mixar/modules/lampway_tools/tool_specs.json"
#: The feature tools the sidebar offers (their api function names); every batch tool is offered too.
FEATURES = ("retopo", "uv_unwrap", "segment_mesh", "auto_rig", "mesh_prep", "asset_acceptance", "detail_normals",
            "image_to_3d", "render_video", "export_piece")


def specs() -> list:
    sys.path.insert(0, str(ROOT / "server"))
    from lampway_server.agent.lampway_tools import DEFS
    out = []
    for d in DEFS:
        if not (d.batch or d.api in FEATURES):
            continue
        out.append({"name": d.name, "description": d.description, "batch": d.batch, "api": d.api if not d.batch else None,
                    "params": [{"name": p.name, "type": p.type, "desc": p.desc, "required": p.required, "flag": p.flag,
                                "repeat": p.repeat} for p in d.params]})
    return sorted(out, key=lambda s: s["name"])


def render() -> str:
    return json.dumps({"generated_by": "scripts/lampway/facelift/tool_specs.py", "tools": specs()}, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = render()
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"tool_specs: {OUT.relative_to(ROOT)} is stale: run scripts/lampway/facelift/tool_specs.py")
            return 1
        print("tool_specs: current")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"tool_specs: {len(json.loads(text)['tools'])} tools -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
