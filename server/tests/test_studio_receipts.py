"""Studio spend jobs behind write-ahead receipts: the hung mark and an interrupted click survive a server restart (specs/mrmak/06-job-receipts.md section 6.6)."""
import pytest

from lampway_server import jobreceipts as JR
from lampway_server.ledger import Ledger

from .test_studio_service import STATE_FRESH, svc

pytestmark = pytest.mark.anyio
HUNG = 'error: no UV mesh arrived within 300 s: HUNG (memory tripo-hung-job-quirk) - reload once, check credits, never re-click\n'


async def run_unwrap(s):
    plan = await s.plan("tripo.uv.unwrap", {}, by="agent")
    return await s.wait((await s.confirm(plan["approval"]["id"], price=20, by="captain"))["id"])


async def test_a_hung_job_is_still_hung_after_a_restart_until_the_user_acknowledges_it(tmp_path):
    rc = tmp_path / "rc"
    s1, _, _ = svc(tmp_path / "a", {"tripo_uv": lambda argv: STATE_FRESH if argv[-1] == "state" else HUNG}, receipts=JR.JobReceipts(rc))
    job = await run_unwrap(s1)
    assert job["state"] == "hung"
    s2, _, _ = svc(tmp_path / "b", {"tripo_uv": STATE_FRESH}, receipts=JR.JobReceipts(rc))              # the server restarted: a new service, the same receipts
    again = await s2.plan("tripo.uv.unwrap", {}, by="agent")
    assert again["state"] == "refused" and "never re-click" in again["reason"]
    s2.acknowledge_hung(job["id"], by="captain")
    assert (await s2.plan("tripo.uv.unwrap", {}, by="agent"))["state"] == "needs_approval"
    assert [r["state"] for r in JR.JobReceipts(rc).list()] == ["abandoned"]


async def test_a_driver_killed_mid_click_is_unknown_after_a_restart_and_blocks_a_second_click(tmp_path):
    import asyncio
    import threading
    rc = tmp_path / "rc"
    release = threading.Event()
    def stuck(argv):
        if argv[-1] == "state" or "--dry-run" in argv or "--plan" in argv:
            return STATE_FRESH
        release.wait(30)                                  # the click is in flight: this "server" never sees it finish
        return 0, "row: 1\n"
    s1, ex1, _ = svc(tmp_path / "a", {"tripo_uv": stuck}, receipts=JR.JobReceipts(rc))
    plan = await s1.plan("tripo.uv.unwrap", {}, by="agent")
    jid = (await s1.confirm(plan["approval"]["id"], price=20, by="captain"))["id"]
    for _ in range(100):
        await asyncio.sleep(0.05)
        if JR.JobReceipts(rc).list()[0]["state"] == "submission_pending":
            break
    [r] = JR.JobReceipts(rc).list()
    assert r["state"] == "submission_pending" and r["model"] == "tripo.uv.unwrap"       # on disk before the click returned
    s2, ex2, _ = svc(tmp_path / "b", {"tripo_uv": STATE_FRESH}, receipts=JR.JobReceipts(rc))     # the restart
    assert JR.JobReceipts(rc).list()[0]["state"] == "submission_unknown"
    refused = await s2.plan("tripo.uv.unwrap", {}, by="agent")
    assert refused["state"] == "refused" and "never re-click" in refused["reason"] and not any("unwrap" in " ".join(c["argv"]) and "--dry-run" not in c["argv"] for c in ex2.calls)
    release.set()
    await asyncio.wait_for(s1.wait(jid), 10)


async def test_a_finished_spend_job_ends_downloaded_with_its_files_hashed_and_one_ledger_row(tmp_path):
    led = Ledger(tmp_path / "ledger" / "runs.jsonl")
    rcs = JR.JobReceipts(tmp_path / "rc", ledger=led)
    s, _, _ = svc(tmp_path / "a", {"tripo_uv": STATE_FRESH, "unwrap": "row: 1\n"}, receipts=rcs)
    job = await run_unwrap(s)
    assert job["state"] == "done"
    [r] = rcs.list()
    assert r["state"] == "downloaded" and r["outputs"][0]["sha256"] and r["provider"] == "studio:tripo" and len(led.rows("job")) == 1
