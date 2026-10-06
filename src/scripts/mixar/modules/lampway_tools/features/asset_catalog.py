# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_catalog_export (specs/asset_library/asset_place.md section 6, "Catalogue integration", export and link): library assets published as a Blender asset library. A niced
headless worker builds ``lampway_library.blend`` from the assets' own files (the live file is never marked or saved), every datablock marked as an asset with its catalogue;
``blender_assets.cats.txt`` is written from the taxonomy (``<facet>/<label>`` of the asset's first term, in the schema's facet order), each catalogue id the UUID5 of its path, so a
re-export keeps every id. Lampway only overwrites a library it wrote itself (``.lampway_library.json`` lists it); ``register`` adds the folder to Blender's asset libraries."""

import json
import os
import re
import uuid
from pathlib import Path

import bpy

from .asset_place import PlaceError, file_of

BLEND = "lampway_library.blend"
MANIFEST = ".lampway_library.json"
CATS = "blender_assets.cats.txt"
FACET_ORDER = ("piece_type", "material_role", "era_style", "faction", "motion_type", "camera_template", "view", "pipeline_stage", "studio")
SLOTS = {"material": "materials", "mesh": "objects", "rig": "objects", "animation": "actions"}
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Keigyoku/lampway/asset-catalog")


def catalog_path(asset: dict) -> str:
    terms = [t for t in asset.get("terms") or [] if t.get("facet") and t.get("label")]
    terms.sort(key=lambda t: FACET_ORDER.index(t["facet"]) if t["facet"] in FACET_ORDER else len(FACET_ORDER))
    raw = f"{terms[0]['facet']}/{terms[0]['label']}" if terms else f"kind/{asset.get('kind')}"
    return re.sub(r"[:\n]", "-", raw)


def catalog_id(path: str) -> str:
    return str(uuid.uuid5(NAMESPACE, path))


def _cats_text(paths) -> str:
    every = set()
    for p in paths:
        parts = p.split("/")
        every.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    lines = ["# This is an Asset Catalog Definition file for Blender.", "# Written by Lampway's asset_catalog_export from the Asset Vault taxonomy.", "", "VERSION 1", ""]
    lines += [f"{catalog_id(p)}:{p}:{p.replace('/', '-')}" for p in sorted(every)]
    return "\n".join(lines) + "\n"


def _item(asset: dict) -> dict:
    kind = asset.get("kind")
    if kind not in SLOTS:
        raise PlaceError(f"a {kind} does not publish to a Blender asset library: the kinds are {sorted(SLOTS)}")
    roles = ("blend",) if kind == "material" else ("main",)
    path, sha, _ = file_of(asset, roles)
    if not path.lower().endswith(".blend") and kind != "mesh":
        raise PlaceError(f"{asset.get('name')!r}: only a .blend {kind} publishes; {os.path.basename(path)} is not one")
    cpath = catalog_path(asset)
    return {"slot": SLOTS[kind], "path": path, "name": str(asset.get("name")), "import": not path.lower().endswith(".blend"), "catalog_path": cpath,
            "catalog_id": catalog_id(cpath), "lw": {"lw_asset_id": str(asset.get("id")), "lw_asset_version": str(asset.get("version")), "lw_asset_sha256": str(sha)}}


def _owned(dest: Path) -> bool:
    try:
        return BLEND in json.loads((dest / MANIFEST).read_text(encoding="utf-8")).get("blends", [])
    except (OSError, ValueError, AttributeError):
        return False


def _register(dest: Path, name: str) -> str:
    libs = bpy.context.preferences.filepaths.asset_libraries
    for lib in libs:
        if os.path.normpath(lib.path) == os.path.normpath(str(dest)):
            return lib.name
    bpy.ops.preferences.asset_library_add(directory=str(dest))
    lib = next(lb for lb in libs if os.path.normpath(lb.path) == os.path.normpath(str(dest)))
    lib.name = name
    return lib.name


def asset_catalog_export(assets: list, dest: Path, register=False, library_name="Lampway Vault", timeout=900) -> dict:
    from .. import runner as RUN
    from .. import settings as S
    if not assets:
        raise PlaceError("no assets to publish: pass the records (lampway_vault_get) of materials, node groups, meshes, rigs or actions")
    items = [_item(a) for a in assets]
    dest.mkdir(parents=True, exist_ok=True)
    blend = dest / BLEND
    if blend.exists() and not _owned(dest):
        raise PlaceError(f"{blend} was not written by Lampway: pick an empty folder (Lampway never overwrites a .blend it did not create)")
    job, result = dest / ".catalog_job.json", dest / ".catalog_result.json"
    job.write_text(json.dumps({"dest_blend": str(blend), "items": items}), encoding="utf-8")
    r = RUN.run("asset_catalog_export", [str(job), str(result)], S.load(), timeout=timeout)
    job.unlink(missing_ok=True)
    if r.rc != 0 or not result.exists():
        raise PlaceError("the catalogue worker failed: " + re.sub(r"\s+", " ", r.stdout)[-400:])
    done = json.loads(result.read_text(encoding="utf-8"))
    result.unlink(missing_ok=True)
    (dest / CATS).write_text(_cats_text([i["catalog_path"] for i in items]), encoding="utf-8")
    (dest / MANIFEST).write_text(json.dumps({"blends": [BLEND], "written_by": "lampway asset_catalog_export"}, indent=1), encoding="utf-8")
    out = {"blend": str(blend), "catalogs": {i["catalog_path"]: i["catalog_id"] for i in items}, "published": done.get("published", []), "previews": done.get("previews", "none")}
    if register:
        out["registered"] = _register(dest, library_name)
    return out
