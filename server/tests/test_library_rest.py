"""The Vault routes the editor uses beyond search and read (specs/asset_library/asset_ui_editor.md section 4 operators; asset_query section 6.9): a page's tiles carry a
thumbnail path when the asset is itself a picture, "Find like this", boards and saved searches, and the user's own rating."""
import pytest
from PIL import Image

from .test_library_ingest import QUAD, glb_bytes


@pytest.fixture
def lib(fake, tmp_path, monkeypatch):
    root = tmp_path / "project" / "armour"
    root.mkdir(parents=True)
    (root / "bronze_greaves.glb").write_bytes(glb_bytes(QUAD, [0, 1, 2, 0, 2, 3]))
    Image.new("RGB", (16, 12), (200, 100, 50)).save(root / "greaves_front.png")
    Image.new("RGB", (16, 12), (205, 98, 52)).save(root / "greaves_back.png")
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "project"))
    fake.login()
    scan = fake.post("/api/v1/library/ingest/scan", json={"paths": [str(root)]}).json()["data"]
    fake.post("/api/v1/library/ingest/import", json={"scan_id": scan["scan_id"]})
    items = fake.post("/api/v1/library/query", json={"limit": 50}).json()["data"]["items"]
    return fake, root, {i["name"]: i for i in items}


def test_a_picture_is_its_own_thumbnail_and_a_mesh_has_none_yet(lib):
    fake, root, items = lib
    assert items["greaves_front"]["thumb"] == str(root / "greaves_front.png")
    assert items["bronze_greaves"]["thumb"] is None


def test_find_like_this_over_rest_after_the_index_runs(lib):
    fake, root, items = lib
    for space in ("image_hist", "image_dhash"):              # the look axis averages both spaces over the assets present in both
        plan = fake.post("/api/v1/library/embed", json={"action": "plan", "space": space}).json()["data"]
        assert plan["uploads"] is False and plan["planned"] == 2
        ran = fake.post("/api/v1/library/embed", json={"action": "run", "plan_id": plan["plan_id"]}).json()["data"]
        assert ran["done"] == 2 and ran["bytes_uploaded"] == 0
    r = fake.post("/api/v1/library/similar", json={"asset_ids": [items["greaves_front"]["id"]], "axes": ["look"], "k": 5})
    assert r.status_code == 200, r.text
    found = [i["id"] for i in r.json()["data"]["items"]]
    assert found and found[0] == items["greaves_back"]["id"]


def test_boards_and_saved_searches_and_the_users_rating(lib):
    fake, root, items = lib
    board = fake.post("/api/v1/library/collect", json={"action": "create", "name": "picks", "kind": "board"}).json()["data"]["collection"]
    got = fake.post("/api/v1/library/collect", json={"action": "add", "collection": board["id"], "asset_ids": [items["bronze_greaves"]["id"]]}).json()["data"]
    assert got["collection"]["items"] == 1
    saved = fake.post("/api/v1/library/collect", json={"action": "save_search", "name": "greaves", "query": {"text": "greaves"}})
    assert saved.status_code == 200 and saved.json()["data"]["search"]["name"] == "greaves"
    rated = fake.post(f"/api/v1/library/assets/{items['bronze_greaves']['id']}/rate", json={"stars": 4}).json()["data"]
    assert rated["rating"]["captain"] == 4
    bad = fake.post("/api/v1/library/collect", json={"action": "explode"})
    assert bad.status_code == 422 and "unknown action" in bad.json()["detail"]


def test_the_view_routes_lineage_views_and_diff(lib):
    fake, root, items = lib
    front, back, mesh = items["greaves_front"]["id"], items["greaves_back"]["id"], items["bronze_greaves"]["id"]
    rel = fake.post("/api/v1/library/relate", json={"src": mesh, "type": "generated_from", "dst": front})
    assert rel.status_code == 200, rel.text
    lin = fake.get(f"/api/v1/library/assets/{mesh}/lineage?depth=3").json()["data"]
    assert {n["id"] for n in lin["nodes"]} == {mesh, front} and lin["png"].endswith(".png")
    from pathlib import Path
    assert Path(lin["png"]).is_file()
    views = fake.get(f"/api/v1/library/assets/{mesh}/views").json()["data"]
    assert views == {"turntable": [], "ball": None, "overlay": None, "sheet": None, "thumb": None, "proxy": [], "strip": None}
    diff = fake.post("/api/v1/library/diff", json={"a": front, "b": back}).json()["data"]
    assert 0 < diff["mean_abs"] and diff["ssim"] <= 1.0 and Path(diff["diff"]).is_file()
    bad = fake.post("/api/v1/library/diff", json={"a": front, "b": mesh})
    assert bad.status_code == 422 and "two pictures" in bad.json()["detail"]


def test_a_page_can_carry_each_assets_main_file_path(lib):
    fake, root, items = lib
    page = fake.post("/api/v1/library/query", json={"limit": 50, "include": ["thumb", "tags", "path"]}).json()["data"]
    paths = {i["name"]: i["path"] for i in page["items"]}
    assert paths["bronze_greaves"] == str(root / "bronze_greaves.glb") and paths["greaves_front"] == str(root / "greaves_front.png")
    plain = fake.post("/api/v1/library/query", json={"limit": 50}).json()["data"]
    assert "path" not in plain["items"][0]
