# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""F16: a UI action whose outcome lands after the caller's deadline is finished and recorded, not abandoned.

The caller still gets its bounded answer (outcome_unknown) at the response deadline, but an action whose input
is already being delivered (claimed in the receipt journal) runs on to its end under LATE_OUTCOME_LIMIT, and its
durable receipt then says succeeded or failed, so lampway_ui_call_status returns the real outcome. A genuine
cancellation (disconnect, undo, a file load) still aborts as before, and so does the hard ceiling."""

import threading
import time
from uuid import uuid4

import pytest

from mixar.modules.common.ui_control import constants
from mixar.modules.common.ui_control.core import service
from mixar.modules.common.ui_control.core.receipts import Receipts


@pytest.fixture
def pump(monkeypatch, tmp_path):
    receipts = Receipts(tmp_path / "receipts.sqlite")
    monkeypatch.setattr(service, "_receipts", receipts)
    monkeypatch.setattr(service, "_registered", True)
    monkeypatch.setattr(service, "_active", None)
    monkeypatch.setattr(service, "_eligible", lambda: None)
    monkeypatch.setattr(service.ownership, "active", lambda: False)
    monkeypatch.setattr(service.ownership, "release", lambda *a, **k: None)
    monkeypatch.setattr(service.observe, "invalidate", lambda: None)
    yield receipts
    receipts.close()


def _claimed_act(receipts, deadline, ceiling, steps):
    call_id = str(uuid4())
    receipts.claim(call_id, receipts.digest("", "mixar_ui_act", {}))
    req = service.Request(str(uuid4()), "mixar_ui_act", {}, call_id, "", deadline, ceiling=ceiling)
    req.claimed = True

    def run():
        for _ in range(steps):
            yield 0.02
        return {"input_delivered": True}, []
    service._active = (req, run())
    return req


def _drain(req, limit=50):
    for _ in range(limit):
        service._pump()
        if req.done.is_set():
            return
    raise AssertionError("the pump never finished the request")


def test_a_claimed_action_past_its_response_deadline_finishes_and_its_receipt_records_the_outcome(pump):
    now = time.monotonic()
    req = _claimed_act(pump, deadline=now - 1, ceiling=now + 60, steps=3)
    _drain(req)
    assert pump.status(req.call_id)["status"] == "succeeded"
    assert req.result["isError"] is False


@pytest.mark.parametrize("why", ["cancelled", "ceiling"])
def test_a_genuine_cancellation_or_the_hard_ceiling_still_aborts_a_claimed_action(pump, why):
    now = time.monotonic()
    req = _claimed_act(pump, deadline=now - 1, ceiling=now + 60 if why == "cancelled" else now - 1, steps=3)
    if why == "cancelled":
        req.cancelled.set()
    _drain(req)
    assert pump.status(req.call_id)["status"] == "outcome_unknown"
    assert req.result["isError"] is True


def test_an_unclaimed_request_still_stops_at_its_response_deadline(pump):
    now = time.monotonic()
    req = service.Request(str(uuid4()), "mixar_ui_act", {}, str(uuid4()), "", now - 1, ceiling=now + 60)
    service._active = (req, (step for step in (0.02,)))
    _drain(req)
    assert req.result["isError"] is True and pump.status(req.call_id)["status"] == "unavailable"


def test_the_caller_timeout_leaves_a_claimed_action_running_and_names_the_status_call(pump, monkeypatch):
    monkeypatch.setattr(service, "ACTION_TIMEOUT", 0.05)
    monkeypatch.setattr(service.schema, "validate", lambda name, args: None)
    monkeypatch.setattr(service, "_queue", service.queue.Queue(constants.MAX_PENDING))
    monkeypatch.setattr(service, "_requests", {})
    taken = []

    def main_thread_claims_it():                 # the pump took the request and started delivering its input
        req = service._queue.get(timeout=5)
        req.claimed = True
        taken.append(req)
    worker = threading.Thread(target=main_thread_claims_it)
    worker.start()
    call_id = str(uuid4())
    answer = service.submit(str(uuid4()), "mixar_ui_act", {"context": "c", "target": "t", "action": "click"}, call_id)
    worker.join(5)
    result = answer["structuredContent"]["result"]
    assert answer["isError"] is True and result["error_type"] == "outcome_unknown"
    assert not taken[0].cancelled.is_set()
    assert result["receipt_status"] == "accepted"
    assert "lampway_ui_call_status" in result["next_step"] and call_id in result["next_step"]
    assert taken[0].ceiling - taken[0].deadline == pytest.approx(constants.LATE_OUTCOME_LIMIT - service.ACTION_TIMEOUT)


@pytest.mark.parametrize("name", ["mixar_scene_new", "mixar_scene_switch", "mixar_project_open", "mixar_ui_observe"])
def test_only_a_native_ui_action_gets_a_late_outcome_ceiling(pump, monkeypatch, name):
    monkeypatch.setattr(service.schema, "validate", lambda name, args: None)
    monkeypatch.setattr(service, "ACTION_TIMEOUT", 0.05)
    monkeypatch.setattr(service, "_queue", service.queue.Queue(constants.MAX_PENDING))
    monkeypatch.setattr(service, "_requests", {})
    monkeypatch.setattr(service._receipts, "prior", lambda *a: None)
    service.submit(str(uuid4()), name, {}, str(uuid4()))
    assert service._queue.get_nowait().ceiling is None


def test_a_caller_timeout_before_the_claim_still_cancels(pump, monkeypatch):
    monkeypatch.setattr(service, "ACTION_TIMEOUT", 0.05)
    monkeypatch.setattr(service.schema, "validate", lambda name, args: None)
    monkeypatch.setattr(service, "_queue", service.queue.Queue(constants.MAX_PENDING))
    monkeypatch.setattr(service, "_requests", {})
    answer = service.submit(str(uuid4()), "mixar_ui_act", {"context": "c", "target": "t", "action": "click"}, str(uuid4()))
    req = service._queue.get_nowait()
    assert answer["isError"] is True and req.cancelled.is_set()
    assert "receipt_status" not in answer["structuredContent"]["result"]
