# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cancellation joins the owned worker and prevents post-cancel publication."""
import asyncio
import json
import threading

from lampway_server.agent import motion_tools as MT


def test_cancelled_call_joins_worker_and_prevents_vault_filing(tmp_path, monkeypatch):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    filings = []
    def render(*args, **kwargs):
        started.set()
        release.wait()
        try:
            if kwargs.get("cancel") is not None:
                kwargs["cancel"].check()
            return {"ok": True, "out_dir": "out"}
        finally:
            finished.set()
    monkeypatch.setattr(MT.M, "render", render)
    monkeypatch.setattr(MT.E, "require", lambda: None)
    monkeypatch.setattr(MT.R, "file_in_vault", lambda *a, **kw: filings.append(True))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "receipt.json").write_text("{}")
    async def run():
        task = asyncio.create_task(MT.call(object(), tmp_path, MT.NAME, {"html": "scene", "name": "cancel"}, capture=lambda: None))
        await asyncio.to_thread(started.wait)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        result, error = await task
        assert finished.is_set(), "the result must await owned worker termination"
        assert error and json.loads(result)["cancelled"] is True
        assert filings == [], "cancelled worker must not begin Vault filing"
    try:
        asyncio.run(run())
    finally:
        release.set()
        finished.wait()


def test_cancellation_reports_committed_assets_without_new_filing(tmp_path, monkeypatch):
    from lampway_server.motion.cancellation import checkpoint
    started, release = threading.Event(), threading.Event()
    asset = {"id": "already-committed"}
    def work(vault, root, arguments, capture, cancel):
        cancel.record_assets([asset])
        started.set()
        release.wait()
        checkpoint(cancel)
    monkeypatch.setattr(MT, "_work", work)
    async def run():
        task = asyncio.create_task(MT.call(None, tmp_path, MT.NAME, {"html": "x", "name": "cancel"}))
        await asyncio.to_thread(started.wait)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        text, error = await task
        assert error
        assert json.loads(text)["vault"] == {"assets": [asset], "filed": False, "partial": True, "spooled": False}
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_cancel_interrupts_owned_encoder_and_leaves_other_process_alive(tmp_path):
    import subprocess
    import sys
    from lampway_server.motion import encode as E
    from lampway_server.motion.cancellation import Cancellation, MotionCancelled
    cancel = Cancellation()
    other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(600)"], start_new_session=True)
    encoder = E.Encoder([sys.executable, "-c", "import time;time.sleep(600)"], cancel=cancel)
    try:
        cancel.cancel()
        encoder.proc.wait(timeout=5)
        import pytest
        with pytest.raises(MotionCancelled):
            encoder.write(b"frame")
        assert other.poll() is None, "cancellation may terminate only processes owned by this call"
    finally:
        encoder.abort()
        other.kill()
        other.wait()


def test_cancel_real_chromium_blocked_setup(tmp_path, monkeypatch):
    import os
    import pytest
    from lampway_server.motion import frames as F
    from lampway_server.motion.cancellation import Cancellation, MotionCancelled
    binary = os.environ.get("LAMPWAY_CHROMIUM")
    if not binary or not os.path.isfile(binary):
        pytest.skip("set LAMPWAY_CHROMIUM; owned-browser cancellation UNVERIFIED")
    monkeypatch.setattr(F, "CHROME_FLAGS", [*F.CHROME_FLAGS, "--no-sandbox"])
    scene = tmp_path / "scene"
    scene.mkdir()
    entry = scene / "index.html"
    entry.write_text("<script>window.__setup=()=>new Promise(()=>{});window.__frame=()=>{};</script>")
    cancel = Cancellation()
    browser = F.Chromium(binary, tmp_path / "browser")
    browser.cancel = cancel
    browser.open(entry, 32, 32)
    started, done = threading.Event(), threading.Event()
    errors = []
    original_send = browser.cdp.send
    def send(method, *args, **kwargs):
        if method == "Runtime.evaluate":
            started.set()
        return original_send(method, *args, **kwargs)
    browser.cdp.send = send
    def blocked_setup():
        try:
            browser.setup()
        except Exception as exc:
            errors.append(exc)
        finally:
            browser.close()
            done.set()
    worker = threading.Thread(target=blocked_setup)
    try:
        worker.start()
        started.wait()
        cancel.cancel()
        worker.join(timeout=5)
        assert done.is_set() and len(errors) == 1 and isinstance(errors[0], MotionCancelled)
        assert browser.proc.poll() is not None
    finally:
        cancel.cancel()
        from lampway_server.motion.cancellation import kill_owned
        kill_owned(browser.proc)
        worker.join()
        browser.close()


def test_cancel_during_frame_stops_probe_preserves_existing_assets(tmp_path):
    import pytest
    from lampway_server import motion as M
    from lampway_server.motion.cancellation import Cancellation, MotionCancelled
    from .fake_motion import FakeCapture
    cancel = Cancellation()
    made = []
    class Capture(FakeCapture):
        def frame(self, time):
            png = super().frame(time)
            cancel.cancel()
            return png
    def fresh():
        cap = Capture(duration_s=1)
        made.append(cap)
        return cap
    scene = tmp_path / "motion" / "scenes" / "cancel"
    scene.mkdir(parents=True)
    (scene / "index.html").write_text("synthetic fake scene")
    existing = tmp_path / "user-video.mp4"
    existing.write_bytes(b"existing user asset")
    with pytest.raises(MotionCancelled):
        M.render(tmp_path, {"scene": "motion/scenes/cancel", "fps": 10, "width": 32, "height": 32}, fresh, cancel=cancel)
    assert len(made) == 1 and made[0].closed
    assert not list((tmp_path / "motion" / "out").rglob("receipt.json"))
    assert existing.read_bytes() == b"existing user asset"
    assert list((tmp_path / "motion" / "out").iterdir()), "retain interrupted render evidence"


def test_cancel_interrupts_encoder_blocked_finish():
    import sys
    from lampway_server.motion import encode as E
    from lampway_server.motion.cancellation import Cancellation, MotionCancelled
    cancel = Cancellation()
    encoder = E.Encoder([sys.executable, "-c", "import time;time.sleep(600)"], cancel=cancel)
    started = threading.Event()
    stderr = encoder.proc.stderr
    class ReadGate:
        def read(self):
            started.set()
            return stderr.read()
        def close(self):
            stderr.close()
    encoder.proc.stderr = ReadGate()
    errors = []
    def finish():
        try:
            encoder.finish()
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=finish)
    try:
        worker.start()
        started.wait()
        cancel.cancel()
        worker.join(timeout=5)
        assert not worker.is_alive(), "cancellation must unblock encoder stderr/exit waiting"
        assert len(errors) == 1 and isinstance(errors[0], MotionCancelled)
        assert encoder.proc.poll() is not None
    finally:
        encoder.abort()
        worker.join()


def test_repeated_cancellation_cannot_abandon_worker(tmp_path, monkeypatch):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def work(vault, root, arguments, capture, cancel):
        started.set()
        release.wait()
        try:
            cancel.check()
        finally:
            finished.set()
    monkeypatch.setattr(MT, "_work", work)
    async def run():
        task = asyncio.create_task(MT.call(None, tmp_path, MT.NAME, {"html": "x", "name": "cancel"}))
        await asyncio.to_thread(started.wait)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        text, error = await task
        assert error and json.loads(text)["cancelled"] and finished.is_set()
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_admitted_commit_can_finish_but_cancellation_rejects_next_transaction():
    from lampway_server.motion.cancellation import Cancellation, MotionCancelled
    cancel = Cancellation()
    started, release = threading.Event(), threading.Event()
    commits, errors = [], []
    def admitted():
        started.set()
        release.wait()
        commits.append("first")
        cancel.record_assets([{"id": "first"}])
    def worker():
        cancel.commit_owned(admitted)
        try:
            cancel.commit_owned(lambda: commits.append("second"))
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=worker)
    try:
        thread.start()
        started.wait()
        cancel.cancel()
        release.set()
        thread.join()
        assert commits == ["first"]
        assert len(errors) == 1 and isinstance(errors[0], MotionCancelled)
        assert cancel.snapshot_filing() == {"assets": [{"id": "first"}], "filed": False, "partial": True, "spooled": False}
    finally:
        release.set()
        thread.join()


def test_cancelled_result_preserves_already_spooled_state(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def work(vault, root, arguments, capture, cancel):
        cancel.record_filing({"assets": [], "filed": False, "spooled": True})
        started.set()
        release.wait()
        cancel.check()
    monkeypatch.setattr(MT, "_work", work)
    async def run():
        task = asyncio.create_task(MT.call(None, tmp_path, MT.NAME, {"html": "x", "name": "cancel"}))
        await asyncio.to_thread(started.wait)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        text, error = await task
        assert error and json.loads(text)["vault"]["spooled"] is True
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_completed_filing_enriches_committed_asset_without_duplicate_ids():
    from lampway_server.motion.cancellation import Cancellation
    cancel = Cancellation()
    cancel.record_assets([{"id": "asset", "kind": "video"}])
    cancel.record_filing({"assets": [{"id": "asset", "kind": "video", "format": "mp4"}], "filed": True, "spooled": False})
    cancel.cancel()
    assert cancel.snapshot_filing() == {"assets": [{"id": "asset", "kind": "video", "format": "mp4"}], "filed": True, "partial": False, "spooled": False}


def test_repeated_driver_close_does_not_close_reused_file_descriptor(tmp_path):
    import os
    from lampway_server.motion.frames import CDP
    read_fd, write_fd = os.pipe()
    client = CDP(write_fd, read_fd)
    client.close()
    replacement = os.open(tmp_path / "unrelated", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        client.close()
        os.write(replacement, b"still owned by caller")
    finally:
        os.close(replacement)


def test_cancel_exited_leader_stops_live_child_holding_owned_pipes(tmp_path, monkeypatch):
    import os
    import signal
    import subprocess
    import sys
    import time
    from pathlib import Path
    from lampway_server.motion import cancellation as C
    cancel = C.Cancellation()
    launched = threading.Event()
    processes, errors = [], []
    original = subprocess.Popen
    unrelated = original([sys.executable, "-c", "import time;time.sleep(600)"], start_new_session=True)
    child_file = tmp_path / "owned-child.pid"
    code = ("import os,time;from pathlib import Path;child=os.fork();"
            f"Path({str(child_file)!r}).write_text(str(child)) if child else None;"
            "os._exit(0) if child else time.sleep(600)")
    def owned_launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        launched.set()
        return process
    monkeypatch.setattr(subprocess, "Popen", owned_launch)
    def run():
        try:
            C.run_owned([sys.executable, "-c", code], cancel=cancel)
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=run)
    try:
        worker.start()
        assert launched.wait(5)
        leader = processes[0]
        # Observe exit without poll()/wait(): the unreaped leader reserves this group's numeric identity.
        deadline = time.monotonic() + 5
        while Path(f"/proc/{leader.pid}/stat").read_text().split(") ", 1)[1].split()[0] != "Z":
            assert time.monotonic() < deadline, "fixture leader must exit"
            threading.Event().wait(0.01)
        child = int(child_file.read_text())
        assert os.getpgid(child) == leader.pid
        cancel.cancel()
        worker.join(timeout=2)
        assert not worker.is_alive(), "an exited leader must not leave its child holding the worker's pipes open"
        assert len(errors) == 1 and isinstance(errors[0], C.MotionCancelled)
        assert unrelated.poll() is None
    finally:
        if processes:
            # Exact fixture PGID only; required for the RED case whose cancelled leader was already reaped.
            try:
                os.killpg(processes[0].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        worker.join()
        unrelated.kill()
        unrelated.wait()


def test_normal_owned_exit_preserves_success_after_streams_close(tmp_path):
    import sys
    from lampway_server.motion.cancellation import run_owned
    completed = tmp_path / "completed-work"
    code = ("import os,time;from pathlib import Path;os.close(1);os.close(2);time.sleep(0.05);"
            f"Path({str(completed)!r}).write_text('done')")
    result = run_owned([sys.executable, "-c", code])
    assert result.returncode == 0 and completed.read_text() == "done"


def test_owned_group_stop_is_once_even_after_leader_is_reaped(tmp_path, monkeypatch):
    import os
    import sys
    from lampway_server.motion import cancellation as C
    calls = []
    original = os.killpg
    def killpg(group, signal):
        calls.append(group)
        original(group, signal)
    monkeypatch.setattr(os, "killpg", killpg)
    # run_owned's wait observes exit without reaping, stops the group, and then reaps the leader.
    import subprocess
    process = C.own_process(subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True))
    assert process.wait() == 0
    C.kill_owned(process)
    C.kill_owned(process)
    assert calls == [process.pid], "repeated cleanup must not signal a now-reusable numeric group ID"
