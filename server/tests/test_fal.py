"""fal_gateway (specs/mrmak/12): a fal queue provider behind the job receipts, built in full against a FAKE transport (the REST paths are [UNVERIFIED] until the user's key allows a live
test: that test is a needs_key skip, never a failure). Every spend is the user's click: the gateway plans, it never confirms."""
import json
import os

import httpx
import pytest

from lampway_server import fal as F
from lampway_server import jobreceipts as JR
from lampway_server.ledger import Ledger

ENDPOINT = "fal-ai/nano-banana-pro"
SCHEMA = {"components": {"schemas": {"NanoInput": {"properties": {"prompt": {"type": "string"}, "image_urls": {"type": "array"}, "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9"]}}, "required": ["prompt"]},
                                       "NanoOutput": {"properties": {"images": {"type": "array"}}}}}}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
SIGNED = "https://v3.fal.media/files/x/out.png?X-Am" "z-Signature=deadbeef"


class Fake:
    """A fake queue: records every request, with injectable faults."""

    def __init__(self):
        self.requests, self.fault, self.status_seq, self.price = [], None, ["IN_QUEUE", "IN_PROGRESS", "COMPLETED"], {"unit_price": 0.039, "unit": "image", "currency": "USD"}
        self.result = {"images": [{"url": "https://v3.fal.media/files/x/out.png"}]}
        self.polls = 0

    def handler(self, request: httpx.Request):
        self.requests.append(request)
        path = request.url.path
        if self.fault == "drop" and request.method == "POST" and path.endswith(ENDPOINT):
            raise httpx.ReadTimeout("no response")
        if request.method == "GET" and "openapi" in str(request.url):
            return httpx.Response(200, json=SCHEMA)
        if request.method == "GET" and "pricing" in str(request.url):
            return httpx.Response(200, json={"prices": [{"endpoint_id": ENDPOINT, **self.price}]} if self.price else {"prices": []})
        if request.method == "POST" and path.endswith(ENDPOINT):
            return httpx.Response(200, json={"request_id": "req-1", "status_url": f"https://queue.fal.run/{ENDPOINT}/requests/req-1/status", "response_url": f"https://queue.fal.run/{ENDPOINT}/requests/req-1",
                                             "cancel_url": f"https://queue.fal.run/{ENDPOINT}/requests/req-1/cancel"})
        if request.method == "GET" and path.endswith("/status"):
            st = self.status_seq[min(self.polls, len(self.status_seq) - 1)]
            self.polls += 1
            return httpx.Response(200, json={"status": st})
        if request.method == "GET" and path.endswith("/requests/req-1"):
            return httpx.Response(200, json=self.result)
        if request.method == "POST" and "storage/upload/initiate" in str(request.url):
            return httpx.Response(200, json={"upload_url": "https://storage.fal.run/put/abc", "file_url": "https://v3.fal.media/files/up/ref.png"})
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(404, json={"detail": "no route"})


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "Key abcdef0123456789")
    fake = Fake()
    receipts = JR.JobReceipts(tmp_path, ledger=Ledger(tmp_path / "ledger" / "runs.jsonl"), fetch=lambda u: (iter([PNG]), "image/png", len(PNG)))
    client = F.FalClient(root=tmp_path, receipts=receipts, transport=httpx.MockTransport(fake.handler), max_job_usd=2.0)
    return client, fake, receipts, tmp_path


def test_a_dry_run_opens_no_socket_and_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "abc")
    def boom(request):
        raise AssertionError("a dry run must not touch the network")
    client = F.FalClient(root=tmp_path, receipts=JR.JobReceipts(tmp_path), transport=httpx.MockTransport(boom))
    out = client.submit(ENDPOINT, {"prompt": "a knight"}, dry_run=True)
    assert out["dry_run"] is True and out["would_send"]["endpoint"] == ENDPOINT and out["state"] == "planned"


def test_input_fields_are_checked_against_the_schema_before_any_price_card(stack):
    client, fake, _r, _t = stack
    with pytest.raises(F.FalError, match="does not take 'resolution': it takes"):
        client.plan(ENDPOINT, {"prompt": "x", "resolution": "4k"})
    with pytest.raises(F.FalError, match="needs 'prompt'"):
        client.plan(ENDPOINT, {})
    with pytest.raises(F.FalError, match="aspect_ratio"):
        client.plan(ENDPOINT, {"prompt": "x", "aspect_ratio": "7:3"})
    assert not any("pricing" in str(r.url) for r in fake.requests)                        # the wrong field never reached the price read
    ok = client.plan(ENDPOINT, {"prompt": "x", "aspect_ratio": "16:9"})
    assert ok["state"] == "needs_approval" and ok["price"]["amount"] == pytest.approx(0.039) and ok["price"]["source"] == "fal get_pricing" and ok["price"]["unit"] == "USD per image"


def test_an_agent_origin_cannot_confirm_the_plan_returns_needs_approval_and_nothing_is_sent(stack):
    client, fake, receipts, _t = stack
    out = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=False, origin="agent")
    assert out["state"] == "needs_approval" and receipts.list() == []
    assert not any(r.method == "POST" and r.url.path.endswith(ENDPOINT) for r in fake.requests)


def test_a_price_without_a_source_and_an_over_cap_price_are_refused_without_a_request(stack):
    client, fake, _r, _t = stack
    fake.price = None
    with pytest.raises(F.FalError, match="price .* refused|no price"):
        client.plan(ENDPOINT, {"prompt": "x"})
    fake.price = {"unit_price": 5.0, "unit": "image", "currency": "USD"}
    posts_before = len([r for r in fake.requests if r.method == "POST"])
    with pytest.raises(F.FalError, match="over the per-job cap of \\$2.00"):
        client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True)
    assert len([r for r in fake.requests if r.method == "POST"]) == posts_before


def test_submit_writes_the_receipt_first_and_a_dropped_response_is_unknown_never_resubmitted(stack):
    client, fake, receipts, _t = stack
    fake.price = {"unit_price": 0.039, "unit": "image", "currency": "USD"}
    fake.fault = "drop"
    with pytest.raises(httpx.ReadTimeout):
        client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-1")
    [r] = receipts.list()
    assert r["state"] == "submission_unknown" and r["provider"] == "fal" and r["model"] == ENDPOINT
    fake.fault = None
    again = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-1")
    assert again["already_exists"] is True and again["state"] == "submission_unknown"
    assert len([x for x in fake.requests if x.method == "POST" and x.url.path.endswith(ENDPOINT)]) == 1


def test_status_mapping_then_result_downloads_once_and_writes_ledger_rows(stack):
    client, fake, receipts, tmp = stack
    sub = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-2")
    assert sub["state"] == "submitted" and sub["provider_job_id"] == "req-1"
    r = receipts.get(sub["key"])
    ad = F.FalAdapter(client)
    assert [ad.status(r) for _ in range(3)] == ["queued", "running", "completed"]
    out = client.result(sub["key"])
    assert out["state"] == "downloaded" and len(out["outputs"]) == 1
    again = client.result(sub["key"])
    assert again["state"] == "downloaded" and len(list((tmp / "jobs" / "fal" / sub["key"] / "assets").iterdir())) == 1
    assert len(Ledger(tmp / "ledger" / "runs.jsonl").rows("job")) == 1
    unknown = F.map_status({"status": "WEIRD"})
    assert unknown == "unknown"


def test_an_error_inside_a_completed_result_is_provider_error_not_accepted(stack):
    client, fake, receipts, _t = stack
    fake.result = {"error": "content policy", "images": []}
    fake.status_seq = ["COMPLETED"]
    sub = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-3")
    out = client.result(sub["key"])
    assert out["state"] == "provider_error" and "content policy" in out["error_text"]


def test_an_upload_is_reused_by_hash_and_other_bytes_at_the_same_path_are_refused(stack):
    client, fake, _r, tmp = stack
    p = tmp / "ref.png"
    p.write_bytes(PNG)
    a = client.upload(str(p))
    b = client.upload(str(p))
    assert a["reused"] is False and b["reused"] is True and a["url_hash"] == b["url_hash"] and "http" not in json.dumps(a)       # the URL is never printed
    assert len([r for r in fake.requests if r.method == "PUT"]) == 1
    p.write_bytes(PNG + b"changed")
    with pytest.raises(F.FalError, match="changed since it was uploaded"):
        client.upload(str(p))
    copy = tmp / "copy.png"
    copy.write_bytes(PNG)
    assert client.upload(str(copy))["reused"] is True                                    # the same bytes at another path are reused
    with pytest.raises(F.FalError, match="outside the project root"):
        client.upload("/etc/hostname")


def test_references_are_uploaded_and_placed_in_the_field_the_schema_names(stack):
    client, fake, _r, tmp = stack
    (tmp / "ref.png").write_bytes(PNG)
    sub = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, references=["ref.png"], idempotency_key="k-4")
    body = json.loads([r for r in fake.requests if r.method == "POST" and r.url.path.endswith(ENDPOINT)][0].content)
    assert body["image_urls"] == ["https://v3.fal.media/files/up/ref.png"] and sub["state"] == "submitted"


@pytest.mark.parametrize("raw", ["Key abcdef0123456789", "Bearer abcdef0123456789", "abcdef0123456789"])
def test_the_key_is_stripped_of_its_prefix_sent_as_authorization_key_and_never_logged_or_stored(tmp_path, monkeypatch, raw, caplog):
    monkeypatch.setenv("FAL_KEY", raw)
    fake = Fake()
    receipts = JR.JobReceipts(tmp_path, fetch=lambda u: (iter([PNG]), "image/png", len(PNG)))
    client = F.FalClient(root=tmp_path, receipts=receipts, transport=httpx.MockTransport(fake.handler))
    with caplog.at_level("DEBUG"):
        client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-5")
    assert all(r.headers["authorization"] == "Key abcdef0123456789" for r in fake.requests)
    blob = caplog.text + "\n".join(p.read_text(errors="replace") for p in (tmp_path / "jobs").rglob("*.json"))
    assert "abcdef0123456789" not in blob
    monkeypatch.delenv("FAL_KEY")
    with pytest.raises(F.FalError, match="no fal key: set FAL_KEY in the environment or a key file"):
        F.FalClient(root=tmp_path, receipts=receipts, transport=httpx.MockTransport(fake.handler)).submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True)


def test_an_sdk_style_error_body_never_reaches_the_message(stack):
    client, fake, _r, _t = stack
    def leaky(request):
        return httpx.Response(500, json={"detail": f"upstream failed for {SIGNED} with key abcdef0123456789"})
    client2 = F.FalClient(root=_t, receipts=_r, transport=httpx.MockTransport(leaky))
    with pytest.raises(F.FalError) as e:
        client2.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, idempotency_key="k-6")
    assert "deadbeef" not in str(e.value) and "abcdef0123456789" not in str(e.value) and "HTTP 500" in str(e.value)


def test_fal_refuses_to_register_without_the_receipt_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "abc")
    with pytest.raises(F.FalError, match="fal needs job receipts: a paid fal job must survive a restart"):
        F.FalClient(root=tmp_path, receipts=None)


@pytest.mark.skipif(not os.environ.get("FAL_KEY_LIVE"), reason="needs_key: set FAL_KEY_LIVE (the user's own key) to run the live fal test; skipped, never failed")
def test_live_schema_and_price_for_a_real_endpoint(tmp_path):
    client = F.FalClient(root=tmp_path, receipts=JR.JobReceipts(tmp_path), key=os.environ["FAL_KEY_LIVE"])
    assert client.schema("fal-ai/flux/schnell")["input"]


def test_an_agent_that_claims_confirmed_is_still_only_planned(stack):
    client, fake, receipts, _t = stack
    out = client.submit(ENDPOINT, {"prompt": "x"}, dry_run=False, confirmed=True, origin="agent")
    assert out["state"] == "needs_approval" and receipts.list() == []
    assert not any(r.method == "POST" and r.url.path.endswith(ENDPOINT) for r in fake.requests)
