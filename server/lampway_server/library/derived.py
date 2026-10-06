"""Derived files (previews, strips, proxies): the bytes the library itself makes FROM a version, kept under ``<library>/derived/<version_id>/``.

A derived file is a managed blob attached to the version it was made from (``version_file``), so ``get`` lists it beside the source. It never changes the version's
content key: a preview is not the asset. Replacing a role swaps its rows and files in one transaction; deleting ``derived/`` is always safe (everything regenerates)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .store import AssetLibrary, LibraryError


def derived_dir(lib: AssetLibrary, version_id: str) -> Path:
    return lib.root / "derived" / version_id


def replace(lib: AssetLibrary, version_id: str, role: str, items: list) -> list:
    """Make ``items`` ([(file name, bytes)], ord = position) the version's files for ``role``. Returns their paths. The previous files of that role are unlinked when no
    longer written."""
    d = derived_dir(lib, version_id)
    d.mkdir(parents=True, exist_ok=True)
    new = []
    for name, data in items:
        if "/" in name or name.startswith("."):
            raise LibraryError(f"bad derived file name {name!r}")
        p = d / name
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        new.append((str(p), hashlib.sha256(data).hexdigest(), len(data)))
    with lib.tx() as db:
        old = [r[0] for r in db.execute("SELECT l.path FROM version_file f JOIN location l ON l.sha256=f.sha256 WHERE f.version_id=? AND f.role=? AND l.path LIKE ?",
                                        (version_id, role, str(d) + "/%"))]
        old_shas = [r[0] for r in db.execute("SELECT sha256 FROM version_file WHERE version_id=? AND role=?", (version_id, role))]
        db.execute("DELETE FROM version_file WHERE version_id=? AND role=?", (version_id, role))
        for path in old:
            db.execute("DELETE FROM location WHERE path=?", (path,))
        now = lib._now()
        for ord_, (path, sha, n) in enumerate(new):
            db.execute("DELETE FROM location WHERE path=?", (path,))                          # the path now holds these bytes, whatever it held before
            db.execute("INSERT OR IGNORE INTO blob(sha256,bytes,mime,cas_path,first_seen) VALUES(?,?,?,?,?)", (sha, n, _mime(path), path, now))
            db.execute("INSERT INTO location(sha256,path,storage,mtime,size,last_verified,missing) VALUES(?,?,'cas',?,?,?,0)", (sha, path, os.path.getmtime(path), n, now))
            db.execute("INSERT INTO version_file(version_id,role,ord,sha256) VALUES(?,?,?,?)", (version_id, role, ord_, sha))
        for sha in set(old_shas):
            if not db.execute("SELECT 1 FROM location WHERE sha256=? UNION SELECT 1 FROM version_file WHERE sha256=?", (sha, sha)).fetchone():
                db.execute("DELETE FROM blob WHERE sha256=?", (sha,))
        lib._event("derived", None, {"version": version_id, "role": role, "files": len(new)})
    keep = {p for p, _, _ in new}
    for path in old:
        if path not in keep and os.path.exists(path):
            os.unlink(path)
    return [p for p, _, _ in new]


def set_attr(lib: AssetLibrary, version_id: str, key: str, sub: str, value) -> None:
    """``attrs_json[key][sub] = value`` on the version (``render_recipe.thumb = <hash>``)."""
    with lib.tx() as db:
        row = db.execute("SELECT attrs_json FROM version WHERE id=?", (version_id,)).fetchone()
        if not row:
            raise LibraryError(f"no version {version_id}")
        attrs = json.loads(row[0] or "{}")
        attrs.setdefault(key, {})[sub] = value
        db.execute("UPDATE version SET attrs_json=? WHERE id=?", (json.dumps(attrs, sort_keys=True), version_id))


def add_tag(lib: AssetLibrary, asset_id: str, tag: str, by: str = "rule") -> None:
    with lib.tx() as db:
        db.execute("INSERT OR IGNORE INTO tag(asset_id,tag,by) VALUES(?,?,?)", (asset_id, tag, by))
        lib._fts_sync(asset_id)


def _mime(path: str):
    return {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".mp4": "video/mp4", ".json": "application/json"}.get(Path(path).suffix.lower())
