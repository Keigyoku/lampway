"""Selective CC0 import (specs/asset_library/asset_seed_cc0.md section 10): ambientCG and Poly Haven, licence recorded per asset, through egress consent. A fake
transport stands in for both sites; the record shapes are the ones the 2026-10-05 probes saved. No live download."""
import hashlib
import io
import itertools
import json
import zipfile

import httpx
import numpy as np
import pytest
from PIL import Image

from lampway_server import egress as EG
from lampway_server.library import cc0 as CC
from lampway_server.library.store import AssetLibrary, LibraryError


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def png_bytes(seed, size=(16, 16)):
    b = io.BytesIO()
    Image.fromarray(np.random.default_rng(seed).integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(b, "PNG")
    return b.getvalue()


def acg_zip(asset, attr, maps=("Color", "NormalGL", "NormalDX", "Roughness", "Displacement")):
    b = io.BytesIO()
    ext = attr.split("-")[1].lower()
    with zipfile.ZipFile(b, "w") as z:
        for i, m in enumerate(maps):
            z.writestr(f"{asset}_{attr}_{m}.{ext}", png_bytes(hash((asset, m)) % 1000))
        z.writestr(f"{asset}.png", png_bytes(5))                              # the site's preview: dropped
        z.writestr(f"{asset}_{attr}.usdc", b"usd")                            # an extra: dropped
    return b.getvalue()


def acg_record(asset="Metal049A", category="Metal", attrs=("1K-JPG", "1K-PNG"), sizes=None, license=None):
    sizes = sizes or {}
    r = {"assetId": asset, "dataType": "Material", "creationMethod": "PBRPhotogrammetry", "displayCategory": category, "tags": ["metal", "plate"], "displayName": asset,
         "shortLink": f"https://ambientcg.com/a/{asset}", "dimensionX": 100, "dimensionY": 100, "dimensionZ": 0,
         "downloadFolders": {"default": {"downloadFiletypeCategories": {"zip": {"downloads": [
             {"downloadLink": f"https://ambientcg.com/get?file={asset}_{a}.zip", "fileName": f"{asset}_{a}.zip", "size": sizes.get(a, len(acg_zip(asset, a))), "attribute": a, "zipContent": []}
             for a in attrs]}}}},
         "previewImage": {"256-PNG": f"https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/256-PNG/{asset}.png"}}
    if license:
        r["license"] = license
    return r


PH_FILES = {"Diffuse": "color", "nor_gl": "normal_gl", "nor_dx": "normal_dx", "Rough": "roughness", "AO": "ao", "Displacement": "displacement", "arm": "arm"}


class Sites:
    """Both sites in one fake: records every request and the time it arrived."""

    def __init__(self, records=None, ph_assets=None, corrupt=(), drop_range=False, crc=()):
        self.records = records if records is not None else [acg_record()]
        self.ph_assets = ph_assets if ph_assets is not None else {"metal_plate_02": {"name": "Metal Plate 02", "categories": ["metal"], "tags": ["plate"], "dimensions": [2000, 2000], "authors": {"Someone": "All"}}}
        self.reqs, self.corrupt, self.drop_range, self.crc = [], set(corrupt), drop_range, set(crc)
        self.served = {}

    def ph_body(self, asset, key, res, fmt):
        return png_bytes(hash((asset, key, res, fmt)) % 1000)

    def ph_files(self, asset):
        out = {}
        for key in PH_FILES:
            out[key] = {"1k": {}}
            for fmt in ("jpg", "png"):
                body = self.ph_body(asset, key, "1k", fmt)
                out[key]["1k"][fmt] = {"size": len(body), "md5": hashlib.md5(body).hexdigest(), "url": f"https://dl.polyhaven.org/file/ph-assets/Textures/{fmt}/1k/{asset}/{asset}_{key}_1k.{fmt}"}
        return out

    def __call__(self, req: httpx.Request):
        self.reqs.append(req)
        u = req.url
        if u.host == "ambientcg.com" and u.path == "/api/v2/full_json":
            off, lim = int(u.params.get("offset", 0)), int(u.params.get("limit", 100))
            cat = u.params.get("category")
            rows = [r for r in self.records if not cat or r["displayCategory"] == cat]
            return httpx.Response(200, json={"numberOfResults": len(rows), "foundAssets": rows[off:off + lim], "nextPageHttp": None})
        if u.host == "ambientcg.com" and u.path == "/get":
            name = u.params["file"]
            asset, attr = name[:-4].rsplit("_", 1)
            body = acg_zip(asset, attr)
            if name in self.corrupt:
                body = body[:-40] + b"\0" * 40                                  # the central directory gone: not a zip at all
            self.served[name] = body
            if name in self.crc:
                body = body[:80] + bytes([body[80] ^ 0xFF]) + body[81:]        # one byte of the first member's data: the directory is intact, the CRC is not
            rng = req.headers.get("range")
            if rng and not self.drop_range:
                start = int(rng.split("=")[1].split("-")[0])
                return httpx.Response(206, content=body[start:])
            return httpx.Response(200, content=body)
        if u.host == "api.polyhaven.com" and u.path == "/assets":
            return httpx.Response(200, json=self.ph_assets)
        if u.host == "api.polyhaven.com" and u.path.startswith("/files/"):
            return httpx.Response(200, json=self.ph_files(u.path.rsplit("/", 1)[1]))
        if u.host == "dl.polyhaven.org":
            parts = u.path.split("/")
            fmt, res, asset = parts[4], parts[5], parts[6]
            key = parts[7][len(asset) + 1:].rsplit("_", 1)[0]
            body = self.ph_body(asset, key, res, fmt)
            if u.path in self.corrupt:
                body = body[:-1] + b"X"
            return httpx.Response(200, content=body)
        return httpx.Response(404)


def cc(tmp_path, sites, **kw):
    lib = make_lib(tmp_path)
    kw.setdefault("sleep", lambda s: None)
    return lib, CC.CC0(lib, transport=httpx.MockTransport(sites), **kw)


# 1 / 2 ------------------------------------------------------------------------------------------------------------------------------
def test_plan_makes_no_download_requests(tmp_path):
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    plan = c.plan("ambientcg", {"type": "material", "categories": ["Metal"]}, resolution="1k", fmt="png")
    assert plan["selected"] == 1 and plan["licence"] == "CC0-1.0" and plan["bytes_estimate"] > 0 and "ambientcg.com" in plan["network_hosts"]
    assert all(r.url.path == "/api/v2/full_json" for r in sites.reqs)


def test_agent_fetch_is_refused_with_the_plan(tmp_path):
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    plan = c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")
    n = len(sites.reqs)
    with pytest.raises(LibraryError, match=r"downloads need the captain's click in the Library panel \(disk and network\): here is the plan .* \(1 assets, "):
        c.fetch(plan["plan_id"], by="agent")
    assert len(sites.reqs) == n


# 3 -------------------------------------------------------------------------------------------------------------------------------
def test_ambientcg_record_maps_to_asset_with_licence_cc0_and_source_key(tmp_path):
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    out = c.fetch(c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")
    assert out["fetched"] == 1 and out["failed"] == [] and out["verified"] == 1
    served = sites.served["Metal049A_1K-PNG.zip"]
    sid = lib.resolve_asset(out["assets"]["Metal049A"])
    a = lib.get(sid)
    assert (a["kind"], a["source_key"], a["license_id"]) == ("texture_set", "Metal049A", "CC0-1.0")
    assert a["attrs"]["source_url"] == "https://ambientcg.com/a/Metal049A" and a["attrs"]["api_snapshot_sha256"]
    assert "dimensions_m" not in a["attrs"] and a["attrs"]["dimensions_raw"] == {"x": 100, "y": 100, "unit": None}      # the site's numbers, no unit claimed
    assert a["attrs"]["archive_sha256"] == hashlib.sha256(served).hexdigest()                                          # the raw download's hash
    roles = sorted(f["role"] for f in a["files"])
    assert roles == ["map:color", "map:displacement", "map:normal_dx", "map:normal_gl", "map:roughness"]                 # no preview, no .usdc
    lic = lib._reader().execute("select attribution_required,commercial_ok,redistribute_ok,url from license where id='CC0-1.0'").fetchone()
    assert tuple(lic[:3]) == (0, 1, 1) and lic[3].startswith("https://")
    maps = [r for r in a["relations"] if r["type"] == "part_of" and r["dst"] == sid]
    assert len(maps) == 5
    members = {lib.get(r["src"])["stats"]["channel"]: lib.get(r["src"]) for r in maps}
    assert {ch: m["attrs"]["colorspace"] for ch, m in members.items()} == {"color": "sRGB", "normal_gl": "Non-Color", "normal_dx": "Non-Color", "roughness": "Non-Color", "displacement": "Non-Color"}
    assert a["attrs"]["map_colorspaces"]["color"] == "sRGB" and a["attrs"]["map_colorspaces"]["roughness"] == "Non-Color" and a["stats"]["colorspace"] is None
    assert a["attrs"]["normal_conventions"] == {"normal_gl": "GL", "normal_dx": "DX"} and members["normal_dx"]["stats"]["convention"] == "DX"
    gl = next(lib.get(r["src"]) for r in maps if lib.get(r["src"])["subtype"] == "normal_gl")
    assert gl["stats"]["convention"] == "GL" and gl["stats"]["channel"] == "normal_gl" and gl["license_id"] == "CC0-1.0"      # map_channel (the DDL's columns)
    assert ("material_role", "plate_metal") in {(t["facet"], t["label"]) for t in a["terms"]}


# 4 -------------------------------------------------------------------------------------------------------------------------------
def test_polyhaven_map_selection_downloads_only_requested_maps_and_verifies_md5(tmp_path):
    asset = "metal_plate_02"
    bad = f"/file/ph-assets/Textures/png/1k/{asset}/{asset}_nor_gl_1k.png"
    sites = Sites(corrupt={bad})
    lib, c = cc(tmp_path, sites)
    plan = c.plan("polyhaven", {"type": "textures", "categories": ["metal"]}, maps=["color", "normal_gl", "roughness"])
    out = c.fetch(plan["plan_id"], by="captain")
    got = [r.url.path for r in sites.reqs if r.url.host == "dl.polyhaven.org"]
    assert got and all("_Diffuse_" in p or "_nor_gl_" in p or "_Rough_" in p for p in got)          # never a map nobody asked for (it stops at the bad one)
    assert out["fetched"] == 0 and "md5 mismatch" in out["failed"][0]["why"]
    assert lib._reader().execute("select count(*) from asset").fetchone()[0] == 0                                  # a set with a bad map is not registered


def test_a_clean_polyhaven_set_lands_with_its_maps(tmp_path):
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    out = c.fetch(c.plan("polyhaven", {"categories": ["metal"]}, maps=["color", "normal_gl", "roughness"])["plan_id"], by="captain")
    a = lib.get(out["assets"]["metal_plate_02"])
    got = [r.url.path for r in sites.reqs if r.url.host == "dl.polyhaven.org"]
    assert len(got) == 3 and all("_Diffuse_" in p or "_nor_gl_" in p or "_Rough_" in p for p in got)
    assert all(p.endswith(".png") for p in got if "_nor_gl_" in p) and all(p.endswith(".jpg") for p in got if "_nor_gl_" not in p)     # normals as png, the rest jpg
    assert out["fetched"] == 1 and sorted(f["role"] for f in a["files"]) == ["map:color", "map:normal_gl", "map:roughness"] and a["license_id"] == "CC0-1.0"
    assert a["attrs"]["source_url"] == "https://polyhaven.com/a/metal_plate_02"


# 5 / 6 ---------------------------------------------------------------------------------------------------------------------------
def test_zip_size_mismatch_and_testzip_failure_are_rejected(tmp_path):
    rec = acg_record(sizes={"1K-PNG": 12345})
    lib, c = cc(tmp_path, Sites(records=[rec]))
    out = c.fetch(c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")
    assert out["fetched"] == 0 and "size" in out["failed"][0]["why"]
    lib2, c2 = cc(tmp_path / "b", Sites(corrupt={"Metal049A_1K-PNG.zip"}))
    out2 = c2.fetch(c2.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")
    assert out2["fetched"] == 0 and "not a valid zip" in out2["failed"][0]["why"]
    lib3, c3 = cc(tmp_path / "c", Sites(crc={"Metal049A_1K-PNG.zip"}))
    out3 = c3.fetch(c3.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")
    assert out3["fetched"] == 0 and "CRC" in out3["failed"][0]["why"] and lib3._reader().execute("select count(*) from asset").fetchone()[0] == 0


def test_lossy_normal_refused(tmp_path):
    lib, c = cc(tmp_path, Sites())
    with pytest.raises(LibraryError, match="lossy normal maps are refused: use png"):
        c.plan("ambientcg", {"categories": ["Metal"]}, fmt="jpg")                       # an ambientCG zip is whole: a jpg set has jpg normals
    with pytest.raises(LibraryError, match="lossy normal maps are refused: use png"):
        c.plan("polyhaven", {"categories": ["metal"]}, maps=["normal_gl"], normal_format="jpg")
    assert c.plan("ambientcg", {"categories": ["Metal"]}, fmt="jpg", maps=["color", "roughness"])["selected"] == 1
    with pytest.raises(LibraryError, match="8k is 20x the size of 1k: name the assets"):
        c.plan("polyhaven", {"categories": ["metal"]}, resolution="8k")


# 7 -------------------------------------------------------------------------------------------------------------------------------
def test_resume_continues_a_part_file_and_reimport_is_idempotent(tmp_path):
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    plan = c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")
    full = acg_zip("Metal049A", "1K-PNG")
    part = lib.root / "downloads" / "ambientcg" / "Metal049A_1K-PNG.zip.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(full[:1000])
    out = c.fetch(plan["plan_id"], by="captain")
    ranged = [r for r in sites.reqs if r.url.path == "/get"]
    assert out["fetched"] == 1 and ranged[0].headers["range"] == "bytes=1000-"
    again = c.fetch(c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")
    assert again["fetched"] == 0 and again["skipped"] == 1                                # same source_key: nothing new, nothing downloaded
    assert len([r for r in sites.reqs if r.url.path == "/get"]) == 1


# 8 -------------------------------------------------------------------------------------------------------------------------------
def test_non_cc0_licence_is_refused(tmp_path):
    lib, c = cc(tmp_path, Sites(records=[acg_record(license="CC-BY-NC-4.0")]))
    plan = c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")
    assert plan["selected"] == 0 and plan["will_skip"] == [{"id": "Metal049A", "reason": "licence is CC-BY-NC-4.0, not CC0: refused"}]


# 9 -------------------------------------------------------------------------------------------------------------------------------
def test_rate_limit_and_user_agent_are_applied(tmp_path):
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s

    sites = Sites(records=[acg_record(f"Metal{i:03d}") for i in range(3)])
    lib, c = cc(tmp_path, sites, sleep=sleep, clock=lambda: t[0], page=1)
    c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")
    api = [r for r in sites.reqs if r.url.path == "/api/v2/full_json"]
    assert len(api) == 3 and all(r.headers["user-agent"].startswith("Lampway/") for r in sites.reqs)
    assert len(slept) == 2 and all(s >= CC.MIN_INTERVAL_S for s in slept)                 # the second and third calls waited


def test_a_429_honours_retry_after(tmp_path):
    calls = []

    def h(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"})
        return Sites()(req)

    slept = []
    lib = make_lib(tmp_path)
    c = CC.CC0(lib, transport=httpx.MockTransport(h), sleep=slept.append)
    assert c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["selected"] == 1 and 3.0 in slept


# 10 / 11 -------------------------------------------------------------------------------------------------------------------------
def test_map_suffix_table_covers_the_sample_names():
    names = ["Metal049A_1K-PNG_Color.png", "Metal049A_1K-PNG_NormalGL.png", "Metal049A_1K-PNG_NormalDX.png", "Metal049A_1K-PNG_Roughness.png",
             "Metal049A_1K-PNG_Metalness.png", "Metal049A_1K-PNG_AmbientOcclusion.png", "Metal049A_1K-PNG_Displacement.png", "Metal049A.png"]
    assert [CC.acg_channel(n) for n in names] == ["color", "normal_gl", "normal_dx", "roughness", "metalness", "ao", "displacement", None]


def test_with_egress_strict_and_the_route_off_nothing_is_sent(tmp_path):
    m = EG.Egress(tmp_path / "egress")
    EG.set_active(m)
    sites = Sites()
    lib, c = cc(tmp_path, sites)
    with pytest.raises(LibraryError, match="cc0:ambientcg is off"):
        c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")
    assert sites.reqs == []
    m.set_route("cc0:ambientcg", True)
    assert c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["selected"] == 1
    assert EG.ROUTES["cc0:ambientcg"].privacy_class == "ok" and EG.ROUTES["cc0:polyhaven"].privacy_class == "ok"


def test_a_fetched_texture_set_gets_a_map_sheet_with_its_normal_convention_stamped(tmp_path):
    from lampway_server.library import render as R
    lib, c = cc(tmp_path, Sites())
    sid = c.fetch(c.plan("ambientcg", {"categories": ["Metal"]}, fmt="png")["plan_id"], by="captain")["assets"]["Metal049A"]
    rr = R.Renderer(lib, blender=None, loadavg=lambda: (0, 0, 0), live_window_cpu=lambda: 0.0)
    rr.enqueue(sid, ["map_sheet", "thumb"])
    rr.drain()
    st = rr.status(sid)["products"]
    assert st["map_sheet"]["state"] == "done" and st["thumb"]["state"] == "done", st
    assert Image.open(st["map_sheet"]["path"]).size == (4 * 256, 2 * (256 + R.LABEL_H))
