# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Idle servers expire their owned copies without deleting user originals."""
import asyncio
from pathlib import Path

import pytest

from lampway_server.app import create_app
from lampway_server.herdr.host import Cockpit


@pytest.mark.anyio
@pytest.mark.parametrize("first_tick_fails", [False, True])
async def test_idle_maintenance_expires_30_day_owned_copies_and_keeps_running(
        settings, provider, tmp_path, monkeypatch, first_tick_fails):
    from lampway_server.herdr import host
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    original = project / "original.png"
    original.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")
    cockpit = Cockpit(tmp_path / "herdr", project_root=project)
    cockpit._save({"version": 1, "sessions": [
        {"id": "owned-pane", "project_root": str(project), "state": "ended"}]})
    copy = Path(cockpit.write_pane_images("owned-pane", [original.read_bytes()])[0])
    app = create_app(settings, provider=provider, cockpit=cockpit, job_backends={})
    monkeypatch.setattr(app.state.renderer, "start", lambda stop: None)
    sleep = asyncio.sleep
    gate = asyncio.Queue()
    ticks = asyncio.Queue()

    async def controlled_sleep(delay, result=None):
        if delay == 60:
            await gate.get()
            return result
        return await sleep(delay, result)

    monkeypatch.setattr(asyncio, "sleep", controlled_sleep)
    async with app.router.lifespan_context(app):
        # Startup reconciliation runs with fresh copies; only subsequent idle ticks
        # see the aged copy. A failed cleanup must not end future maintenance.
        assert copy.exists()
        now = host.time.time() + 30 * 86400 + 1
        monkeypatch.setattr(host.time, "time", lambda: now)
        expire = cockpit.expire_pane_images
        calls = 0

        def observed_expiry():
            nonlocal calls
            calls += 1
            try:
                if first_tick_fails and calls == 1:
                    raise OSError("synthetic maintenance failure")
                return expire()
            finally:
                loop.call_soon_threadsafe(ticks.put_nowait, calls)

        loop = asyncio.get_running_loop()
        monkeypatch.setattr(cockpit, "expire_pane_images", observed_expiry)
        gate.put_nowait(None)
        assert await asyncio.wait_for(ticks.get(), 5) == 1
        if first_tick_fails:
            assert copy.exists()
            gate.put_nowait(None)
            assert await asyncio.wait_for(ticks.get(), 5) == 2
        assert not copy.exists()
        assert original.read_bytes() == b"\x89PNG\r\n\x1a\nsynthetic"


@pytest.mark.anyio
async def test_shutdown_joins_inflight_owned_image_expiry(settings, provider, tmp_path, monkeypatch):
    import threading
    cockpit = Cockpit(tmp_path / "herdr", project_root=tmp_path)
    app = create_app(settings, provider=provider, cockpit=cockpit, job_backends={})
    monkeypatch.setattr(app.state.renderer, "start", lambda stop: None)
    real_sleep = asyncio.sleep
    gate = asyncio.Event()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    async def controlled_sleep(delay, result=None):
        if delay == 60:
            await gate.wait()
            gate.clear()
            return result
        return await real_sleep(delay, result)

    monkeypatch.setattr(asyncio, "sleep", controlled_sleep)
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()

    def held_expiry():
        started.set()
        try:
            assert release.wait(5), "synthetic cleanup release never arrived"
        finally:
            finished.set()

    monkeypatch.setattr(cockpit, "expire_pane_images", held_expiry)
    shutdown = None
    try:
        gate.set()
        assert await asyncio.to_thread(started.wait, 5)
        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await real_sleep(0.02)
        assert not shutdown.done(), "lifespan ended with image expiry still running"
        release.set()
        await asyncio.wait_for(shutdown, 5)
        assert finished.is_set()
        assert not [t for t in asyncio.all_tasks() if t.get_name() in
                    {"lampway-maintenance", "lampway-pane-image-expiry"} and not t.done()]
    finally:
        release.set()
        if shutdown is None:
            await lifespan.__aexit__(None, None, None)
        elif not shutdown.done():
            await asyncio.wait_for(shutdown, 5)
