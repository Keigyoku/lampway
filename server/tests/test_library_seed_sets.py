"""The user's own folders into the Vault (specs/asset_library/asset_seed_captain.md, the folder sets): nothing scans until the user clicks; everything is
referenced, never copied; sources are proven untouched. Synthetic fixtures only: a fake home built in the test, never a real folder."""
import hashlib
import itertools
import json
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from lampway_server.ledger import Ledger
from lampway_server.library import seed_sets as SS
from lampway_server.library.store import AssetLibrary, LibraryError
from tests.test_library_vectors import box, glb_from_mesh


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def png(path, seed=1, size=(24, 16)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.random.default_rng(seed).integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(path)
    return path


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "Downloads/StudioMeshes").mkdir(parents=True)
    (h / "Downloads/StudioMeshes/helmet_a.glb").write_bytes(glb_from_mesh(*box()))
    png(h / "Downloads/Plates/front.png", seed=7)
    png(h / "Pictures/Turnarounds/front.png", seed=7)                     # the same plate in a second folder
    png(h / "Pictures/Turnarounds/side.png", seed=8)
    (h / "Pictures/notes.txt").write_text("not an asset")
    proj = tmp_path / "projects"
    png(proj / "references/front.png", seed=7)                             # and a third
    return {"home": h, "projects": proj}


def sets(home):
    return SS.SeedSets(home=home["home"], project_root=home["projects"])


def snapshot(root):
    return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob("*")) if p.is_file()}


def test_the_initial_import_card_reads_nothing_inside_the_folders(tmp_path, home):
    lib = make_lib(tmp_path)
    card = sets(home).card(lib)
    ids = {s["id"]: s for s in card["sets"]}
    assert set(ids) >= {"downloads", "pictures", "videos", "lampway_projects"}
    assert ids["downloads"]["exists"] is True and ids["videos"]["exists"] is False
    assert all("files" not in s for s in card["sets"]) and not (lib.root / "scans").exists()      # a card is a stat of each root, not a listing
    assert card["action"] == "scan" and "click" in card["note"]


def test_scan_and_import_need_the_users_click(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    with pytest.raises(LibraryError, match="the user's click"):
        ss.scan(lib, ["downloads"], by="agent")
    scan = ss.scan(lib, ["downloads"], by="captain")
    with pytest.raises(LibraryError, match="the user's click"):
        ss.import_(lib, scan["scan_id"], by="agent")


def test_a_set_imports_referenced_and_its_sources_are_proven_untouched(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    before = snapshot(home["home"])
    scan = ss.scan(lib, ["downloads", "pictures"], by="captain")
    assert scan["report"]["by_kind"] == {"mesh": 1, "image": 3}
    rep = ss.import_(lib, scan["scan_id"], by="captain")
    assert rep["sets"]["downloads"]["assets_created"] == 2 and rep["sets"]["pictures"]["assets_created"] == 1 and rep["sets"]["pictures"]["deduped"] == 1
    storages = {l["storage"] for r in lib._reader().execute("select id from asset") for f in lib.get(r[0])["files"] for l in f["locations"]}
    assert storages == {"external"}                                          # referenced, never copied
    assert rep["untouched_sources"] == {"checked": 4, "changed": 0}
    assert snapshot(home["home"]) == before


def test_same_plate_in_three_folders_is_one_blob_three_locations(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    ss.import_(lib, ss.scan(lib, ["downloads", "pictures", "lampway_projects"], by="captain")["scan_id"], by="captain")
    sha = hashlib.sha256((home["home"] / "Downloads/Plates/front.png").read_bytes()).hexdigest()
    locs = [r[0] for r in lib._reader().execute("select path from location where sha256=?", (sha,))]
    assert len(locs) == 3 and lib._reader().execute("select count(*) from blob where sha256=?", (sha,)).fetchone()[0] == 1
    assert lib._reader().execute("select count(distinct v.asset_id) from version_file f join version v on v.id=f.version_id where f.sha256=?", (sha,)).fetchone()[0] == 1


def test_ledger_rows_in_the_projects_root_become_generation_rows(tmp_path, home):
    clip = home["projects"] / "video/clip.png"
    png(clip, seed=11)
    sha = hashlib.sha256(clip.read_bytes()).hexdigest()
    led = Ledger(home["projects"] / "ledger/runs.jsonl")
    row = led.record({"piece": "helmet", "stage": "image", "studio": "openrouter", "model_version": "openai/gpt-image-2.5", "output_hashes": [sha],
                      "cost": {"developer_api_usd": 0.07}, "reason": "plate study"})
    lib = make_lib(tmp_path)
    ss = sets(home)
    rep = ss.import_(lib, ss.scan(lib, ["lampway_projects"], by="captain")["scan_id"], by="captain")
    aid = lib.resolve_asset(sha)
    g = lib.get(aid)["generation"]
    assert len(g) == 1 and g[0]["studio"] == "openrouter" and g[0]["cost_usd"] == pytest.approx(0.07) and g[0]["ledger_ref"] == f"ledger:{row['id']}"
    assert rep["generation_rows"] == 1
    again = ss.import_(lib, ss.scan(lib, ["lampway_projects"], by="captain")["scan_id"], by="captain")
    assert again["generation_rows"] == 0 and len(lib.get(aid)["generation"]) == 1                 # the ledger link is made once


def test_a_root_the_user_adds_is_a_set_and_a_missing_one_is_skipped(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    extra = tmp_path / "elsewhere"
    png(extra / "x.png", seed=3)
    with pytest.raises(LibraryError, match="the user's click"):
        ss.add_root(lib, extra, "Elsewhere", by="agent")
    sid = ss.add_root(lib, extra, "Elsewhere", by="captain")["id"]
    assert sid in {s["id"] for s in ss.card(lib)["sets"]}
    shutil.rmtree(extra)
    scan = ss.scan(lib, [sid, "downloads"], by="captain")
    assert f"set '{sid}' not found at {extra}: skipped" in scan["report"]["skipped_sets"]
    assert scan["report"]["by_kind"] == {"mesh": 1, "image": 1}


def test_reimport_is_idempotent_and_batch_rollback_soft_deletes_only(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    first = ss.import_(lib, ss.scan(lib, ["downloads"], by="captain")["scan_id"], by="captain")
    second = ss.import_(lib, ss.scan(lib, ["downloads"], by="captain")["scan_id"], by="captain")
    assert second["sets"]["downloads"]["assets_created"] == 0
    before = snapshot(home["home"])
    lib.rollback(first["batch"])
    assert lib._reader().execute("select count(*) from asset where status='active'").fetchone()[0] == 0
    assert snapshot(home["home"]) == before


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg needed")
def test_imported_clips_are_analysed_and_a_bad_one_is_reported_not_fatal(tmp_path, home):
    vids = home["home"] / "Videos"
    vids.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=12", "-t", "1", "-vf", "fps=24,format=yuv420p", str(vids / "walk.mp4")], check=True)
    (vids / "broken.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    lib = make_lib(tmp_path)
    ss = sets(home)
    rep = ss.import_(lib, ss.scan(lib, ["videos"], by="captain")["scan_id"], by="captain")
    assert rep["videos_analysed"] == 1 and len(rep["video_failures"]) == 1 and "cannot decode" in rep["video_failures"][0]["why"]
    walk = lib.resolve_asset(str(vids / "walk.mp4"))
    assert lib.get(walk)["stats"]["motion_fps"] == pytest.approx(12.0, abs=0.3)


def test_a_file_that_changes_between_preview_and_import_is_named(tmp_path, home):
    """The check is real: a file rewritten after the preview (by the user, not by us) shows up in untouched_sources with its path."""
    lib = make_lib(tmp_path)
    ss = sets(home)
    scan = ss.scan(lib, ["downloads"], by="captain")
    png(home["home"] / "Downloads/Plates/front.png", seed=99)
    rep = ss.import_(lib, scan["scan_id"], by="captain")
    assert rep["untouched_sources"]["changed"] == 1 and rep["untouched_sources"]["changed_paths"] == [str(home["home"] / "Downloads/Plates/front.png")]


def test_the_tool_surface_lets_an_agent_see_the_card_and_nothing_more(tmp_path, home):
    lib = make_lib(tmp_path)
    ss = sets(home)
    assert ss.handle(lib, {"action": "card"}, by="agent")["ok"] is True
    for action in ("scan", "import", "add_root"):
        out = ss.handle(lib, {"action": action, "sets": ["downloads"], "scan_id": "x", "root": str(tmp_path), "label": "x"}, by="agent")
        assert out["ok"] is False and "the user's click" in out["error"] and out["help"]
    scan = ss.handle(lib, {"action": "scan", "sets": ["downloads"]}, by="captain")
    assert scan["ok"] is True and ss.handle(lib, {"action": "import", "scan_id": scan["scan_id"]}, by="captain")["sets"]["downloads"]["assets_created"] == 2
