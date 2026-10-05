"""The Tripo Studio drivers, ported server-side from the owner's shelf. They drive his logged-in browser and can spend
credits, so NOTHING here touches a browser or a credit: the invariants in their headers are tested as pure checks against
his own recorded dry runs (fixtures/), and every mutating command is refused unless the studio guard is armed."""

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from lampway_server.studios import axi, guard
from lampway_server.studios.tripo import seed_db, studio, tripo_regen, verify

FIX = Path(__file__).parent / "fixtures"
IMAGE = json.loads((FIX / "tripo_image_dry_run.json").read_text())
MESH = json.loads((FIX / "tripo_mesh_dry_run.json").read_text())


# ---- the guard

def test_the_guard_refuses_unless_armed(monkeypatch, capsys):
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    with pytest.raises(SystemExit) as e:
        guard.require_armed("generate images")
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert out.startswith("error:") and "generate images" in out and "LAMPWAY_STUDIO_ARMED=1" in out


@pytest.mark.parametrize("val", ["", "0", "true", "yes", "2"])
def test_only_exactly_1_arms_it(monkeypatch, val):
    monkeypatch.setenv("LAMPWAY_STUDIO_ARMED", val)
    assert guard.armed() is False


def test_armed_lets_it_through(monkeypatch):
    monkeypatch.setenv("LAMPWAY_STUDIO_ARMED", "1")
    guard.require_armed("anything")


# ---- image generation: the invariants, on his recorded dry run

def image_args(**kw):
    base = dict(model="GPT Image 2.5", aspect="1:1", count="4", no_4k=False, prompt=IMAGE["prompt"], n_refs=1, n_ref_thumbs=1)
    base.update(kw)
    return base


def test_his_recorded_dry_run_passes_every_check():
    assert verify.image_problems(IMAGE["settings_read_back"], **image_args()) == []


def test_a_price_that_is_not_free_refuses():
    st = copy.deepcopy(IMAGE["settings_read_back"])
    st["price"] = [{"v": 120, "struck": False}]
    assert any("price is not free" in p for p in verify.image_problems(st, **image_args()))


def test_a_struck_through_price_does_not_count_but_no_live_price_does():
    st = copy.deepcopy(IMAGE["settings_read_back"])
    st["price"] = [{"v": 120, "struck": True}]
    assert any("price is not free" in p for p in verify.image_problems(st, **image_args()))


def test_fewer_than_four_images_refuses():
    st = copy.deepcopy(IMAGE["settings_read_back"])
    st["counts"] = {"1": "on", "2": "off", "3": "off", "4": "off"}
    assert any("count state" in p for p in verify.image_problems(st, **image_args()))
    assert verify.image_count_refusal("2") and "never fewer than 4" in verify.image_count_refusal("2")
    assert verify.image_count_refusal("4") is None


def test_4k_off_refuses_unless_asked_for():
    st = copy.deepcopy(IMAGE["settings_read_back"])
    st["fourk"] = "false"
    assert any("4K switch" in p for p in verify.image_problems(st, **image_args()))
    assert verify.image_problems(st, **image_args(no_4k=True)) == []


def test_every_setting_is_read_back_the_prompt_the_model_the_aspect_the_references():
    st = copy.deepcopy(IMAGE["settings_read_back"])
    st["prompt"] = "something else"
    st["model"] = "Other Model"
    st["aspects"]["16:9"] = "on"
    probs = verify.image_problems(st, **image_args(n_ref_thumbs=0))
    for needle in ("model reads", "aspect state", "prompt text differs", "reference(s) uploaded"):
        assert any(needle in p for p in probs), needle


# ---- mesh generation

def mesh_args(**kw):
    base = dict(polycount="50000", topology="Triangle", expect_price="100", smart_mesh_on=True)
    base.update(kw)
    return base


def test_his_recorded_mesh_dry_run_passes_every_check():
    assert verify.mesh_problems(MESH, **mesh_args()) == []


def test_a_lower_polycount_than_the_topologys_maximum_refuses():
    rec = copy.deepcopy(MESH)
    rec["polycount_read_back"], rec["polycount_slider"] = "5000", "5000/50000"
    probs = verify.mesh_problems(rec, **mesh_args(polycount="5000"))
    assert any("is not the maximum" in p for p in probs)


def test_fewer_than_four_generations_or_view_thumbnails_refuse():
    rec = copy.deepcopy(MESH)
    rec["generations_state"] = {"1": "off", "2": "on", "4": "off"}
    rec["thumbnails_seen"] = 3
    probs = verify.mesh_problems(rec, **mesh_args())
    assert any("generations state" in p for p in probs) and any("3 of 4 view thumbnails" in p for p in probs)


def test_a_price_other_than_the_expected_one_refuses():
    rec = copy.deepcopy(MESH)
    rec["generate_button"] = "Generate 150"
    assert any("price reads" in p for p in verify.mesh_problems(rec, **mesh_args()))


def test_multi_view_needs_exactly_the_four_cardinal_slots():
    rec = copy.deepcopy(MESH)
    rec["slot_map"] = {"Front": 0, "Left": 1, "Right": 2}
    assert any("slots not mapped" in p for p in verify.mesh_problems(rec, **mesh_args()))


def test_the_wrong_topology_shown_selected_refuses():
    assert any("not shown selected" in p for p in verify.mesh_problems(MESH, **mesh_args(topology="Quad", polycount="50000")))


# ---- Edit Mesh retries (tripo_regen)

def test_an_exact_region_retry_needs_the_captains_approval_flag():
    assert verify.region_refusal(approved=False) and "approval" in verify.region_refusal(approved=False)
    assert verify.region_refusal(approved=True) is None


@pytest.mark.parametrize("argv", [["retry", "o", "10-04 12:00", "30000"], ["sift", "o", "30000"], ["apply"], ["discard"],
                                  ["region", "o", "30000", "--bbox-blender", "0,0,0,1,1,1", "--approved-exact-region"]])
def test_every_mutating_regen_command_is_refused_before_the_browser_unless_armed(monkeypatch, capsys, argv):
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    monkeypatch.setattr("sys.argv", ["tripo_regen", *argv])
    with pytest.raises(SystemExit) as e:
        tripo_regen.main()
    assert e.value.code == 1
    assert "LAMPWAY_STUDIO_ARMED=1" in capsys.readouterr().out


def test_region_without_the_flag_is_refused_before_the_guard_or_a_browser(monkeypatch, capsys):
    monkeypatch.setenv("LAMPWAY_STUDIO_ARMED", "1")
    monkeypatch.setattr("sys.argv", ["tripo_regen", "region", "o", "30000", "--bbox-blender", "0,0,0,1,1,1"])
    with pytest.raises(SystemExit) as e:
        tripo_regen.main()
    assert e.value.code == 1 and "approval flag" in capsys.readouterr().out


def test_no_browser_means_an_unreachable_state_not_a_crash(monkeypatch):
    monkeypatch.setenv("LAMPWAY_STUDIO_CDP", "http://127.0.0.1:1")
    st = studio.live()
    assert st["browser"].startswith("unreachable")


# ---- the seed catalog (pure sqlite; no signed URLs stored)

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_SEED_DB", str(tmp_path / "seeds.sqlite"))
    return tmp_path / "seeds.sqlite"


def run_seed_db(monkeypatch, capsys, *argv):
    monkeypatch.setattr("sys.argv", ["seed_db", *argv])
    seed_db.main()
    return capsys.readouterr().out


SIGNED = "https://cdn.example/output_mesh_0a1b2c3d-0000-1111-2222-333344445555.fbx?Policy=SECRET&Signature=SECRET&Key-Pair-Id=K"


def test_ingest_variants_stores_the_unsigned_url_and_never_the_signature(tmp_path, db, monkeypatch, capsys):
    f = tmp_path / "variant1.fbx"
    f.write_bytes(b"mesh")
    j = tmp_path / "variants.json"
    j.write_text(json.dumps({"variants": [{"url": SIGNED, "file": "variant1.fbx", "faces_shown": 25000, "topology_shown": "Quad"}]}))
    out = run_seed_db(monkeypatch, capsys, "ingest-variants", str(j), "chest")
    assert "ingested: 1" in out
    row = sqlite3.connect(db).execute("SELECT id, piece, url, faces, topology FROM seeds").fetchone()
    assert row == ("0a1b2c3d-0000-1111-2222-333344445555", "chest", "https://cdn.example/output_mesh_0a1b2c3d-0000-1111-2222-333344445555.fbx", 25000, "Quad")
    assert "SECRET" not in json.dumps(sqlite3.connect(db).execute("SELECT * FROM seeds").fetchall())


def test_verdicts_attach_by_unique_id_prefix_and_an_ambiguous_prefix_is_refused(tmp_path, db, monkeypatch, capsys):
    con = sqlite3.connect(db)
    con.execute(seed_db.SCHEMA)
    for i in ("aaaa1111-x", "aaaa2222-x"):
        con.execute("INSERT INTO seeds (id, piece) VALUES (?, 'chest')", (i,))
    con.commit()
    out = run_seed_db(monkeypatch, capsys, "verdict", "aaaa1", "usable", "--note", "good")
    assert "verdict: usable" in out
    with pytest.raises(SystemExit):
        run_seed_db(monkeypatch, capsys, "verdict", "aaaa", "usable")
    assert sqlite3.connect(db).execute("SELECT verdict FROM seeds WHERE id='aaaa1111-x'").fetchone() == ("usable",)


def test_the_catalog_lists_ranked_by_score_with_a_definitive_count(db, monkeypatch, capsys):
    con = sqlite3.connect(db)
    con.execute(seed_db.SCHEMA)
    con.executemany("INSERT INTO seeds (id, piece, score_rms) VALUES (?, 'chest', ?)", [("b" * 8, 0.2), ("a" * 8, 0.1), ("c" * 8, None)])
    con.commit()
    out = run_seed_db(monkeypatch, capsys, "list", "--piece", "chest")
    assert out.splitlines()[0] == "count: 3 of 3 total"
    ids = [l.strip().split(",")[0] for l in out.splitlines() if l.startswith("  ") and "," in l and not l.strip().startswith("-")]
    assert ids[:3] == ["aaaaaaaa", "bbbbbbbb", "cccccccc"]


# ---- relief generator size limit and relief on the free site

def test_an_upload_over_the_sites_limit_is_refused_before_any_browser(tmp_path):
    from lampway_server.studios.tripo import relief_gen
    big = tmp_path / "big.png"
    big.write_bytes(b"x" * (relief_gen.MAX_UPLOAD + 1))
    small = tmp_path / "small.png"
    small.write_bytes(b"x")
    assert relief_gen.too_big([str(big), str(small)]) == [str(big)]


# ---- the Texture + PBR driver (tripo_texture.py): its checks against the owner's recorded texture dry run

TEXTURE = json.loads((FIX / "tripo_texture_dry_run.json").read_text())


def test_the_recorded_texture_panel_passes_as_requested():
    st = TEXTURE["state"]
    assert verify.texture_problems(st, res="8K", remove_lighting=True, expect_price=30) == []


def test_a_texture_panel_that_differs_from_the_request_is_refused_with_each_difference_named():
    st = TEXTURE["state"]
    bad = verify.texture_problems(st, res="4K", remove_lighting=False, expect_price=30)
    assert any("4K" in b for b in bad) and any("lighting" in b.lower() for b in bad)
    assert any("price" in b for b in verify.texture_problems(st, res="8K", remove_lighting=True, expect_price=25))
    disabled = {**st, "disabled": True}
    assert any("disabled" in b for b in verify.texture_problems(disabled, res="8K", remove_lighting=True, expect_price=30))


def test_the_pbr_panel_is_judged_by_its_price_and_button():
    assert verify.pbr_problems({"button": "Generate PBR 5", "disabled": False}, expect_price=5) == []
    assert verify.pbr_problems({"button": "Generate PBR 10", "disabled": False}, expect_price=5)
    assert verify.pbr_problems({"button": None, "disabled": None}, expect_price=5)


def test_texturing_comes_last_so_a_history_without_a_smart_uv_step_is_refused():
    assert verify.texturing_last_refusal([{"stamp": "10-05 14:02", "icon": "i-tripo:uv"}, {"stamp": "Current Version", "icon": None}]) is None
    assert "Smart UV" in verify.texturing_last_refusal([{"stamp": "10-05 14:02", "icon": "i-tripo:remesh"}])
    assert "Smart UV" in verify.texturing_last_refusal([])


def test_the_texture_driver_refuses_to_click_generate_unless_armed(monkeypatch, capsys):
    """run_and_fetch is the only path that clicks Generate; it starts with the guard."""
    import asyncio
    from lampway_server.studios.tripo import tripo_texture
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    with pytest.raises(SystemExit):
        asyncio.run(tripo_texture.run_and_fetch(object(), "/tmp/never"))
    assert "LAMPWAY_STUDIO_ARMED=1" in capsys.readouterr().out
