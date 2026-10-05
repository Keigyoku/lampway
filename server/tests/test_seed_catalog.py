"""seed_catalog (specs/shelf/seed_catalog.md + specs/wiki/seed_catalog.md): the typed catalogue of every seed (generation variants, banked rerolls) with scores and verdicts.
The shelf's REAL recorded variants / harvest / scores are the fixtures where they exist on this machine; a signed URL is never stored; only the user picks."""

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from lampway_server.seeds import Catalog, SeedError

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
REAL = (SCR / "tripo_mesh/Boots1_g1/variants.json").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's Boots1 seeds are not on this machine")

A, B = "5f108619-cfff-48d2-afce-b9ce6c2b5d93", "37e91e32-2ca2-40e3-b8f4-eafafb01711b"


def variants(tmp_path, signed=False, ids=(A, B)):
    rows = []
    for i, tid in enumerate(ids, 1):
        (tmp_path / f"variant{i}.fbx").write_bytes(b"fbx" + bytes([i]))
        rows.append({"asset": i - 1, "faces_shown": 28000 + i, "topology_shown": "Quad",
                     "url": f"https://tripo-data.test/{tid}/output_mesh_{tid}.fbx" + ("?Signature=SECRETSIG&Expires=1" if signed else ""),
                     "file": f"variant{i}.fbx", "bytes": 4, "sha256": None})
    p = tmp_path / "variants.json"
    p.write_text(json.dumps({"stamp": "10-05 02:57", "variants": rows}))
    return p


@pytest.fixture
def cat(tmp_path):
    return Catalog(tmp_path / "seeds" / "seeds.sqlite")


def test_a_signed_url_is_stored_without_its_signature_and_the_warning_says_so(cat, tmp_path):
    out = cat.ingest_variants(variants(tmp_path, signed=True), "Boots1")
    assert out["ingested"] == 2 and out["warnings"] and "Signature" in out["warnings"][0]
    urls = [r[0] for r in sqlite3.connect(cat.path).execute("select url from seeds")]
    assert urls and all("?" not in u and "SECRETSIG" not in u for u in urls), "a signed URL is a credential"
    assert "SECRETSIG" not in (tmp_path / "seeds" / "seeds.sqlite").read_bytes().decode("latin1")


def test_a_seed_is_stage_model_and_settings_with_the_seed_recorded_as_not_exposed(cat, tmp_path):
    cat.ingest_variants(variants(tmp_path), "Boots1", settings={"topology": "Quad", "polycount": "max"}, model_version="tripo-studio-smart-mesh")
    row = cat.show(A[:8])
    assert row["stage"] == "mesh" and row["seed"] == "not_exposed" and row["model_version"] == "tripo-studio-smart-mesh" and json.loads(row["settings_json"])["polycount"] == "max"


def test_the_list_ranks_scored_seeds_first_and_unscored_last(cat, tmp_path):
    cat.ingest_variants(variants(tmp_path), "Boots1")
    sc = tmp_path / "scores.json"
    sc.write_text(json.dumps({"pieces": {"v2": {"file": f"{tmp_path.name}/variant2.fbx", "rms_logdev": 0.1, "ratios": {}, "dev_pct": {}, "placed": {}}}}))
    out = cat.ingest_scores(sc)
    assert out["scores_attached"] == 1 and out["unmatched"] == []
    table = cat.list(piece="Boots1")
    assert [r["id"] for r in table] == [B[:8], A[:8]] and table[0]["score"] == 0.1 and table[1]["score"] is None


def test_scores_match_by_directory_and_stem_so_a_recurring_variant_name_hits_one_piece(cat, tmp_path):
    d1, d2 = tmp_path / "Boots1_g1", tmp_path / "Helmet1_g1"
    d1.mkdir(), d2.mkdir()
    cat.ingest_variants(variants(d1, ids=(A, B)), "Boots1")
    cat.ingest_variants(variants(d2, ids=("a1111111-0000-4000-8000-000000000001", "a2222222-0000-4000-8000-000000000002")), "Helmet1")
    sc = tmp_path / "scores.json"
    sc.write_text(json.dumps({"pieces": {"v2": {"file": "x/Helmet1_g1/variant2.npz", "rms_logdev": 0.3, "ratios": {}, "dev_pct": {}, "placed": {}},
                                         "nope": {"file": "x/Gone_g1/variant1.npz", "rms_logdev": 0.9, "ratios": {}, "dev_pct": {}, "placed": {}}}}))
    out = cat.ingest_scores(sc)
    assert out["scores_attached"] == 1 and out["unmatched"] == ["nope (Gone_g1/variant1)"] and "ingest_harvest/ingest_variants" in out["hint"]
    scored = [r for r in cat.list() if r["score"] is not None]
    assert [(r["piece"], r["id"]) for r in scored] == [("Helmet1", "a2222222")], "variant2 exists in two pieces: only Helmet1_g1's was scored"


def test_only_the_captain_picks_and_an_ambiguous_prefix_writes_nothing(cat, tmp_path):
    cat.ingest_variants(variants(tmp_path), "Boots1")
    with pytest.raises(SeedError, match="only the user picks a seed"):
        cat.verdict(A[:8], "pick", by="agent")
    with pytest.raises(SeedError, match="2 seeds match"):
        cat.verdict("", "reject")
    with pytest.raises(SeedError, match="0 seeds match"):
        cat.verdict("zzzzzzzz", "reject")
    with pytest.raises(SeedError, match="pick, reroll, reject, usable, fix"):
        cat.verdict(A[:8], "great", by="captain")
    assert cat.show(A[:8])["verdict"] is None and not (tmp_path / "seeds" / "decisions.jsonl").exists(), "refusals write nothing"
    cat.verdict(A[:8], "pick", note="best proportions", by="captain")
    cat.verdict(B[:8], "fix", note="shaft short", by="agent")
    rows = [json.loads(line) for line in (tmp_path / "seeds" / "decisions.jsonl").read_text().splitlines()]
    assert [(r["answer"], r["decider"]) for r in rows] == [("pick", "captain"), ("fix", "agent")] and rows[0]["question"] == "seed_verdict" and rows[0]["descriptor"]["id"] == A
    assert cat.show(B[:8])["verdict"] == "fix"
    cat.verdict(B[:8], "reject", by="captain")
    assert cat.show(B[:8])["verdict"] == "reject", "a correction is a new row; the latest wins"


def test_an_agents_usable_is_a_proposal_not_a_ruling(cat, tmp_path):
    cat.ingest_variants(variants(tmp_path), "Boots1")
    cat.verdict(A[:8], "usable", by="agent")
    row = cat.show(A[:8])
    assert row["verdict"] == "usable" and "proposal" in (row["verdict_note"] or "")


@real
def test_the_real_boots1_variants_and_harvest_reproduce_the_shelfs_catalogue(tmp_path):
    cat = Catalog(tmp_path / "s.sqlite")
    cat.ingest_variants(SCR / "tripo_mesh/Boots1_g1/variants.json", "boots1")
    cat.ingest_harvest(SCR / "tripo_mesh/Boots1_sift1/harvest.json", "boots1")
    shelf = sqlite3.connect(SCR / "tripo_mesh/seeds.sqlite")
    want = sorted((r[0], r[1], r[2], r[3]) for r in shelf.execute("select id,kind,topology,faces from seeds where piece='boots1'"))
    got = sorted((r["id"], r["kind"], r["topology"], r["faces"]) for r in [cat.show(x["id"]) for x in cat.list(piece="boots1")])
    assert got == want and len(got) == 9
    sc = cat.ingest_scores(SCR / "proportion/pieces_g1/Boots1.json")
    assert sc["scores_attached"] == 4 and sc["unmatched"] == []


@pytest.mark.anyio
async def test_the_agent_tool_ingests_inside_the_project_root_and_cannot_pick(tmp_path, monkeypatch):
    from lampway_server.agent import seed_tools as SDT
    from lampway_server.agent import tools as T
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("LAMPWAY_SEED_DB", raising=False)
    variants(tmp_path)
    assert "lampway_seed_catalog" in {t.name for t in T.TOOLS}
    out, err = await SDT.call("lampway_seed_catalog", {"verb": "ingest_variants", "file": "variants.json", "piece": "Boots1"})
    assert err is False and json.loads(out)["ingested"] == 2
    out, err = await SDT.call("lampway_seed_catalog", {"verb": "verdict", "id": A[:8], "verdict": "pick", "by": "captain"})
    assert err is True and "only the user picks" in out, "claiming by=captain does nothing: the tool always records as the agent"
    out, err = await SDT.call("lampway_seed_catalog", {"verb": "list", "piece": "Boots1"})
    assert [r["id"] for r in json.loads(out)["table"]] == [A[:8], B[:8]] or len(json.loads(out)["table"]) == 2
    out, err = await SDT.call("lampway_seed_catalog", {"verb": "ingest_variants", "file": "../../etc/passwd", "piece": "x"})
    assert err is True
