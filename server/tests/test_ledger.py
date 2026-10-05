"""The experiment ledger (specs/wiki/experiment_ledger.md): ONE append-only record of every generation or experiment run, shared with the prompt run log.
Four cost quantities stay separate; rows are never edited (a correction supersedes); an agent can never choose a spend result; concurrent workers
append without losing rows (threads AND processes)."""

import json
import multiprocessing
import threading

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.ledger import Ledger, LedgerError
from lampway_server.prompts.runlog import RunLog

from .fake_client import FakeMixarClient


def run(**kw):
    base = {"piece": "Boots1", "stage": "uv", "studio": "tripo", "settings": {"unwrap": "Smart UV"}, "by": "captain"}
    base.update(kw)
    return base


def test_rows_are_append_only_and_a_correction_supersedes_without_editing(tmp_path):
    lg = Ledger(tmp_path / "ledger" / "runs.jsonl")
    a = lg.record(run(cost={"generation_credits": 20, "price_source": "driver read-back"}, reason="first unwrap"))
    before = (tmp_path / "ledger" / "runs.jsonl").read_text()
    b = lg.record(run(cost={"generation_credits": 20, "price_source": "driver read-back"}, supersedes=a["id"], reason="logged twice by mistake: this is the real one"))
    assert (tmp_path / "ledger" / "runs.jsonl").read_text().startswith(before), "nothing before the new line changed"
    assert [r["id"] for r in lg.list(piece="Boots1")] == [b["id"]], "a superseded row is hidden by default"
    assert {r["id"] for r in lg.list(piece="Boots1", include_superseded=True)} == {a["id"], b["id"]}
    with pytest.raises(LedgerError, match="no row"):
        lg.record(run(supersedes="nope"))


def test_concurrent_appends_from_threads_and_processes_lose_no_row(tmp_path):
    path = tmp_path / "runs.jsonl"
    lg = Ledger(path)
    ts = [threading.Thread(target=lambda i=i: [lg.record(run(piece=f"t{i}", reason=str(k))) for k in range(25)]) for i in range(8)]
    ps = [multiprocessing.Process(target=_proc_append, args=(str(path), i)) for i in range(4)]
    for t in ts + ps:
        t.start()
    for t in ts + ps:
        t.join()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 8 * 25 + 4 * 25 and len({r["id"] for r in rows}) == len(rows)


def _proc_append(path, i):
    lg = Ledger(path)
    for k in range(25):
        lg.record(run(piece=f"p{i}", reason=str(k)))


def test_an_agent_can_never_choose_a_spend_result_but_the_captain_and_a_rule_can(tmp_path):
    lg = Ledger(tmp_path / "r.jsonl")
    with pytest.raises(LedgerError, match="only the user chooses a result"):
        lg.record(run(stage="texture", decision="chosen", by="agent"))
    lg.record(run(stage="texture", decision="rejected", by="agent", reason="blurry"))
    lg.record(run(stage="texture", decision="chosen", by="captain"))
    lg.record(run(stage="uv", studio="local", decision="chosen", by="agent"))                       # no spend: an agent may pick a local result


def test_a_price_needs_the_source_it_was_read_from(tmp_path):
    lg = Ledger(tmp_path / "r.jsonl")
    with pytest.raises(LedgerError, match="record the price the driver read back"):
        lg.record(run(cost={"generation_credits": 20}))
    lg.record(run(cost={"generation_credits": 20, "price_source": "get_cost"}))
    for bad in (dict(stage="nonsense"), dict(studio="nowhere"), dict(piece=""), dict(cost={"generation_credits": "20", "price_source": "x"}), dict(seed="abc")):
        with pytest.raises(LedgerError):
            lg.record(run(**bad))


def test_the_receipt_sums_the_four_quantities_separately(tmp_path):
    lg = Ledger(tmp_path / "r.jsonl")
    lg.record(run(cost={"subscription": "Tripo Pro, 1450 credits left", "generation_credits": 20, "price_source": "button", "work_s": 40}))
    lg.record(run(stage="texture", cost={"generation_credits": 30, "price_source": "button", "work_s": 90.5}))
    lg.record(run(stage="image", studio="openrouter", cost={"developer_api_usd": 0.24}))
    lg.record(run(piece="Other", cost={"generation_credits": 999, "price_source": "button"}))
    r = lg.receipt("Boots1")
    assert r["generation_credits"] == 50 and r["developer_api_usd"] == pytest.approx(0.24) and r["work_s"] == pytest.approx(130.5)
    assert r["subscription"] == ["Tripo Pro, 1450 credits left"] and r["rows"] == 3
    only_usd = Ledger(tmp_path / "u.jsonl")
    only_usd.record(run(stage="image", studio="openrouter", cost={"developer_api_usd": 1.5}))
    assert only_usd.receipt("Boots1")["generation_credits"] == 0, "dollars never leak into credits"


def test_compare_shows_the_settings_and_outputs_that_differ(tmp_path):
    lg = Ledger(tmp_path / "r.jsonl")
    a = lg.record(run(settings={"res": "4K", "pbr": True}, output_hashes=["h1"], seed=7))
    b = lg.record(run(settings={"res": "8K", "pbr": True}, output_hashes=["h2"], seed="not_exposed"))
    c = lg.compare([a["id"], b["id"]])
    assert c["settings_diff"] == {"res": {a["id"]: "4K", b["id"]: "8K"}} and c["output_changed"] is True
    assert c["seed"] == {a["id"]: 7, b["id"]: "not_exposed"}
    with pytest.raises(LedgerError, match="no row"):
        lg.compare([a["id"], "missing"])


def test_the_prompt_run_log_is_a_view_of_the_same_ledger(tmp_path):
    """ONE ledger: prompt runs, ratings and gates are lines in the same file as experiment rows, and neither side is confused by the other's lines."""
    path = tmp_path / "ledger" / "runs.jsonl"
    log, lg = RunLog(path), Ledger(path)
    log.record("j1", prompt="p", model="m", template="t@1.0.0", cost=0.3, service="video_gen", extra={"piece": "Boots1"})
    log.rate("j1", 4)
    exp = lg.record(run(stage="video", studio="openrouter", cost={"developer_api_usd": 0.1}))
    assert [r["job_id"] for r in log.runs()] == ["j1"] and [r["id"] for r in lg.list(piece="Boots1")] == [exp["id"]]
    assert lg.receipt("Boots1")["developer_api_usd"] == pytest.approx(0.4), "the prompt run's dollars count on its piece"
    assert {r["kind"] for r in lg.rows()} == {"run", "rating", "experiment"}


def test_routes_expose_the_ledger_under_the_project_root_and_need_a_token(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "proj"))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        assert http.get("/app/ledger").status_code == 401 and http.post("/app/ledger", json=run()).status_code == 401
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        r = fake.post("/app/ledger", json=run(cost={"generation_credits": 20, "price_source": "button"}))
        assert r.status_code == 200, r.text
        bad = fake.post("/app/ledger", json=run(stage="texture", decision="chosen", by="agent"))
        assert bad.status_code == 422 and "user" in bad.text
        assert fake.get("/app/ledger", params={"piece": "Boots1"}).json()["rows"][0]["id"] == r.json()["id"]
        assert fake.get("/app/ledger/receipt", params={"piece": "Boots1"}).json()["generation_credits"] == 20
        two = fake.post("/app/ledger", json=run(settings={"unwrap": "other"})).json()["id"]
        assert fake.get("/app/ledger/compare", params={"ids": f"{r.json()['id']},{two}"}).json()["settings_diff"]["unwrap"]
    assert (tmp_path / "proj" / "ledger" / "runs.jsonl").exists()


@pytest.mark.anyio
async def test_the_agent_tools_record_as_the_agent_and_cannot_choose_a_spend_result(tmp_path):
    from lampway_server.agent import ledger_tools as LGT
    from lampway_server.agent import tools as T
    from lampway_server.prompts.library import Library
    from lampway_server.prompts.service import PromptService
    svc = PromptService(Library(builtin_dir=Library().dirs["builtin"], user_dir=tmp_path / "u"), RunLog(tmp_path / "runs.jsonl"))
    assert LGT.NAMES <= {t.name for t in T.TOOLS}
    out, err = await LGT.call(svc, "lampway_ledger_record", {"run": run(by="captain", stage="texture", decision="chosen")})
    assert err is True and "user" in out, "an agent claiming by=captain is overridden: it still records as the agent"
    out, err = await LGT.call(svc, "lampway_ledger_record", {"run": run(decision="rejected", reason="blurry", cost={"generation_credits": 30, "price_source": "button"})})
    assert err is False and json.loads(out)["by"] == "agent"
    rec = json.loads((await LGT.call(svc, "lampway_ledger_receipt", {"piece": "Boots1"}))[0])
    assert rec["generation_credits"] == 30 and json.loads((await LGT.call(svc, "lampway_ledger_list", {"piece": "Boots1"}))[0])["rows"][0]["decision"] == "rejected"
