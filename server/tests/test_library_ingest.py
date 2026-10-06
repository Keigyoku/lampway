"""Asset Vault ingest (specs/asset_library/asset_ingest.md section 10): scan -> preview -> user-confirmed import, tier-1 extractors, rules, watch."""
import hashlib
import itertools
import json
import struct

import pytest
from PIL import Image

from lampway_server.library import ingest as I
from lampway_server.library.store import AssetLibrary, LibraryError


def glb_bytes(positions, indices=None, materials=1, skin=False, uv=True, extra_prims=()):
    """A minimal valid GLB: one mesh, one primitive over ``positions`` (list of xyz), optional index list."""
    bin_ = b"".join(struct.pack("<3f", *p) for p in positions)
    accessors = [{"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
                  "min": [min(p[i] for p in positions) for i in range(3)], "max": [max(p[i] for p in positions) for i in range(3)]}] if positions else \
                [{"componentType": 5126, "count": 0, "type": "VEC3"}]
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(bin_)}]
    attrs = {"POSITION": 0}
    if uv:
        attrs["TEXCOORD_0"] = 0
    prim = {"attributes": attrs, "mode": 4}
    if indices is not None:
        off = len(bin_)
        bin_ += struct.pack(f"<{len(indices)}H", *indices)
        bin_ += b"\0" * (-len(bin_) % 4)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(indices) * 2})
        accessors.append({"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"})
        prim["indices"] = 1
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [prim, *extra_prims]}], "accessors": accessors, "bufferViews": views,
           "buffers": [{"byteLength": len(bin_)}], "materials": [{} for _ in range(materials)]}
    if skin:
        doc["skins"] = [{"joints": [0, 1, 2]}]
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


QUAD = [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 1)]


def png(path, size=(16, 12), color=(200, 100, 50)):
    Image.new("RGB", size, color).save(path)


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


@pytest.fixture
def tree(tmp_path):
    r = tmp_path / "Downloads" / "TripoAssets"
    r.mkdir(parents=True)
    (r / "lowpolysmartmeshgreaves.glb").write_bytes(glb_bytes(QUAD, [0, 1, 2, 0, 2, 3]))
    png(r / "Front.png")
    (r / "notes.pyc").write_bytes(b"\0\1\2")
    (r / "tool.py").write_text("print(1)")
    (r / "weird.bin").write_bytes(b"\x01\x02\x03\x04\x05\x06\x07\x08\x09")
    (r / "empty.glb").write_bytes(b"")
    (r / "pack.zip").write_bytes(b"PK\x03\x04zipbytes")
    (r / "rig.fbx").write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00" + b"x" * 40)
    return r


def snapshot(root):
    return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob("*") if p.is_file()}


def test_scan_is_read_only_and_writes_nothing_but_the_scan_file(tree, tmp_path):
    lib = make_lib(tmp_path)
    before = snapshot(tree)
    out = I.Ingest(lib).scan([tree])
    assert snapshot(tree) == before
    assert lib.status()["assets"]["total"] == 0 and lib.status()["blobs"] == 0
    assert (tmp_path / "lib" / "scans" / f"{out['scan_id']}.json").exists()
    assert not lib._db.execute("select count(*) from source").fetchone()[0]       # nothing is enrolled by a scan


def test_scan_report_counts_unknowns_ignores_failures_and_archives(tree, tmp_path):
    rep = I.Ingest(make_lib(tmp_path)).scan([tree])["report"]
    assert rep["by_kind"] == {"mesh": 2, "image": 1}                                 # glb + fbx, png
    assert {s["path"].rsplit("/", 1)[1] for s in rep["skipped"]} >= {"notes.pyc", "tool.py"}
    assert [u["magic"] for u in rep["unknown"]] == ["0102030405060708"] and rep["unknown"][0]["path"].endswith("weird.bin")
    assert [f["path"].rsplit("/", 1)[1] for f in rep["failed"]] == ["empty.glb"]
    assert [a.rsplit("/", 1)[1] for a in rep["archives"]] == ["pack.zip"]


def test_import_needs_the_users_click_and_imports_exactly_what_was_previewed(tree, tmp_path):
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    scan = ing.scan([tree])
    with pytest.raises(LibraryError, match="user's click"):
        ing.import_(scan["scan_id"], by="agent")
    (tree / "late.png").write_bytes(b"")                       # appears after the preview
    png(tree / "late.png")
    res = ing.import_(scan["scan_id"], by="captain")
    assert res["report"]["new_assets"] == 3 and lib.status()["assets"]["by_kind"] == {"image": 1, "mesh": 2}
    assert all(not str(f).endswith("late.png") for f in [loc["path"] for a in lib._db.execute("select id from asset") for loc in lib.get(a[0])["files"][0]["locations"]])


def test_reimport_is_idempotent_and_sources_stay_untouched(tree, tmp_path):
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    before = snapshot(tree)
    first = ing.import_(ing.scan([tree])["scan_id"], by="captain")["report"]
    second = ing.import_(ing.scan([tree])["scan_id"], by="captain")["report"]
    assert first["new_assets"] == 3 and second["new_assets"] == 0 and second["new_versions"] == 0
    assert snapshot(tree) == before


def test_glb_stats_come_from_the_file(tree, tmp_path):
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    ing.import_(ing.scan([tree])["scan_id"], by="captain")
    a = next(lib.get(r[0]) for r in lib._db.execute("select id from asset where name like '%greaves%'"))
    st = a["stats"]
    assert (st["verts"], st["faces"], st["tris"], st["topology"], st["materials"], st["uv_sets"], st["skinned"]) == (4, 2, 2, "Tri", 1, 1, 0)
    assert (st["dim_x"], st["dim_y"], st["dim_z"]) == (2.0, 3.0, 1.0) and json.loads(st["bbox_max_json"]) == [2.0, 3.0, 1.0]


def test_glb_degenerate_primitive_is_counted_not_trusted(tmp_path):
    extra = ({"attributes": {}, "mode": 4},)
    st = I.extract_glb(glb_bytes(QUAD, [0, 1, 2], extra_prims=extra))
    assert st["stats"]["tris"] == 1 and st["attrs"]["degenerate_primitives"] == 1


def test_glb_skin_and_no_uv(tmp_path):
    st = I.extract_glb(glb_bytes(QUAD, [0, 1, 2], skin=True, uv=False))["stats"]
    assert st["skinned"] == 1 and st["bones"] == 3 and st["uv_sets"] == 0


def test_a_tier2_file_is_recorded_with_stats_pending(tree, tmp_path):
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    ing.import_(ing.scan([tree])["scan_id"], by="captain")
    fbx = next(lib.get(r[0]) for r in lib._db.execute("select id from asset where name like 'rig%'"))
    assert fbx["attrs"]["extract"].startswith("pending")


def test_image_stats_and_dhash_are_deterministic(tmp_path):
    p = tmp_path / "a.png"
    png(p, (32, 24))
    a, b = I.extract_image(p), I.extract_image(p)
    assert a == b and a["stats"]["width"] == 32 and a["stats"]["height"] == 24 and len(a["stats"]["dhash"]) == 16 and a["stats"]["has_alpha"] == 0


def test_unknown_magic_is_never_guessed():
    assert I.classify(b"\x01\x02\x03\x04\x05\x06\x07\x08", "weird.bin") is None
    assert I.classify(b"glTF\x02\0\0\0", "x.dat")["kind"] == "mesh"           # magic beats the extension
    assert I.classify(b"\x89PNG\r\n\x1a\n", "x.glb")["kind"] == "image"


def test_ignore_list_skips_code_and_caches(tmp_path):
    r = tmp_path / "Assets"
    (r / "GameRigTools" / "__pycache__").mkdir(parents=True)
    for n in ("a.pyc", "b.py", "c.so", "d.dll", "e.blend1", "f.tmp", "GameRigTools/__pycache__/g.pyc"):
        (r / n).write_bytes(b"")
    png(r / "keep.png")
    rep = I.Ingest(make_lib(tmp_path)).scan([r])["report"]
    assert rep["seen"] == 1 and rep["by_kind"] == {"image": 1} and len(rep["skipped"]) == 6
    assert not any("__pycache__" in x["path"] for x in rep["skipped"])        # an ignored directory is never listed into


RULE_TABLE = [
    ("Downloads/TripoAssets/lowpolysmartmeshgreaves.glb", "mesh", {"piece_type:greaves", "studio:tripo", "topology:smart_low", "pipeline_stage:retopo"}),
    ("Downloads/Hi3DAssets/Gauntlets.glb", "mesh", {"piece_type:gauntlets", "studio:hi3d"}),
    ("Downloads/MeshyAssets/ChestSegmented.glb", "mesh", {"piece_type:chest", "studio:meshy", "pipeline_stage:segmented"}),
    ("Downloads/Hi3DAssets/FittedWarriorSegmentedTextured.glb", "mesh", {"studio:hi3d", "pipeline_stage:segmented"}),
    ("Pictures/TitanAssets/greek-armor-turnarounds-transparent-v3/Helmet1/Front.png", "image", {"piece_type:helmet", "view:front", "authority:appearance"}),
    ("Pictures/TitanAssets/greek-armor-turnarounds-transparent-v3/Waist1/Bottom.png", "image", {"piece_type:waist", "view:bottom", "authority:appearance"}),
    ("Downloads/Armor Motion Videos/B-ANKLE-ROCK.mp4", "video", {"piece_type:boots", "motion_type:ankle-rock"}),
    ("Downloads/Armor Motion Videos/C-CLOTH-SHIFT.mp4", "video", {"piece_type:chest", "motion_type:cloth-shift"}),
    ("Downloads/Armor Motion Videos/G-L-GRIP.mp4", "video", {"piece_type:gauntlets", "motion_type:l-grip"}),
    ("Downloads/Armor Motion Videos/H-TURN-NOD.mp4", "video", {"piece_type:helmet", "motion_type:turn-nod"}),
    ("Downloads/Armor Motion Videos/W-REAR-TURN.mp4", "video", {"piece_type:waist", "motion_type:rear-turn"}),
    ("Downloads/Armor Motion Videos/W-FRONT-SHIFT.mp4", "video", {"piece_type:waist", "motion_type:front-shift"}),
    ("Downloads/TripoAssets/Boots1.glb", "mesh", {"piece_type:boots", "studio:tripo"}),
]


@pytest.mark.parametrize("path,kind,expected", RULE_TABLE)
def test_rules_map_observed_filenames_to_terms(path, kind, expected):
    got = {f"{t['facet']}:{t['label']}" for t in I.rule_terms(path, kind)}
    assert expected <= got, (expected - got, got)


def test_a_video_motion_name_never_becomes_a_view():
    got = {f"{t['facet']}:{t['label']}" for t in I.rule_terms("Downloads/Armor Motion Videos/W-FRONT-SHIFT.mp4", "video")}
    assert not any(t.startswith("view:") for t in got)


def test_stats_rules_add_lod_rigged_and_needs_uv():
    got = {f"{t['facet']}:{t['label']}" for t in I.stats_terms("mesh", {"faces": 4000, "skinned": 1, "uv_sets": 0})}
    assert got == {"lod:low", "state:rigged", "state:needs_uv"}
    assert I.stats_terms("mesh", {"faces": 90000, "skinned": 0, "uv_sets": 1}) == []


def test_verification_json_hash_mismatch_is_a_finding_not_silence(tmp_path):
    r = tmp_path / "Armor Motion Videos"
    r.mkdir()
    good, bad = r / "B-ANKLE-ROCK.mp4", r / "C-ARM-LIFT.mp4"
    good.write_bytes(b"\0\0\0\x18ftypmp42" + b"a" * 20)
    bad.write_bytes(b"\0\0\0\x18ftypmp42" + b"b" * 20)
    (r / "verification.json").write_text(json.dumps({"files": [
        {"file": good.name, "sha256": hashlib.sha256(good.read_bytes()).hexdigest()},
        {"file": bad.name, "sha256": hashlib.sha256(b"different").hexdigest()}]}))
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    rep = ing.import_(ing.scan([r])["scan_id"], by="captain")["report"]
    assert [f["file"] for f in rep["findings"] if f["what"] == "verification_hash_mismatch"] == ["C-ARM-LIFT.mp4"]


def test_watch_debounces_a_growing_file_and_marks_removals_missing(tmp_path):
    root = tmp_path / "watched"
    root.mkdir()
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    ing.watch_add(root, by="captain")
    w = I.Watcher(ing, root)
    f = root / "grow.glb"
    f.write_bytes(glb_bytes(QUAD, [0, 1, 2])[:40])
    assert w.poll() == []                                    # first sighting
    f.write_bytes(glb_bytes(QUAD, [0, 1, 2])[:60])
    assert w.poll() == [] and lib.status()["assets"]["total"] == 0           # still growing
    f.write_bytes(glb_bytes(QUAD, [0, 1, 2]))
    assert w.poll() == []                                    # size changed again: stability restarts
    assert len(w.poll()) == 0 and lib.status()["assets"]["total"] == 0       # one stable poll
    done = w.poll()                                          # two stable polls: ingest
    assert len(done) == 1 and lib.status()["assets"]["total"] == 1
    f.unlink()
    w.poll()
    assert lib.status()["missing_files"] == 1 and lib.status()["assets"]["total"] == 1       # the asset stays


def test_watch_needs_the_users_confirm_and_lists_sources(tmp_path):
    lib = make_lib(tmp_path)
    ing = I.Ingest(lib)
    with pytest.raises(LibraryError, match="user's click"):
        ing.watch_add(tmp_path, by="agent")
    assert ing.watch_list() == []
    ing.watch_add(tmp_path, by="captain")
    assert [w["root"] for w in ing.watch_list()] == [str(tmp_path)]
    ing.watch_remove(tmp_path, by="captain")
    assert ing.watch_list() == []
