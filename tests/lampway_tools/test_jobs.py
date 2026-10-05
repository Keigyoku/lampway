# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background jobs for the slow tools: the heavy part runs in a thread (a rebuild is minutes; the UI and the agent's
script slot must not block), its result is handed back on the MAIN thread by pump() (the app's timer calls it), because
touching the scene from a thread is not allowed."""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import jobs as J  # noqa: E402


@pytest.fixture(autouse=True)
def fresh():
    J.reset()
    yield
    J.reset()


def wait(job, timeout=5):
    t = time.time()
    while job.state == "running" and time.time() - t < timeout:
        time.sleep(0.01)


def test_a_job_runs_in_a_thread_and_reports_done_with_its_result():
    main = threading.get_ident()
    seen = {}
    job = J.start("rebuild", lambda: seen.update(thread=threading.get_ident()) or {"ok": True})
    wait(job)
    assert job.state == "done" and job.result == {"ok": True} and seen["thread"] != main
    assert J.get(job.id) is job and job.id.startswith("rebuild-")


def test_a_failing_job_is_failed_with_the_error_not_an_exception_in_the_caller():
    def boom():
        raise RuntimeError("no science python")
    job = J.start("rebuild", boom)
    wait(job)
    assert job.state == "failed" and "no science python" in job.error


def test_on_done_runs_once_on_the_pumping_thread_after_the_job_finishes():
    calls = []
    job = J.start("rebuild", lambda: {"mesh": "m"}, on_done=lambda j: calls.append((threading.get_ident(), j.result)))
    wait(job)
    assert calls == []                                       # not from the worker thread
    assert J.pump() == 1
    assert calls == [(threading.get_ident(), {"mesh": "m"})]
    assert J.pump() == 0 and len(calls) == 1


def test_an_on_done_that_raises_marks_the_job_and_does_not_stop_the_pump():
    def bad(j):
        raise ValueError("load failed")
    a = J.start("x", lambda: 1, on_done=bad)
    b = J.start("y", lambda: 2, on_done=lambda j: None)
    wait(a), wait(b)
    assert J.pump() == 2
    assert a.state == "done" and "load failed" in a.finish_error and b.finish_error == ""


def test_a_running_job_is_not_pumped_and_status_lists_it():
    gate = threading.Event()
    job = J.start("slow", lambda: gate.wait(5), on_done=lambda j: None)
    assert J.pump() == 0
    rows = J.status()
    assert rows == [{"id": job.id, "kind": "slow", "state": "running", "seconds": rows[0]["seconds"], "error": "", "finish_error": ""}]
    gate.set()
    wait(job)
    assert J.pump() == 1


def test_only_a_bounded_history_is_kept():
    for i in range(J.KEEP + 5):
        j = J.start("k", lambda: None)
        wait(j)
        J.pump()
    assert len(J.status()) == J.KEEP
