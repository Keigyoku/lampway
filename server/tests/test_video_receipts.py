"""The video providers behind write-ahead receipts: a server killed after OpenRouter accepted the job resumes it by id, downloads once and never posts a second paid request."""
import pytest

from lampway_server import jobreceipts as JR
from lampway_server import videojobs as VJ

from .test_videogen import MP4, wire  # noqa: F401  (the MockTransport fixture)


def hooks_for(store, r):
    class H:
        @staticmethod
        def sending():
            store.mark_pending(r)

        @staticmethod
        def submitted(pid, urls=None):
            store.mark_submitted(r, pid, urls)
    return H


def test_killed_after_the_provider_accepted_the_job_it_resumes_by_id_and_posts_only_once(wire, tmp_path, monkeypatch):
    client, seen, state, ledger = wire
    state["status"] = ["completed"]
    s1 = JR.JobReceipts(tmp_path)
    r, _ = s1.create("openrouter", "heygen/heygen-video-1", {"prompt": "x"}, "vk-1", "user", job_id="j1")
    h = hooks_for(s1, r)
    def die(self, c, job):
        raise SystemExit(9)                                                # the server dies while polling
    with monkeypatch.context() as m:
        m.setattr(type(client), "_wait", die)
        with pytest.raises(SystemExit):
            client.generate("heygen/heygen-video-1", "x", {"resolution": "480p", "duration": 5}, on_sending=h.sending, on_submitted=h.submitted)
    assert len(seen["posts"]) == 1 and s1.get(r["key"])["state"] == "submitted" and s1.get(r["key"])["provider_job_id"] == "job1"

    class System:
        higgs = None
    system = VJ.VideoSystem.__new__(VJ.VideoSystem)
    system.client, system.higgs = client, None
    s2 = JR.JobReceipts(tmp_path, fetchers=system.receipt_fetchers())
    out = s2.reconcile(system.receipt_adapters())
    assert out["completed"] == [r["key"]]
    rec = s2.get(r["key"])
    assert rec["state"] == "downloaded" and rec["outputs"][0]["bytes"] == len(MP4)
    assert len(seen["posts"]) == 1                                         # resumed by id: no second paid POST
    assert seen["gets"] and seen["gets"][-1].startswith("Bearer ")         # the content download carried the provider's authorization


def test_killed_before_the_provider_answered_it_is_unknown_and_nothing_posts_again(wire, tmp_path):
    client, seen, state, _ = wire
    s1 = JR.JobReceipts(tmp_path)
    r, _ = s1.create("openrouter", "heygen/heygen-video-1", {"prompt": "x"}, "vk-2", "user", job_id="j2")
    h = hooks_for(s1, r)
    import httpx
    client.models()                                                        # cache the catalogue, then make the provider die on the paid POST
    def dies(req):
        raise SystemExit(9)
    client._transport = httpx.MockTransport(dies)
    with pytest.raises(SystemExit):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "480p", "duration": 5}, on_sending=h.sending, on_submitted=h.submitted)
    s2 = JR.JobReceipts(tmp_path)
    out = s2.reconcile({})
    assert out["unknown"] == [r["key"]] and seen["posts"] == []


def test_a_refusal_before_the_send_leaves_the_receipt_planned_never_pending(wire, tmp_path):
    client, seen, state, _ = wire
    s = JR.JobReceipts(tmp_path)
    r, _ = s.create("openrouter", "heygen/heygen-video-1", {"prompt": "x"}, "vk-3", "user", job_id="j3")
    h = hooks_for(s, r)
    with pytest.raises(Exception, match="does not take"):
        client.generate("heygen/heygen-video-1", "x", {"resolution": "9999p", "duration": 5}, on_sending=h.sending, on_submitted=h.submitted)
    assert s.get(r["key"])["state"] == "planned" and seen["posts"] == []
