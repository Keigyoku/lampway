# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stage an additive delta for a texture library (STATUS O33). The shelf's stage_library_delta.py was a recorded build for one delta; its rules are what
this keeps, driven by a manifest ({library, library_version, previous_index, approved_folders, catalog {file, previous, status}, files: [{src, dst, role,
color_space, provider, method, model_version, seed, cost, parents [{file, sha256}], status, derived_by?, ...}]}):

* immutable versioned files: every dst names a version (_v####), is new to the library, and gets its sha256, size and dimensions recorded;
* lineage resolves INSIDE the library: a parent is a file of this delta or of the current library listing, with the same sha256;
* unknown model / seed / cost are recorded as null, never guessed: each key must be present, a seed is an integer or null, a cost a number or null;
* colour images declare their colour space; a data map (normal, roughness, metallic, ao, orm, height, displacement, mask) is Non-Color and names the
  tool that measured or baked it (derived_by): no PBR map is inferred from a colour image;
* nothing is staged under an approved-release folder, and approved_final_release is false on every record;
* the staging root is one this tool made (it carries a marker) or none; a refused delta writes nothing.
Then a catalog (the delta's records) and INDEX.<library_version>.json (every staged file's sha256 and size)."""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath

MARK = ".made-by-texture_library_stage"
COLOUR = ("basecolor", "emission", "reference")
DATA = ("normal", "roughness", "metallic", "ao", "orm", "height", "displacement", "mask", "material_id")
REQUIRED = ("src", "dst", "role", "provider", "method", "model_version", "seed", "cost", "parents", "status")
VERSION = re.compile(r"_v\d{4}(?:\.[A-Za-z0-9]+)$")


class StageRefused(ValueError):
    pass


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _dims(p):
    try:
        from PIL import Image
        with Image.open(p) as im:
            return list(im.size)
    except Exception:  # noqa: BLE001 - not an image
        return None


def _check(m, listing):
    errs = []
    lib_files = {x["Path"]: (x.get("Hashes") or {}).get("sha256") for x in listing or [] if not x.get("IsDir")}
    approved = tuple(m.get("approved_folders") or ())
    files = m.get("files")
    if not isinstance(files, list) or not files:
        raise StageRefused("the manifest needs files: a non-empty list")
    for k in ("library", "library_version", "previous_index", "catalog"):
        if k not in m:
            errs.append(f"manifest: missing {k!r}")
    if not re.fullmatch(r"v\d{4}", str(m.get("library_version", ""))):
        errs.append("manifest: library_version is v####")
    dsts = {}
    for i, f in enumerate(files):
        who = f"file {i} ({f.get('dst', '?')})"
        for k in REQUIRED:
            if k not in f:
                errs.append(f"{who}: missing {k!r} (an unknown value is null, never left out or guessed)")
        dst = str(f.get("dst", ""))
        pp = PurePosixPath(dst)
        if not dst or pp.is_absolute() or ".." in pp.parts:
            errs.append(f"{who}: dst must stay inside the library (a relative path, no '..')")
        if approved and dst.startswith(approved):
            errs.append(f"{who}: {dst} is under an approved-release folder; staging never writes there")
        if not VERSION.search(pp.name):
            errs.append(f"{who}: the file name must carry its version (_v####): files are immutable and versioned")
        if dst in dsts or dst in lib_files:
            errs.append(f"{who}: {dst} already exists in the library or this delta; a file is never replaced")
        if not Path(str(f.get("src", ""))).is_file():
            errs.append(f"{who}: no source file at {f.get('src')}")
        else:
            dsts[dst] = _sha(f["src"])
        if "seed" in f and f["seed"] is not None and not isinstance(f["seed"], int):
            errs.append(f"{who}: seed is an integer or null (unknown), not {f['seed']!r}")
        if "cost" in f and f["cost"] is not None and not isinstance(f["cost"], (int, float)):
            errs.append(f"{who}: cost is a number or null (unknown)")
        if "model_version" in f and f["model_version"] is not None and not isinstance(f["model_version"], str):
            errs.append(f"{who}: model_version is a string or null (unknown)")
        role = f.get("role")
        if role in COLOUR:
            if not f.get("color_space"):
                errs.append(f"{who}: a {role} image needs its colour space declared (e.g. sRGB)")
        elif role in DATA:
            if f.get("color_space") != "Non-Color" or not str(f.get("derived_by") or "").strip():
                errs.append(f"{who}: a {role} map is Non-Color and names the tool that measured or baked it (derived_by): no PBR map is inferred")
        else:
            errs.append(f"{who}: role {role!r} is one of {COLOUR + DATA}")
    for i, f in enumerate(files):
        for p in f.get("parents") or []:
            pf, ps = p.get("file"), p.get("sha256")
            have = dsts.get(pf, lib_files.get(pf))
            if have is None:
                errs.append(f"file {i}: parent {pf} does not resolve inside the library (neither this delta nor the library listing)")
            elif have != ps:
                errs.append(f"file {i}: parent {pf} sha256 {str(ps)[:12]} differs from the library's {str(have)[:12]}")
    if errs:
        raise StageRefused("refused:\n  " + "\n  ".join(errs))
    return dsts


def stage(manifest, staging_root, library_listing=None):
    m = manifest
    root = Path(staging_root)
    if root.exists() and not (root / MARK).is_file():
        raise StageRefused(f"refused: {root} exists and was not made by this tool (no {MARK}); choose a new staging root")
    _check(m, library_listing)
    if root.exists():
        shutil.rmtree(root)
    lib = root / m["library"]
    lib.mkdir(parents=True)
    (root / MARK).write_text("staging directory made by texture_library_stage; safe for it to replace\n")
    records = []
    for f in m["files"]:
        dst = lib / f["dst"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f["src"], dst)
        rec = {k: v for k, v in f.items() if k != "src"}
        rec.update(filename=dst.name, sha256=_sha(dst), bytes=dst.stat().st_size, dimensions=_dims(dst), approved_final_release=False)
        (dst.parent / (dst.stem + ".manifest.json")).write_text(json.dumps(rec, indent=1) + "\n")
        records.append(rec)
    c = m["catalog"]
    cat = {"schema_version": "1.0", "catalog_type": "additive_delta", "library_version": m["library_version"], "previous_catalog": c.get("previous"),
           "status": c.get("status"), "approved_final_release": False, "adds": records}
    cf = lib / c["file"]
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(cat, indent=1) + "\n")
    staged = {}
    for p in sorted(lib.rglob("*")):
        if p.is_file():
            staged[p.relative_to(lib).as_posix()] = {"sha256": _sha(p), "bytes": p.stat().st_size}
    idx = lib / f"INDEX.{m['library_version']}.json"
    idx.write_text(json.dumps({"index_version": m["library_version"], "previous_index": m["previous_index"], "delta": True, "status": c.get("status"),
                               "approved_final_release": False, "catalog": c["file"], "files": staged}, indent=1) + "\n")
    return {"staging": str(root), "library": str(lib), "files": len(records), "index": str(idx), "catalog": str(cf),
            "next": "upload the library folder's delta (rclone copy), then list the library and write the next INDEX delta (index_delta) against the baseline"}
