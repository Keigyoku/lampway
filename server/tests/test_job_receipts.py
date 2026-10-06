"""Write-ahead job receipts (specs/mrmak/06-job-receipts.md): the ordering law, exclusive create, resume by id, download hygiene, redaction."""
import json
import multiprocessing
import os
import stat
import threading

import pytest

from lampway_server import jobreceipts as JR
from lampway_server.ledger import Ledger


class FakeProvider:
    """submit/status/result with injectable faults and a call count."""
    def __init__(self, fault=None):
        self.submits, self.fault, self.jobs = 0, fault, {}

    def send(self):
        self.submits += 1
        if self.fault == "crash_after_pending":
            raise SystemExit(9)
        if self.fault == "drop_response":
            raise ConnectionError("the response never came")
        pid = f"job-{self.submits}"
        self.jobs[pid] = "completed"
        return pid, {"status": "https://api.example.test/status/" + pid}

    def status(self, r):
        if self.fault == "forgotten":
            raise LookupError("no such job")
        return self.jobs.get(r["provider_job_id"], "unknown")

    def result(self, r):
        if self.fault == "forgotten":
            raise LookupError("no such job")
        return {"video": {"url": "https://media.example.test/a/clip.mp4"}, "frames_urls": ["https://media.example.test/a/f1.png"]}


def media(url):
    data = b"X" * 100
    return iter([data[:60], data[60:]]), "video/mp4" if url.endswith(".mp4") else "image/png", len(data)


@pytest.fixture
def store(tmp_path):
    return JR.JobReceipts(tmp_path, ledger=Ledger(tmp_path / "ledger" / "runs.jsonl"), fetch=media)


def new(store, key="k1", payload=None):
    r, created = store.create("fal", "model-x", payload or {"prompt": "a"}, key, "user", price={"amount": 1.0, "unit": "usd", "source": "list price"}, job_id="job-uuid")
    return r, created


def test_a_crash_between_pending_and_submitted_becomes_unknown_and_never_resubmits(tmp_path):
    fake = FakeProvider("crash_after_pending")
    s1 = JR.JobReceipts(tmp_path)
    r, _ = new(s1)
    with pytest.raises(SystemExit):
        JR.submit_guarded(s1, r, fake.send)                              # the process "dies" inside the provider call
    s2 = JR.JobReceipts(tmp_path)                                         # a new server over the same folder
    assert s2.get(r["key"])["state"] == "submission_pending"
    out = s2.reconcile({"fal": fake})
    assert out["unknown"] == [r["key"]] and s2.get(r["key"])["state"] == "submission_unknown"
    again, created = new(s2)
    assert created is False and again["state"] == "submission_unknown"
    with pytest.raises(JR.ReceiptError, match="mark_pending needs a planned receipt"):
        s2.mark_pending(again)                                            # even a caller that tries is refused
    assert fake.submits == 1


def test_the_falsifier_a_receipt_written_after_the_provider_call_would_leave_nothing_to_find(tmp_path):
    """The order is the contract: with the provider call FIRST and no receipt, a crash leaves no trace, and a retry sends again (count 2)."""
    fake = FakeProvider("crash_after_pending")
    for _ in range(2):
        try:
            fake.send()
        except SystemExit:
            pass
    assert fake.submits == 2 and JR.JobReceipts(tmp_path).list() == []


def test_a_dropped_response_is_unknown_not_failed_and_not_retried(store):
    fake = FakeProvider("drop_response")
    r, _ = new(store)
    with pytest.raises(ConnectionError):
        JR.submit_guarded(store, r, fake.send)
    assert r["state"] == "submission_unknown" and r["error_class"] == "ConnectionError"
    r2, created = new(store)
    assert created is False and fake.submits == 1


def test_not_sent_is_a_provider_error_the_adapter_knew_nothing_left(store):
    r, _ = new(store)
    def refuse():
        raise JR.NotSent("price over the per-job cap")
    with pytest.raises(JR.NotSent):
        JR.submit_guarded(store, r, refuse)
    assert r["state"] == "provider_error" and r["error_class"] == "not_sent"


def _create_in_process(args):
    root, = args
    r, created = JR.JobReceipts(root).create("fal", "m", {"p": 1}, "race", "user")
    return created


def test_exclusive_create_under_a_race_exactly_one_wins(tmp_path):
    results, lock = [], threading.Lock()
    def worker():
        _r, created = JR.JobReceipts(tmp_path).create("fal", "m", {"p": 1}, "race", "user")
        with lock:
            results.append(created)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results += pool.map(_create_in_process, [(str(tmp_path),)] * 4)
    assert results.count(True) == 1 and len(results) == 12
    assert len(JR.JobReceipts(tmp_path).list()) == 1


def test_restart_while_running_resumes_by_job_id_and_downloads_once(tmp_path):
    fake = FakeProvider()
    led = Ledger(tmp_path / "ledger" / "runs.jsonl")
    s1 = JR.JobReceipts(tmp_path, ledger=led, fetch=media)
    r, _ = new(s1)
    JR.submit_guarded(s1, r, fake.send)
    s1.mark_running(r)                                                    # the server dies here
    s2 = JR.JobReceipts(tmp_path, ledger=led, fetch=media)
    out = s2.reconcile({"fal": fake})
    assert out["completed"] == [r["key"]]
    rec = s2.get(r["key"])
    assert rec["state"] == "downloaded" and len(rec["outputs"]) == 2 and all(o["sha256"] and o["bytes"] == 100 for o in rec["outputs"])
    s3 = JR.JobReceipts(tmp_path, ledger=led, fetch=media)
    s3.reconcile({"fal": fake})
    assets = list((tmp_path / "jobs" / "fal" / r["key"] / "assets").iterdir())
    assert len(assets) == 2 and fake.submits == 1
    assert len([x for x in led.rows("job")]) == 1


def test_the_result_is_saved_before_download_and_survives_the_provider_forgetting(tmp_path):
    fake = FakeProvider()
    calls = {"n": 0}
    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("network down")
        return media(url)
    s = JR.JobReceipts(tmp_path, fetch=flaky)
    r, _ = new(s)
    JR.submit_guarded(s, r, fake.send)
    s.save_result(r, fake.result(r))
    with pytest.raises(ConnectionError):
        s.download(r)
    assert s.get(r["key"])["state"] == "completed" and (tmp_path / "jobs" / "fal" / r["key"] / "result.json").exists()
    forgetful = FakeProvider("forgotten")
    s.reconcile({"fal": forgetful})
    assert s.get(r["key"])["state"] == "downloaded"                       # finished from result.json: the provider no longer knew the job


def test_a_provider_error_inside_a_completed_result_is_not_accepted(store):
    r, _ = new(store)
    JR.submit_guarded(store, r, FakeProvider().send)
    store.save_result(r, {"error": "content policy", "video": {"url": "https://media.example.test/a/x.mp4"}})
    assert r["state"] == "provider_error" and "content policy" in r["error_text"] and r["outputs"] == []
    with pytest.raises(JR.ReceiptError):
        store.download(r)


@pytest.mark.parametrize("url,msg", [("http://media.example.test/a.mp4", "https only"), ("https://user:pw" "@media.example.test/a.mp4", "userinfo"), ("file:///etc/passwd", "https only"),
                                      ("https://x.example.invalid/a.mp4", "example.invalid")])
def test_download_refusals(store, url, msg):
    r, _ = new(store)
    JR.submit_guarded(store, r, FakeProvider().send)
    store.save_result(r, {"ok": True})
    with pytest.raises(JR.ReceiptError, match=msg):
        store.download(r, urls=[url])


def test_a_513_mb_file_is_refused_by_header_and_by_stream(store):
    r, _ = new(store)
    JR.submit_guarded(store, r, FakeProvider().send)
    store.save_result(r, {"ok": True})
    with pytest.raises(JR.ReceiptError, match="exceeds the 512 MB per-file limit; download it separately"):
        store.download(r, urls=["https://media.example.test/big.mp4"], fetch=lambda u: (iter([]), "video/mp4", 513 * 1024 * 1024))


def test_the_part_file_is_never_the_final_name_and_a_leftover_part_is_fetched_again(tmp_path):
    seen = {}
    s = JR.JobReceipts(tmp_path)
    r, _ = new(s)
    JR.submit_guarded(s, r, FakeProvider().send)
    s.save_result(r, {"ok": True})
    d = tmp_path / "jobs" / "fal" / r["key"] / "assets"
    d.mkdir(parents=True, exist_ok=True)
    import hashlib
    url = "https://media.example.test/a/clip.mp4"
    (d / f"01-{hashlib.sha256(url.encode()).hexdigest()[:10]}.mp4.part").write_bytes(b"stale")
    def fetch(url):
        def gen():
            yield b"A" * 10
            seen["during"] = sorted(p.name for p in d.iterdir())
            yield b"B" * 10
        return gen(), "video/mp4", 20
    s.download(r, urls=[url], fetch=fetch)
    names = sorted(p.name for p in d.iterdir())
    final = [n for n in names if n.endswith(".mp4")]
    assert len(final) == 1 and not any(n.endswith(".part") for n in names)
    assert not any(n.endswith(".mp4") for n in seen["during"])            # while it was being written, no file had the final name
    assert (d / final[0]).read_bytes() == b"A" * 10 + b"B" * 10


def test_export_safe_never_contains_a_signed_url_and_the_ledger_row_is_clean(tmp_path):
    led = Ledger(tmp_path / "ledger" / "runs.jsonl")
    s = JR.JobReceipts(tmp_path, ledger=led, fetch=media)
    r, _ = new(s)
    signed = "https://bucket.example.test/o/clip.mp4?X-Amz-" "Signature=deadbeef&X-Amz-Credential=AKIAFAKE"
    JR.submit_guarded(s, r, lambda: ("job-1", {"status": signed, "response": "https://api.example.test/r/1"}))
    safe = JR.export_safe(s.get(r["key"]))
    blob = json.dumps(safe)
    assert "X-Amz-" "Signature" not in blob and "deadbeef" not in blob and safe["response_url"] == "https://api.example.test/r/1" and "status_url" not in safe
    s.save_result(r, {"ok": True})
    s.download(r, urls=[])
    assert "X-Amz-" "Signature" not in json.dumps(led.rows("job")) and "deadbeef" not in json.dumps(led.rows("job"))
    assert JR.export_safe({"api_key": "sk-x", "nested": {"authorization": "Bearer t"}, "ok": 1}) == {"nested": {}, "ok": 1}


def test_receipt_files_are_0600_and_their_folders_0700(store, tmp_path):
    r, _ = new(store)
    JR.submit_guarded(store, r, FakeProvider().send)
    d = tmp_path / "jobs" / "fal" / r["key"]
    assert stat.S_IMODE((d / "receipt.json").stat().st_mode) == 0o600 and stat.S_IMODE(d.stat().st_mode) == 0o700 and stat.S_IMODE((tmp_path / "jobs").stat().st_mode) == 0o700


def test_an_unresolved_placeholder_in_a_rendered_payload_is_refused_before_anything_is_written(store, tmp_path):
    for payload in ({"prompt": "a {{style}} knight"}, {"image_url": "https://example.invalid/ref.png"}):
        with pytest.raises(JR.ReceiptError, match="Replace placeholder references before submitting"):
            store.create("fal", "m", payload, "kk", "user")
    assert store.list() == []


def test_unknown_can_only_be_acknowledged_or_linked_by_the_user(store):
    r, _ = new(store)
    with pytest.raises(ConnectionError):
        JR.submit_guarded(store, r, FakeProvider("drop_response").send)
    with pytest.raises(JR.ReceiptError, match="only the user"):
        store.acknowledge(r, "agent")
    with pytest.raises(JR.ReceiptError, match="only the user"):
        store.link(r, "job-9", "agent")
    store.link(r, "job-9", "user")
    assert r["state"] == "submitted" and r["provider_job_id"] == "job-9"
    r2, _ = new(store, "k2")
    with pytest.raises(ConnectionError):
        JR.submit_guarded(store, r2, FakeProvider("drop_response").send)
    store.acknowledge(r2, "user")
    assert r2["state"] == "abandoned"


def test_the_jobs_folder_cap_refuses_a_new_job_and_never_prunes(tmp_path):
    s = JR.JobReceipts(tmp_path, cap_bytes=1)
    s.create("fal", "m", {"p": 1}, "a", "user")                       # the first fits (nothing on disk yet)
    with pytest.raises(JR.ReceiptError, match="jobs folder is over its cap: delete or move finished jobs"):
        s.create("fal", "m", {"p": 2}, "b", "user")
    assert len(s.list()) == 1


def test_illegal_transitions_are_refused_and_the_key_is_stable():
    assert JR.key_for("fal", "m", {"a": 1, "b": 2}, "user") == JR.key_for("fal", "m", {"b": 2, "a": 1}, "user")
    assert JR.key_for("fal", "m", {}, "user", "client-key") == JR.key_for("higgsfield", "z", {"x": 1}, "agent", "client-key")


@pytest.mark.parametrize("secret", ["sk-" "or-v1-abcdef0123456789", "ghp_" + "a1" * 18, "AKIA" + "ABCDEFGHIJKLMNOP", "AIza" + "x" * 30, "https://user:" "pw" "@api.invalid/x"])
def test_a_secret_prefixed_value_or_userinfo_url_is_refused_in_the_provider_model_and_ledger_fields(tmp_path, secret):
    s = JR.JobReceipts(tmp_path)
    for provider, model in ((secret, "m"), ("fal", secret)):
        with pytest.raises(JR.ReceiptError, match="looks like a secret"):
            s.create(provider, model, {"p": 1}, "kk", "user")
    led = Ledger(tmp_path / "ledger" / "runs.jsonl")
    from lampway_server.ledger import LedgerError
    with pytest.raises(LedgerError, match="looks like a secret"):
        led.record({"piece": "P", "stage": "image", "studio": "openrouter", "settings": {"note": secret}})
    with pytest.raises(LedgerError, match="looks like a secret"):
        led.record({"piece": "P", "stage": "image", "studio": "openrouter", "reason": f"called with {secret} today"})
    assert led.rows() == []
    led.record({"piece": "P", "stage": "image", "studio": "openrouter", "reason": "a normal row, sk-less"})
