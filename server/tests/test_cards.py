"""Project cards (specs/mrmak/09-report-cards.md section 10): the registry keeps unknown fields and loses no concurrent change, the archive rule with an injected date,
the builder's deterministic and localised pages, the generated-HTML contract, escaped prompts, the content server's refusals on its own origin, and a day's activity."""
import html.parser
import json
import multiprocessing
import subprocess
import threading
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lampway_server.cards import activity as ACT
from lampway_server.cards import archive as AR
from lampway_server.cards import build as BLD
from lampway_server.cards import content as CON
from lampway_server.cards.registry import CardError, Registry
from lampway_server.ledger import Ledger
from lampway_server.prompts.runlog import RunLog

DAY = 86400.0


@pytest.fixture
def reg(tmp_path):
    return Registry(tmp_path / "project", today=lambda: "2026-10-05")


def test_registry_update_preserves_unknown_fields_and_bumps_updated(reg):
    card = reg.create({"title": "Boots1", "category": "armour", "custom_flag": {"x": 1}})
    raw = json.loads(reg.path.read_text())
    raw["registry_note"] = "kept"
    raw["entities"][0]["from_upstream"] = [1, 2]
    reg.path.write_text(json.dumps(raw))
    reg.today = lambda: "2026-10-07"
    out = reg.update(card["id"], status="done", pinned=True)
    raw = json.loads(reg.path.read_text())
    assert raw["registry_note"] == "kept"
    e = raw["entities"][0]
    assert e["from_upstream"] == [1, 2] and e["custom_flag"] == {"x": 1} and e["status"] == "done" and e["pinned"] is True
    assert e["updated"] == "2026-10-07" and out["updated"] == "2026-10-07" and e["created"] == "2026-10-05"
    with pytest.raises(CardError, match="status is active, done or archived"):
        reg.update(card["id"], status="finished")
    with pytest.raises(CardError, match="pinned is true or false"):
        reg.update(card["id"], pinned="yes")
    with pytest.raises(CardError, match="no card 'nope'"):
        reg.update("nope", status="done")
    with pytest.raises(CardError, match="400 characters"):
        reg.create({"title": "x", "description": "d" * 401})


def _bump(root, cid, status):
    Registry(root, today=lambda: "2026-10-05").update(cid, status=status)


def test_concurrent_updates_do_not_lose_a_change(reg):
    ids = [reg.create({"title": f"card {i}"})["id"] for i in range(11)]
    threads = [threading.Thread(target=reg.update, args=(ids[i],), kwargs={"status": "done"}) for i in range(8)]
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_bump, args=(reg.root, ids[8 + i], "archived")) for i in range(3)]
    for t in threads + procs:
        t.start()
    for t in threads:
        t.join()
    for p in procs:
        p.join(60)
    by = {c["id"]: c["status"] for c in json.loads(reg.path.read_text())["entities"]}
    assert [by[i] for i in ids] == ["done"] * 8 + ["archived"] * 3


def test_archive_rule_with_an_injected_date():
    today = "2026-10-13"
    base = {"status": "active", "pinned": False, "created": "2026-09-01"}
    assert AR.is_archived({**base, "updated": "2026-10-05"}, today) is True              # untouched for 8 days
    assert AR.is_archived({**base, "updated": "2026-10-07"}, today) is False             # 6 days
    assert AR.is_archived({**base, "updated": "2026-10-01", "pinned": True}, today) is False
    assert AR.is_archived({**base, "updated": "2026-10-12", "status": "archived"}, today) is True
    reg_cards = [{**base, "id": "a", "title": "Boots1", "updated": "2026-10-01"}, {**base, "id": "b", "title": "Helm", "updated": "2026-10-12"}]
    assert [c["id"] for c in AR.visible(reg_cards, today, query="")] == ["b"]
    assert [c["id"] for c in AR.visible(reg_cards, today, query="boots")] == ["a"], "search reaches into the archive"


def ledger_fixture(root: Path):
    from PIL import Image
    (root / "plates").mkdir(parents=True, exist_ok=True)
    (root / "clips").mkdir(parents=True, exist_ok=True)
    for i, letter in enumerate("ABC"):
        Image.new("RGB", (8, 8), (60 * i, 90, 40)).save(root / "plates" / f"{letter}.png")
    (root / "clips" / "m1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42 a fixture clip")
    led = Ledger(root / "ledger" / "runs.jsonl")
    runs = RunLog(led.path)
    base = led.record({"piece": "Boots1", "stage": "image", "studio": "openrouter", "id": "r3-base", "settings": {"round": "3"}, "by": "captain", "decision": "chosen",
                       "reason": "the v2 original", "cost": {"developer_api_usd": 0.07}})
    rows = []
    for letter, model in (("A", "gemini"), ("B", "gpt-image"), ("C", "seedream")):
        rows.append(led.record({"piece": "Boots1", "stage": "image", "studio": "openrouter", "id": f"r4-{letter}", "settings": {"round": "4", "variant": letter, "model": model},
                                "parent_hashes": ["base"], "cost": {"developer_api_usd": 0.07}, "reason": f"variant {letter}"}))
        runs.record(f"job-{letter}", prompt=f"bronze greaves {letter} </pre><script>alert(1)</script>", model=model, template="plate@4",
                    variables={"metal": "bronze", "variant": letter}, cost=0.07, output=f"plates/{letter}.png", service="image_gen", extra={"piece": "Boots1", "ledger_id": f"r4-{letter}"})
    led.record({"piece": "Boots1", "stage": "decision", "studio": "local", "id": "r4-pick", "settings": {"round": "4", "pick": "B"}, "by": "captain", "decision": "chosen",
                "reason": "B keeps the shin ridge"})
    led.record({"piece": "Boots1", "stage": "video", "studio": "higgsfield", "id": "m1", "settings": {"question": "what does the upper body do while she stands?",
                "clip": "clips/m1.mp4", "start_frame": "plates/B.png", "template": "motion@2"}, "cost": {"generation_credits": 30, "price_source": "button read-back"}})
    return led, runs, base, rows


def test_build_is_deterministic_and_localised(tmp_path):
    root = tmp_path / "project"
    led, runs, *_ = ledger_fixture(root)
    reg = Registry(root, today=lambda: "2026-10-05")
    card = reg.create({"title": "Boots1"})
    p1 = BLD.build(reg, led, runs, card["id"], "design_versions", "Boots1", "4")
    first = Path(p1).read_bytes()
    p2 = BLD.build(reg, led, runs, card["id"], "design_versions", "Boots1", "4")
    assert Path(p2).read_bytes() == first and p1 == p2
    other = reg.create({"title": "Helm"})
    led.record({"piece": "Helm", "stage": "image", "studio": "openrouter", "id": "h1", "settings": {"round": "1", "variant": "A"}, "cost": {"developer_api_usd": 0.07}})
    hp = BLD.build(reg, led, runs, other["id"], "design_versions", "Helm", "1")
    helm_before = Path(hp).read_bytes()
    runs.rate("job-B", 5, "the pick")
    BLD.build(reg, led, runs, card["id"], "design_versions", "Boots1", "4")
    BLD.build(reg, led, runs, other["id"], "design_versions", "Helm", "1")
    assert Path(p1).read_bytes() != first and Path(hp).read_bytes() == helm_before
    steps = reg.get(card["id"])["steps"]
    assert [s["name"] for s in steps] == ["Round 4"]
    with pytest.raises(CardError, match="no runs recorded for Ghost: nothing to report"):
        BLD.build(reg, led, runs, card["id"], "design_versions", "Ghost", "auto")


class _Doc(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.stack, self.details_pre = [], [], 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "pre" and "details" in self.stack:
            self.details_pre += 1
        self.stack.append(tag)

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop() != tag:
            pass


def test_generated_html_contract_and_escaped_prompts(tmp_path):
    root = tmp_path / "project"
    led, runs, *_ = ledger_fixture(root)
    reg = Registry(root, today=lambda: "2026-10-05")
    card = reg.create({"title": "Boots1"})
    pages = [BLD.build(reg, led, runs, card["id"], k, "Boots1", "4") for k in ("design_versions", "motion_tests", "receipt")]
    for page in pages:
        text = Path(page).read_text()
        assert text.startswith("<!-- generated by lampway_cards; edits are overwritten: change the data -->")
        assert 'data-lw-report="document"' in text and "../_shared/report.css" in text and "../_shared/report.js" in text
        doc = _Doc()
        doc.feed(text)
        for tag, attrs in doc.tags:
            assert all(not str(v or "").startswith(("http:", "https:")) for v in attrs.values()), (tag, attrs)
            if tag == "img":
                assert attrs.get("alt")
            if tag == "video":
                assert "controls" in attrs
        assert "<script>alert(1)" not in text
    design = Path(pages[0]).read_text()
    assert "&lt;/pre&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in design and "Saved generation prompt" in design
    doc = _Doc()
    doc.feed(design)
    assert doc.details_pre == 3, "each of the three variants' saved prompt sits in a <details>"
    assert "B keeps the shin ridge" in design and "BASE" in design
    css = (root / "cards" / "_shared" / "report.css").read_text()
    assert "@import" not in css and "http" not in css
    js = (root / "cards" / "_shared" / "report.js").read_text()
    assert all(k in js for k in ("ArrowLeft", "ArrowRight", "Escape", "focus()")), "the lightbox's keyboard and focus contract"
    motion = Path(pages[1]).read_text()
    assert "what does the upper body do while she stands?" in motion and '<video controls src="media/m1.mp4">' in motion
    assert '<img src="media/B.png" alt=' in design and (Path(pages[0]).parent / "media" / "B.png").is_file(), "media is copied into the card's own folder"


def test_content_server_refusals_on_its_own_origin(tmp_path):
    root = tmp_path / "project" / "cards"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "page.html").write_text("<p>ok</p>")
    (root / "c1" / ".env").write_text("SECRET=1")
    (root / "c1" / "auth.json").write_text("{}")
    (root / "c1" / "tokens.json").write_text("{}")
    (root / "c1" / "oauth_x.json").write_text("{}")
    (root / "c1" / "node_modules").mkdir()
    (root / "c1" / "node_modules" / "x.js").write_text("1")
    (root / "c1" / "big.txt").write_text("0123456789")
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    (root / "c1" / "link.txt").symlink_to(outside)
    srv = CON.ContentServer(root, host="127.0.0.1", port=18999)
    grant = srv.grant()
    with TestClient(srv.app, base_url="http://127.0.0.1:18999") as http:
        ok = http.get(f"/view/{grant}/c1/page.html")
        assert ok.status_code == 200 and ok.headers["x-content-type-options"] == "nosniff" and ok.headers["referrer-policy"] == "no-referrer"
        assert ok.headers["cross-origin-resource-policy"] == "same-site"
        for bad in ("c1/.env", "c1/auth.json", "c1/tokens.json", "c1/oauth_x.json", "c1/node_modules/x.js", "c1/link.txt", "c1/..%2f..%2foutside.txt"):
            assert http.get(f"/view/{grant}/{bad}").status_code in (403, 404), bad
        assert http.get(f"/view/not-a-grant/c1/page.html").status_code == 404
        assert http.post(f"/view/{grant}/c1/page.html").status_code == 405
        part = http.get(f"/view/{grant}/c1/big.txt", headers={"Range": "bytes=2-4"})
        assert part.status_code == 206 and part.content == b"234"
        assert http.get(f"/view/{grant}/c1/big.txt", headers={"Range": "bytes=50-60"}).status_code == 416
        head = http.head(f"/view/{grant}/c1/page.html")
        assert head.status_code == 200 and head.content == b""
    with TestClient(srv.app, base_url="http://evil.example:18999") as http:
        assert http.get(f"/view/{grant}/c1/page.html").status_code == 421


def test_two_ports_two_origins(tmp_path):
    srv = CON.ContentServer(tmp_path / "cards", host="127.0.0.1", port=0, api_port=8787)
    with pytest.raises(CardError, match="not serving yet"):
        srv.origin()
    origin = srv.serve()
    assert srv.port not in (0, 8787) and origin == f"http://127.0.0.1:{srv.port}", "a report's script never shares the API's origin (and its token)"
    import httpx
    assert httpx.get(f"{origin}/view/x/y.html").status_code == 404, "it really serves, on its own port"
    with pytest.raises(CardError, match="its own port"):
        CON.ContentServer(tmp_path / "cards", host="127.0.0.1", port=8787, api_port=8787)


def test_activity_for_a_date(tmp_path):
    root = tmp_path / "project"
    led, runs, *_ = ledger_fixture(root)
    reg = Registry(root, today=lambda: "2026-10-03")
    a = reg.create({"title": "Boots1"})
    reg.today = lambda: "2026-10-05"
    reg.create({"title": "Helm"})
    day = time.strftime("%Y-%m-%d", time.localtime(led.rows()[0]["t"]))
    out = ACT.activity(reg, led, "2026-10-03", git_root=root)
    assert [c["id"] for c in out["cards"]] == [a["id"]] and out["commits"] == [] and "not a record of unsaved work" in out["basis"]
    today = ACT.activity(reg, led, day, git_root=root)
    assert today["ledger"]["rows"] >= 5 and today["ledger"]["spend"]["developer_api_usd"] == pytest.approx(0.28)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", "add", "cards"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "cards: Boots1 round 4"], check=True)
    committed = ACT.activity(reg, led, time.strftime("%Y-%m-%d"), git_root=root)
    assert "cards: Boots1 round 4" in committed["commits"]
