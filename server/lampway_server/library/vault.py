"""The server's one handle on the Asset Vault: the library opened once per process (the store allows ONE writer, so every route, agent tool, MCP call and hook shares this),
lazily on first use and closed with the app. It also holds what the REST routes and the agent tools share: the compact record the agents read, the members of a set, the
``placed`` event."""
from __future__ import annotations

import os
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional

from . import curate as CU
from . import embed as EM
from . import query as Q
from .ingest import Ingest
from .store import AssetLibrary, LibraryError

SET_KINDS = ("texture_set", "material")
PICTURE_KINDS = ("image", "hdri", "map")


class Vault:
    def __init__(self, state_dir, project_root: Optional[Path] = None):
        self.root = Path(state_dir) / "library"
        self._project_root = project_root
        self._lib: Optional[AssetLibrary] = None
        self._ingest: Optional[Ingest] = None
        self._embed: Optional[EM.Embed] = None
        self._lock = threading.Lock()

    @classmethod
    def open(cls, state_dir, project_root: Optional[Path] = None) -> "Vault":
        return cls(state_dir, project_root)

    @property
    def spool(self) -> Path:
        """Where provenance payloads wait while the library cannot take them (``provenance.capture``/``replay_spool``)."""
        return self.root / "spool"

    @property
    def project_root(self) -> Path:
        return Path(self._project_root or os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects")

    @property
    def lib(self) -> AssetLibrary:
        with self._lock:
            if self._lib is None:
                self._lib = AssetLibrary(self.root)
            return self._lib

    @property
    def ingest(self) -> Ingest:
        lib = self.lib
        with self._lock:
            if self._ingest is None:
                self._ingest = Ingest(lib)
            return self._ingest

    @property
    def embed(self) -> EM.Embed:
        """The embedding service with NO OpenRouter client: the deterministic and bundled spaces run; an uploading space is refused until the user's settings supply a key."""
        lib = self.lib
        with self._lock:
            if self._embed is None:
                self._embed = EM.Embed(lib)
            return self._embed

    def close(self) -> None:
        with self._lock:
            if self._lib is not None:
                self._lib.close()
            self._lib, self._ingest, self._embed = None, None, None

    # ---- reads
    def query(self, q: dict) -> dict:
        """A page of ``asset_query``; a tile whose asset is itself a picture carries that picture's path as its thumbnail (rendered thumbnails are asset_render's)."""
        res = Q.query(self.lib, q)
        pics = [it for it in res["items"] if it.get("thumb") is None and it["kind"] in PICTURE_KINDS]
        if pics:
            with closing(self.lib._reader()) as db:
                for it in pics:
                    row = db.execute("SELECT l.path FROM version v JOIN version_file f ON f.version_id=v.id AND f.role='main' JOIN location l ON l.sha256=f.sha256 AND l.missing=0 "
                                     "WHERE v.asset_id=? AND v.n=? ORDER BY l.storage='cas' DESC, l.path LIMIT 1", (it["id"], it["version"])).fetchone()
                    it["thumb"] = row[0] if row else None
        return res

    def get(self, asset_id: str, version: Optional[int] = None) -> dict:
        return self.lib.get(asset_id, version)

    def members(self, asset_id: str) -> list:
        """The maps a texture set (or a PBR-set material) groups: every asset ``part_of`` it."""
        rec = self.lib.get(asset_id)
        return [self.lib.get(r["src"]) for r in rec["relations"] if r["type"] == "part_of" and r["dst"] == asset_id]

    def get_record(self, asset_id: str, version: Optional[int] = None, include=()) -> dict:
        rec = self.lib.get(asset_id, version)
        if "members" in include and rec["kind"] in SET_KINDS:
            rec["members"] = self.members(asset_id)
        return rec

    def file_path(self, sha256: str) -> Path:
        """A readable copy of a blob (managed first, then any referenced location that is present)."""
        with closing(self.lib._reader()) as db:
            rows = db.execute("SELECT path,storage FROM location WHERE sha256=? AND missing=0 ORDER BY storage='cas' DESC, path", (sha256,)).fetchall()
        for path, _storage in rows:
            if Path(path).is_file():
                return Path(path)
        raise LibraryError(f"no copy of {sha256} is on disk: re-run lampway_asset_library verify")

    # ---- writes
    def rate(self, asset_id: str, rater: str, origin: str = "user", **kw) -> dict:
        return CU.rate(self.lib, asset_id, rater, origin=origin, **kw)

    def record_event(self, verb: str, asset_id: str, detail: dict, actor: str) -> dict:
        if verb not in ("placed",):
            raise LibraryError(f"unknown event {verb!r}; events: placed")
        if self.lib.resolve_asset(asset_id) != asset_id:
            raise LibraryError(f"no asset {asset_id}")
        with self.lib.tx():
            self.lib._event(verb, asset_id, detail, actor=actor)
        return {"recorded": True}
