"""slot_register (specs/wiki/slot_register.md): a typed, dated, append-only register of every model or Studio slot: its evidence class, whether a driver exists
(checked against the Studio action catalog), the last read-back and its price. It answers 'what can actually run now'."""

import asyncio
import json

import pytest

from lampway_server import slots as SL
from lampway_server.agent import orphan_server_tools as OST
from lampway_server.agent import tools as T


def test_driver_flag_must_match_the_catalog(tmp_path):
    reg = SL.SlotRegister(tmp_path / "slots.jsonl")
    with pytest.raises(SL.SlotError, match="no catalog action named 'cubepart.split'"):
        reg.record("cubepart.split", {"evidence": "repo", "driver_exists": True, "source": "wiki concepts/x.md:1", "by": "agent"})
    row = reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "price_read_back": 100, "read_back_at": "2026-10-05",
                                    "source": "studios/actions.py", "by": "agent"})
    assert row["slot"] == "tripo.mesh" and row["driver_exists"] is True


def test_old_rows_are_stale(tmp_path):
    reg = SL.SlotRegister(tmp_path / "slots.jsonl", today="2026-12-01")
    reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "price_read_back": 100, "read_back_at": "2026-10-05", "source": "s", "by": "agent"})
    reg.record("meshy.text_to_3d", {"evidence": "official_docs", "driver_exists": True, "read_back_at": "2026-11-25", "source": "s", "by": "agent"})
    rows = {r["slot"]: r for r in reg.list()}
    assert rows["tripo.mesh"]["stale"] is True and rows["meshy.text_to_3d"]["stale"] is False
    assert rows["tripo.mesh"]["stale_policy_days"] == 30


def test_research_lead_is_never_runnable(tmp_path):
    reg = SL.SlotRegister(tmp_path / "slots.jsonl")
    rows = {r["slot"]: r for r in reg.list()}
    for lead in ("arbor", "kaininja", "worldsculpt", "hktex", "trellis2"):
        assert rows[lead]["runnable"] is False and rows[lead]["evidence"] in ("paper", "repo", "demo_shell"), rows[lead]
    with pytest.raises(SL.SlotError, match="research"):
        reg.record("tripo.mesh", {"evidence": "paper", "driver_exists": True, "source": "s", "by": "agent"})


def test_the_seed_holds_the_six_studio_families_and_ten_research_leads_each_with_a_source():
    reg = SL.SlotRegister("/nonexistent/never-written.jsonl")
    rows = reg.list()
    families = {r["family"] for r in rows if r["kind"] == "studio"}
    assert {"tripo", "meshy", "hi3d", "hyper3d", "higgsfield", "openrouter"} <= families
    leads = [r for r in rows if r["kind"] == "research"]
    assert len(leads) >= 10 and all(r["source"] and r["evidence"] for r in rows)
    assert all(r["by"] == "rule" for r in rows)


def test_append_only_a_correction_is_a_new_row_and_the_latest_wins(tmp_path):
    p = tmp_path / "slots.jsonl"
    reg = SL.SlotRegister(p)
    reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "price_read_back": 100, "read_back_at": "2026-10-05", "source": "s", "by": "agent"})
    reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "price_read_back": 120, "read_back_at": "2026-10-06", "source": "s", "by": "captain",
                              "eligibility": "Pro plan"})
    lines = p.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["price_read_back"] == 100
    assert reg.show("tripo.mesh")["price_read_back"] == 120 and len(reg.show("tripo.mesh")["history"]) == 3   # the seed row and both records


def test_only_the_captain_states_eligibility_and_expire_marks_the_read_back_gone(tmp_path):
    reg = SL.SlotRegister(tmp_path / "slots.jsonl")
    with pytest.raises(SL.SlotError, match="eligibility is the user's"):
        reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "eligibility": "Pro", "source": "s", "by": "agent"})
    reg.record("tripo.mesh", {"evidence": "local_measured", "driver_exists": True, "price_read_back": 100, "read_back_at": "2026-10-05", "source": "s", "by": "agent"})
    row = reg.expire("tripo.mesh", by="agent")
    assert row["read_back_at"] is None and row["expired"] is True and reg.show("tripo.mesh")["runnable"] is False


def test_the_agent_tool_lists_and_records_through_the_register(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    assert "lampway_slot_register" in T.TOOL_NAMES
    with pytest.raises(T.UnknownTool, match="runs on the server"):
        T.script_for("lampway_slot_register", {"action": "list"})
    text, err = asyncio.run(OST.call(None, "lampway_slot_register", {"action": "record", "slot": "meshy.text_to_3d",
                                                                      "row": {"evidence": "official_docs", "driver_exists": True, "source": "s", "by": "captain"}}))
    assert not err, text
    assert json.loads(text)["row"]["by"] == "agent", "the agent records as the agent, whatever it claims"
    text, err = asyncio.run(OST.call(None, "lampway_slot_register", {"action": "list"}))
    assert not err and any(r["slot"] == "meshy.text_to_3d" for r in json.loads(text)["rows"])
    assert (tmp_path / "ledger" / "slots.jsonl").exists()
