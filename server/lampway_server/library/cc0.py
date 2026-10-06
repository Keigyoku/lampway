"""Selective CC0 import (specs/asset_library/asset_seed_cc0.md): ambientCG materials and Poly Haven textures as ``texture_set`` assets with their ``map`` members,
the licence recorded per asset.

``plan`` makes metadata calls only and names every host it would touch. ``fetch`` is the user's click: zips are size- and testzip-checked, Poly Haven files are
md5-checked, a set with one bad map is not registered, downloads resume from ``.part`` files, and a set already in the Vault is skipped without a request. Every
request passes the ``cc0:ambientcg`` / ``cc0:polyhaven`` egress routes (off until the user opts in), carries a Lampway User-Agent and waits MIN_INTERVAL_S
between calls (a 429's Retry-After is honoured). Record shapes are the ones the 2026-10-05 probes saved; ambientCG's in-zip map names are [UNVERIFIED] (the API
lists ``zipContent: []``) and frozen in ``ACG_SUFFIX`` until a first live fetch confirms them."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Callable

import httpx

from .. import egress as EG
from . import ingest as I
from .store import AssetLibrary, LibraryError

MIN_INTERVAL_S = 0.25
USER_AGENT = "Lampway/0.0.1 (+asset library; CC0 import)"
ACG_API = "https://ambientcg.com/api/v2/full_json"
PH_API = "https://api.polyhaven.com"
CC0_LICENCE = {"id": "CC0-1.0", "name": "Creative Commons CC0 1.0 Universal", "url": "https://creativecommons.org/publicdomain/zero/1.0/"}
LICENCE_PAGES = {"ambientcg": "https://docs.ambientcg.com/license/", "polyhaven": "https://polyhaven.com/license"}
HOSTS = {"ambientcg": ["ambientcg.com"], "polyhaven": ["api.polyhaven.com", "dl.polyhaven.org"]}
ACG_SUFFIX = (("_NormalGL", "normal_gl"), ("_NormalDX", "normal_dx"), ("_Color", "color"), ("_Roughness", "roughness"), ("_Metalness", "metalness"),
              ("_AmbientOcclusion", "ao"), ("_Displacement", "displacement"), ("_Opacity", "opacity"))
PH_KEYS = {"Diffuse": "color", "nor_gl": "normal_gl", "nor_dx": "normal_dx", "Rough": "roughness", "AO": "ao", "Displacement": "displacement", "arm": "arm", "Metal": "metalness"}
NORMALS = {"normal_gl", "normal_dx"}
SUBTYPE = {"color": "basecolor", "normal_gl": "normal_gl", "normal_dx": "normal_dx", "roughness": "roughness", "metalness": "metallic", "ao": "ao", "displacement": "height",
           "arm": "orm", "opacity": "mask"}
ROLE = {"metal": "plate_metal", "metalplates": "plate_metal", "paintedmetal": "plate_metal", "diamondplate": "plate_metal", "corrugatedsteel": "plate_metal",
        "metalwalkway": "plate_metal", "sheetmetal": "plate_metal", "chainmail": "plate_metal", "foil": "plate_metal", "rust": "wear_overlay", "scratches": "wear_overlay",
        "surfaceimperfections": "wear_overlay", "leather": "leather", "fabric": "cloth", "rope": "cloth", "wicker": "cloth", "carpet": "cloth"}


def acg_channel(name: str):
    stem = name.rsplit(".", 1)[0]
    return next((ch for suf, ch in ACG_SUFFIX if stem.endswith(suf)), None)


class CC0:
    def __init__(self, lib: AssetLibrary, transport=None, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic, page: int = 100):
        self.lib, self.transport, self.sleep, self.clock, self.page = lib, transport, sleep, clock, page
        self._last = None
        self.plans = lib.root / "cc0_plans"
        self.downloads = lib.root / "downloads"

    # -- the polite client ------------------------------------------------------------------------------------------------------
    def _get(self, url, route, params=None, headers=None, kind="request"):
        for attempt in range(4):
            if self._last is not None:
                wait = MIN_INTERVAL_S - (self.clock() - self._last)
                if wait > 0:
                    self.sleep(wait)
            try:
                with EG.context(route=route, kind=kind, content_class="public"), httpx.Client(transport=self.transport, timeout=600, follow_redirects=True,
                                                                                              headers={"User-Agent": USER_AGENT}) as c:
                    r = c.get(url, params=params, headers=headers or {})
            except EG.EgressRefused as e:
                raise LibraryError(str(e)) from None
            self._last = self.clock()
            if r.status_code == 429 and attempt < 3:
                self.sleep(float(r.headers.get("retry-after") or 2))
                continue
            return r
        return r

    def _json(self, url, route, params=None):
        r = self._get(url, route, params)
        if r.status_code >= 400:
            raise LibraryError(f"{url} answered HTTP {r.status_code}")
        return r.json()

    # -- plan ---------------------------------------------------------------------------------------------------------------------
    def plan(self, source: str, select: dict, resolution: str = "1k", fmt: str = "jpg", maps=None, normal_format: str = "png", max_assets: int = 400) -> dict:
        if source not in HOSTS:
            raise LibraryError(f"unknown source {source!r}: ambientcg|polyhaven")
        if resolution not in ("1k", "2k", "4k", "8k"):
            raise LibraryError("resolution: 1k|2k|4k|8k")
        if resolution == "8k" and not select.get("ids"):
            raise LibraryError("8k is 20x the size of 1k: name the assets")
        want = set(maps) if maps else None
        wants_normals = want is None or bool(want & NORMALS)
        if wants_normals and ((source == "ambientcg" and fmt == "jpg") or (source == "polyhaven" and normal_format == "jpg")):
            raise LibraryError("lossy normal maps are refused: use png" + (" (an ambientCG zip is whole: its normals come in the zip's format; or leave normals out of maps)" if source == "ambientcg" else ""))
        entries, skip, matched, by_cat = [], [], 0, {}
        for rec in (self._acg_list if source == "ambientcg" else self._ph_list)(select):
            matched += 1
            if select.get("ids") and rec["id"] not in select["ids"]:
                continue
            lic = rec.get("license")
            if lic and lic not in ("CC0", "CC0-1.0", "CC0 1.0"):
                skip.append({"id": rec["id"], "reason": f"licence is {lic}, not CC0: refused"})
                continue
            item = self._acg_item(rec, resolution, fmt) if source == "ambientcg" else self._ph_item(rec, resolution, fmt, normal_format, want)
            if isinstance(item, str):
                skip.append({"id": rec["id"], "reason": item})
                continue
            if len(entries) >= int(max_assets):
                skip.append({"id": rec["id"], "reason": f"max_assets {max_assets} reached"})
                continue
            entries.append({**item, "maps": sorted(want) if want else None})
            by_cat[rec["category"]] = by_cat.get(rec["category"], 0) + 1
        total = sum(e["bytes"] for e in entries)
        pid = "cc0-" + hashlib.sha1(json.dumps([source, entries], sort_keys=True).encode()).hexdigest()[:10]
        plan = {"ok": True, "plan_id": pid, "source": source, "matched": matched, "selected": len(entries), "bytes_estimate": total, "by_category": by_cat,
                "licence": CC0_LICENCE["id"], "sample": [{"id": e["id"], "name": e["name"], "thumb": e.get("thumb")} for e in entries[:6]], "will_skip": skip,
                "network_hosts": HOSTS[source], "resolution": resolution}
        self.plans.mkdir(parents=True, exist_ok=True)
        (self.plans / f"{pid}.json").write_text(json.dumps({**plan, "entries": entries}))
        return plan

    def _acg_list(self, select):
        for cat in select.get("categories") or [None]:
            off = 0
            for _ in range(10000):                                    # bounded paging
                doc = self._json(ACG_API, "cc0:ambientcg", {"type": select.get("type") or "material", **({"category": cat} if cat else {}), "sort": "popular",
                                                            "limit": self.page, "offset": off, "include": "statisticsData,labelData,previewData,technicalData,fileData"})
                if "foundAssets" not in doc or "numberOfResults" not in doc:
                    raise LibraryError("ambientCG API changed shape: expected numberOfResults/foundAssets")
                for r in doc["foundAssets"]:
                    yield {**r, "id": r["assetId"], "category": r.get("displayCategory") or cat or "", "license": r.get("license") or r.get("licence")}
                off += len(doc["foundAssets"])
                if not doc["foundAssets"] or off >= doc["numberOfResults"]:
                    break

    def _ph_list(self, select):
        for cat in select.get("categories") or [None]:
            doc = self._json(f"{PH_API}/assets", "cc0:polyhaven", {"t": select.get("type") or "textures", **({"c": cat} if cat else {})})
            for aid, r in sorted(doc.items()):
                yield {**r, "id": aid, "category": cat or (r.get("categories") or [""])[0], "license": r.get("license")}

    @staticmethod
    def _acg_item(rec, resolution, fmt):
        attr = f"{resolution.upper()}-{fmt.upper()}"
        dls = (((rec.get("downloadFolders") or {}).get("default") or {}).get("downloadFiletypeCategories") or {}).get("zip", {}).get("downloads", [])
        dl = next((d for d in dls if d.get("attribute") == attr), None)
        if not dl:
            return f"no {attr} download"
        return {"id": rec["id"], "name": rec.get("displayName") or rec["id"], "category": rec["category"], "bytes": int(dl["size"]), "files": [{"url": dl["downloadLink"], "name": dl["fileName"], "size": int(dl["size"])}],
                "thumb": (rec.get("previewImage") or {}).get("256-PNG"), "source_url": rec.get("shortLink"), "tags": rec.get("tags") or [],
                "dimensions_m": [rec["dimensionX"] / 100.0, rec["dimensionY"] / 100.0] if rec.get("dimensionX") else None, "creation_method": rec.get("creationMethod"),
                "snapshot": hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest(), "attribution": f"Created using {rec.get('displayName') or rec['id']} from ambientCG.com, licensed under the Creative Commons CC0 1.0 Universal License."}

    def _ph_item(self, rec, resolution, fmt, normal_format, want):
        files_doc = self._json(f"{PH_API}/files/{rec['id']}", "cc0:polyhaven")
        files = []
        for key, ch in PH_KEYS.items():
            if key not in files_doc or (want is not None and ch not in want) or (want is None and ch == "arm"):
                continue
            f = (files_doc[key].get(resolution) or {}).get(normal_format if ch in NORMALS else fmt)
            if f:
                files.append({"url": f["url"], "name": f["url"].rsplit("/", 1)[-1], "size": int(f["size"]), "md5": f["md5"], "channel": ch})
        if not files:
            return f"no maps at {resolution}"
        authors = ", ".join(sorted((rec.get("authors") or {}).keys()))
        return {"id": rec["id"], "name": rec.get("name") or rec["id"], "category": rec["category"], "bytes": sum(f["size"] for f in files), "files": files,
                "thumb": rec.get("thumbnail_url"), "source_url": f"https://polyhaven.com/a/{rec['id']}", "tags": rec.get("tags") or [],
                "dimensions_m": [d / 1000.0 for d in rec["dimensions"]] if rec.get("dimensions") else None, "creation_method": None,
                "snapshot": hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest(), "attribution": f"{rec.get('name') or rec['id']} by {authors or 'Poly Haven'}, polyhaven.com (CC0)"}

    # -- fetch ----------------------------------------------------------------------------------------------------------------------
    def fetch(self, plan_id: str, by: str) -> dict:
        f = self.plans / f"{plan_id}.json"
        if not f.exists():
            raise LibraryError(f"no plan {plan_id}: plan first")
        plan = json.loads(f.read_text())
        if by not in I.USER:
            raise LibraryError(f"downloads need the captain's click in the Library panel (disk and network): here is the plan {plan_id} "
                               f"({plan['selected']} assets, {plan['bytes_estimate'] / 1024 ** 3:.2f} GB)")
        free = shutil.disk_usage(self.lib.root).free
        if free < 1.5 * plan["bytes_estimate"]:
            raise LibraryError(f"need {1.5 * plan['bytes_estimate'] / 1024 ** 3:.1f} GB free, have {free / 1024 ** 3:.1f}")
        src = plan["source"]
        out = {"ok": True, "plan_id": plan_id, "batch_id": plan_id, "fetched": 0, "skipped": 0, "failed": [], "bytes": 0, "verified": 0, "assets": {}}
        for e in plan["entries"]:
            have = self.lib._reader().execute("SELECT a.id FROM asset a JOIN source s ON s.id=a.source_id WHERE s.kind=? AND a.source_key=? AND a.status='active'",
                                              (f"cc0:{src}", e["id"])).fetchone()
            if have:
                out["skipped"] += 1
                out["assets"][e["id"]] = have[0]
                continue
            try:
                maps, n = self._acg_maps(e) if src == "ambientcg" else self._ph_maps(e)
            except LibraryError as err:
                out["failed"].append({"id": e["id"], "why": str(err)})
                continue
            out["bytes"] += n
            out["verified"] += 1
            out["assets"][e["id"]] = self._register(src, e, maps, plan_id)
            out["fetched"] += 1
        return out

    def _download(self, url, dest: Path, route) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        r = self._get(url, route, headers={"Range": f"bytes={have}-"} if have else None, kind="file")
        if r.status_code >= 400:
            raise LibraryError(f"download of {dest.name} answered HTTP {r.status_code}")
        with open(part, "ab" if r.status_code == 206 and have else "wb") as fh:
            fh.write(r.content)
        part.replace(dest)
        return dest.stat().st_size

    def _acg_maps(self, e):
        f = e["files"][0]
        z = self.downloads / "ambientcg" / f["name"]
        n = self._download(f["url"], z, "cc0:ambientcg")
        try:
            if n != f["size"]:
                raise LibraryError(f"size {n} is not the API's {f['size']}: rejected")
            try:
                with zipfile.ZipFile(z) as zf:
                    bad = zf.testzip()
                    if bad:
                        raise LibraryError(f"zip failed its CRC check at {bad}: rejected")
                    maps = {}
                    for name in zf.namelist():
                        ch = acg_channel(name)
                        if ch and (not e.get("maps") or ch in e["maps"]):
                            maps[ch] = (name, zf.read(name))
            except zipfile.BadZipFile as err:
                raise LibraryError(f"not a valid zip: {err}") from None
        finally:
            z.unlink(missing_ok=True)
        if not maps:
            raise LibraryError("the zip held no recognised map")
        return maps, n

    def _ph_maps(self, e):
        maps, n = {}, 0
        for f in e["files"]:
            r = self._get(f["url"], "cc0:polyhaven", kind="file")
            if r.status_code >= 400:
                raise LibraryError(f"download of {f['name']} answered HTTP {r.status_code}")
            if hashlib.md5(r.content).hexdigest() != f["md5"]:
                raise LibraryError(f"md5 mismatch for {f['name']}: the set is not registered")
            maps[f["channel"]] = (f["name"], r.content)
            n += len(r.content)
        return maps, n

    def _register(self, src, e, maps: dict, batch: str) -> str:
        role = ROLE.get(str(e["category"]).lower().replace(" ", ""))
        terms = ([{"facet": "material_role", "label": role}] if role else []) + [{"facet": "license", "label": "cc0"}]
        attrs = {"source_url": e["source_url"], "dimensions_m": e["dimensions_m"], "creation_method": e["creation_method"], "api_snapshot_sha256": e["snapshot"],
                 "licence_text": "CC0 1.0 Universal (stated site-wide)", "licence_page": LICENCE_PAGES[src], "fetched_at": time.time(), "category": e["category"]}
        source = {"kind": f"cc0:{src}", "root": HOSTS[src][0], "label": src}
        with self.lib.bulk():
            sid = self.lib.put({"kind": "texture_set", "name": e["name"], "license": CC0_LICENCE["id"], "attribution": e["attribution"], "source": {**source, "key": e["id"]},
                                "files": [{"role": f"map:{ch}", "bytes": data, "storage": "cas", "name": name} for ch, (name, data) in sorted(maps.items())],
                                "stats": {"maps_json": sorted(maps), "colorspace": "sRGB"}, "attrs": attrs, "terms": terms, "tags": list(e["tags"])[:12], "batch": batch})["id"]
            for ch, (name, data) in sorted(maps.items()):
                st = I.extract_image(io.BytesIO(data))["stats"]
                self.lib.put({"kind": "map", "subtype": SUBTYPE.get(ch), "name": f"{e['name']} {ch}", "license": CC0_LICENCE["id"], "attribution": e["attribution"],
                              "source": {**source, "key": f"{e['id']}:{ch}"}, "files": [{"role": "main", "bytes": data, "storage": "cas", "name": name}],
                              "stats": {"channel": ch, "convention": "GL" if ch == "normal_gl" else "DX" if ch == "normal_dx" else None, "bit_depth": st.get("bit_depth")},
                              "attrs": {"width": st.get("width"), "height": st.get("height")}, "terms": terms, "batch": batch,
                              "relations": [{"type": "part_of", "to": sid, "role": f"map:{ch}"}]})
        with self.lib.tx() as db:
            db.execute("UPDATE license SET name=?,url=?,attribution_required=0,commercial_ok=1,redistribute_ok=1 WHERE id=?", (CC0_LICENCE["name"], CC0_LICENCE["url"], CC0_LICENCE["id"]))
        return sid

