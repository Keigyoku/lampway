"""The procedural library into the Vault (specs/asset_library/asset_seed_procedural.md): every preset of the client's procedural library (55: 40 metals, 5 leathers,
6 cloths, 4 embroideries from 12 templates) becomes a ``material/procedural`` asset with its node-group script, its measured stats and, through ``asset_render``,
an EEVEE ball.

``export`` runs the real binary headless and niced (factory settings, bridge off): the client module emits each script and measures each group with EEVEE emission
bakes; nothing is authored here. ``seed`` is the user's click and is idempotent; the export's manifest hash is recorded per library version, so a changed library at
the same version is refused until it is bumped or upgraded. ``render_sheet`` tiles a category's balls: the screenshot evidence."""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from . import ingest as I
from .render import blender_command
from .store import AssetLibrary, LibraryError

ROLES = {"metal": "plate_metal", "leather": "leather", "cloth": "cloth", "embroidery": "embroidery"}
LICENSE = "GPL-3.0-or-later"
_EXPORT = '''import json, sys
from mixar.modules.lampway_tools.features import procedural_library as PL
out = sys.argv[sys.argv.index("--") + 1]
res = PL.verify(None, bake=True)
if res["broken"]:
    raise SystemExit("broken materials: " + json.dumps(res["broken"]))
mats = []
for m in res["materials"]:
    p = PL.PRESETS[m["material_id"]]
    mats.append({**{k: v for k, v in m.items() if not k.startswith("_")}, "script": PL.emit(m["material_id"]), "look_ref": p.get("look_ref")})
json.dump({"library_version": PL.LIBRARY_VERSION, "manifest_sha256": PL.manifest_hash(), "materials": mats}, open(out, "w"))
'''


def export(blender, work, runner=subprocess.run) -> dict:
    """The client library's presets, scripts and EEVEE-measured stats, from one headless run of the real binary."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    script, out = work / "export_procedural.py", work / "procedural.json"
    script.write_text(_EXPORT, encoding="utf-8")
    argv, env = blender_command(blender, out, work / "scratch", script=script)
    p = runner(argv, env=env, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0 or not out.exists():
        raise LibraryError(f"the procedural export failed: {((p.stderr or '') + (p.stdout or ''))[-400:].strip()}")
    return json.loads(out.read_text())


def seed(lib: AssetLibrary, doc: dict, by: str, upgrade: bool = False) -> dict:
    I.Ingest._need_user(by, "seeding the procedural library")
    rec = lib.root / "procedural_manifest.json"
    seen = json.loads(rec.read_text()) if rec.exists() else {}
    ver, sha = str(doc["library_version"]), doc["manifest_sha256"]
    if seen.get(ver) not in (None, sha) and not upgrade:
        raise LibraryError("library manifest changed: bump library_version or run seed --upgrade")
    out = {"ok": True, "library_version": ver, "count": 0, "created": 0, "new_versions": 0, "unchanged": 0, "ids": {}}
    with lib.bulk():
        for m in doc["materials"]:
            mid, cat = m["material_id"], m["category"]
            res = lib.put({"kind": "material", "subtype": "procedural", "name": m["name"], "description": m.get("description"), "license": LICENSE,
                           "source": {"kind": "procedural_library", "key": mid, "label": "Lampway procedural library"},
                           "files": [{"role": "script", "bytes": m["script"].encode("utf-8"), "storage": "cas", "name": f"{mid}.py"}],
                           "stats": {"shader": f"LWP_{mid}", "inputs_json": json.dumps(m.get("inputs") or []), "metallic_mean": m.get("metallic_mean"),
                                     "roughness_mean": m.get("roughness_mean"), "tileable": 1, "build_ms": m.get("build_ms"), "generator": m.get("generator"), "role": cat},
                           "attrs": {"template": m.get("template"), "look_ref": m.get("look_ref"), "hue_deg": m.get("hue_deg"), "chroma": m.get("chroma"),
                                     "value_mean": m.get("value_mean"), "base_color_mean": m.get("base_color_mean"), "library_version": ver, "material_id": mid},
                           "terms": [{"facet": "material_role", "label": ROLES.get(cat, cat)}, {"facet": "pipeline_stage", "label": "library"}]})
            out["ids"][mid] = res["id"]
            out["count"] += 1
            if res["created"] and res["version"] == 1:
                out["created"] += 1
            elif res["created"]:
                out["new_versions"] += 1
            else:
                out["unchanged"] += 1
    seen[ver] = sha
    rec.write_text(json.dumps(seen, indent=1, sort_keys=True))
    return out


def render_sheet(lib: AssetLibrary, category: str, out_dir, cell: int = 192, cols: int = 8) -> dict:
    """One labelled JPEG of every ball in ``category`` (the balls come from asset_render)."""
    from PIL import Image, ImageDraw, ImageFont
    rows = lib._reader().execute("SELECT a.id,a.name FROM asset a JOIN version v ON v.asset_id=a.id AND v.n=a.current_version JOIN material_stats m ON m.version_id=v.id "
                                 "WHERE a.kind='material' AND a.subtype='procedural' AND a.status='active' AND m.role=? ORDER BY a.name", (category,)).fetchall()
    cells = []
    for aid, name in rows:
        ball = [f for f in lib.get(aid)["files"] if f["role"] == "ball" and f["locations"]]
        if ball:
            cells.append((name, ball[0]["locations"][0]["path"]))
    if not cells:
        raise LibraryError(f"no balls rendered for {category!r}: enqueue ball for its materials first")
    n = min(cols, len(cells))
    label = 18
    sheet = Image.new("RGB", (n * cell, -(-len(cells) // n) * (cell + label)), (40, 40, 40))
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=11)
    for i, (name, path) in enumerate(cells):
        x, y = (i % n) * cell, (i // n) * (cell + label)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((cell, cell)), (x, y))
        draw.text((x + 3, y + cell + 3), name[:30], fill=(230, 230, 230), font=font)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    b = io.BytesIO()
    sheet.save(b, "JPEG", quality=90)
    path = out / f"procedural_{category}.jpg"
    path.write_bytes(b.getvalue())
    return {"ok": True, "path": str(path), "cells": len(cells)}
