"""The job queue over write-ahead receipts: nothing paid is sent twice, across crashes and restarts (specs/mrmak/06-job-receipts.md section 10)."""
import asyncio
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from lampway_server import jobreceipts as JR
from lampway_server.jobqueue import ImageOutput, JobQueue
from lampway_server.ledger import Ledger

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class Hub:
    sockets = {}


def make_queue(root, backend):
    return JobQueue({"image_gen": backend}, Hub(), "http://127.0.0.1:1", receipts=JR.JobReceipts(root, ledger=Ledger(Path(root) / "ledger" / "runs.jsonl")))


async def settle(q, job):
    await asyncio.wait_for(job.task, 10)


CHILD = textwrap.dedent('''
    import asyncio, os, sys
    sys.path.insert(0, {server!r})
    from lampway_server import jobreceipts as JR
    from lampway_server.jobqueue import JobQueue
    class Hub: sockets = {{}}
    def backend(model, payload):
        with open({counter!r}, "a") as f: f.write("call\\n")
        os._exit(9)                                           # the server is killed with the paid request in flight
    async def main():
        q = JobQueue({{"image_gen": backend}}, Hub(), "http://127.0.0.1:1", receipts=JR.JobReceipts({root!r}))
        q.submit("image_gen", "default", {{"prompt": "a knight"}}, "client-key-1")
        await asyncio.sleep(30)
    asyncio.run(main())
''')


def test_killing_the_server_mid_job_leaves_an_unknown_receipt_and_no_second_paid_submit(tmp_path):
    counter = tmp_path / "calls.txt"
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(server=str(Path(__file__).resolve().parents[1]), counter=str(counter), root=str(tmp_path)))
    p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 9, p.stderr[-800:]
    assert counter.read_text().count("call") == 1
    store = JR.JobReceipts(tmp_path)
    [r] = store.list()
    assert r["state"] == "submission_pending"                                 # the write-ahead receipt was on disk before the provider was called

    calls = []
    def backend(model, payload):
        calls.append(1)
        return ImageOutput(images=[(PNG, "image/png")])

    async def after_restart():
        q = make_queue(tmp_path, backend)
        out = await q.recover()
        assert out["unknown"] == [r["key"]]
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "client-key-1")            # the Client retries its own key
        await asyncio.sleep(0.2)
        snap = q.snapshot(job)
        assert snap["state"] == "pending" and "Maybe sent" in snap["user_message"] and snap["receipt_state"] == "submission_unknown"
        assert q.get(job.job_id) is job
    asyncio.run(after_restart())
    assert calls == [] and counter.read_text().count("call") == 1              # no second paid submit, ever


def test_a_normal_job_walks_the_receipt_to_downloaded_with_one_ledger_row(tmp_path):
    def backend(model, payload):
        return ImageOutput(images=[(PNG, "image/png")], image_name="x")

    async def go():
        q = make_queue(tmp_path, backend)
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-normal")
        await settle(q, job)
        return job
    job = asyncio.run(go())
    assert job.status == "DONE"
    [r] = JR.JobReceipts(tmp_path).list()
    assert r["state"] in ("downloaded", "result_saved") and [h["state"] for h in r["history"]][:3] == ["planned", "submission_pending", "submitted"] and r["job_id"] == job.job_id
    assert len(Ledger(tmp_path / "ledger" / "runs.jsonl").rows("job")) == 1


def test_a_finished_job_comes_back_after_a_restart_instead_of_a_404(tmp_path):
    def backend(model, payload):
        return ImageOutput(images=[(PNG, "image/png")])

    async def first():
        q = make_queue(tmp_path, backend)
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-keep")
        await settle(q, job)
        return job.job_id
    jid = asyncio.run(first())

    async def second():
        q = make_queue(tmp_path, backend)
        await q.recover()
        job = q.get(jid)
        assert job is not None and job.status == "DONE" and q.snapshot(job)["state"] == "succeeded" and q.snapshot(job)["result"]["recovered"] is True
        assert any(s["job_id"] == jid for s in q.snapshots())
        again = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-keep")
        assert again.job_id == jid
    asyncio.run(second())


def test_a_network_failure_after_pending_is_unknown_and_the_same_key_is_not_sent_again(tmp_path):
    calls = []
    def backend(model, payload):
        calls.append(1)
        raise ConnectionError("the connection dropped after the request went out")

    async def go():
        q = make_queue(tmp_path, backend)
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-net")
        await settle(q, job)
        again = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-net")
        await asyncio.sleep(0.1)
        return job, again
    job, again = asyncio.run(go())
    [r] = JR.JobReceipts(tmp_path).list()
    assert r["state"] == "submission_unknown" and job.status in ("FAILED", "PENDING") and again.job_id == job.job_id and calls == [1]


def test_a_refusal_before_anything_was_sent_is_not_unknown(tmp_path):
    def backend(model, payload):
        raise ValueError("number_of_images must be between 1 and 4")

    async def go():
        q = make_queue(tmp_path, backend)
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-bad")
        await settle(q, job)
    asyncio.run(go())
    [r] = JR.JobReceipts(tmp_path).list()
    assert r["state"] == "provider_error" and r["error_class"] == "not_sent"


def test_an_unresolved_placeholder_is_refused_at_submit_and_no_receipt_is_written(tmp_path):
    from lampway_server.jobqueue import BadJob
    async def go():
        q = make_queue(tmp_path, lambda m, p: ImageOutput(images=[(PNG, "image/png")]))
        with pytest.raises(BadJob, match="Replace placeholder references"):
            q.submit("image_gen", "default", {"prompt": "a {{style}} knight"}, "k-ph")
    asyncio.run(go())
    assert JR.JobReceipts(tmp_path).list() == []


def test_the_receipt_tool_lists_and_shows_without_signed_urls(tmp_path):
    from lampway_server.agent import video_tools as VT

    async def go():
        q = make_queue(tmp_path, lambda m, p: ImageOutput(images=[(PNG, "image/png")]))
        job = q.submit("image_gen", "default", {"prompt": "a knight"}, "k-tool")
        await settle(q, job)
        r = q.receipts.get(job.receipt["key"])
        q.receipts._write({**r, "status_url": "https://x.example.test/s?X-Amz-" "Signature=deadbeef"})
        sysm = type("S", (), {"jobs": q})()
        listed, err = await VT.call(sysm, "lampway_job_receipt", {"action": "list"})
        shown, err2 = await VT.call(sysm, "lampway_job_receipt", {"action": "show", "id": job.job_id})
        missing, err3 = await VT.call(sysm, "lampway_job_receipt", {"action": "show", "id": "nope"})
        return listed, err, shown, err2, err3
    listed, err, shown, err2, err3 = asyncio.run(go())
    assert not err and json.loads(listed)["count"] == 1 and "deadbeef" not in listed + shown and not err2 and err3
