# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A worker startup qualification uses the sole local launcher and bounded owned environment."""
from types import SimpleNamespace

from lampway_server.herdr import launcher as L


def test_probe_passes_worker_environment_without_starting_herdr(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(L, "scrubbed_base", lambda: {"HOME": str(tmp_path), "PATH": "/synthetic"})
    def spawn(argv, env, timeout):
        calls.append((argv, env, timeout))
        return SimpleNamespace(returncode=0, stdout='{"guard":"installed"}\n', stderr="")
    monkeypatch.setattr(L, "_probe_spawn", spawn)
    # The ordinary probe deliberately cannot carry a startup guard. The worker seam must.
    probe = getattr(L, "worker_probe", lambda argv, env, timeout: L.probe(argv, timeout))
    assert probe(["/synthetic/hermes", "--version"], {"LAMPWAY_HERMES_WORKER_PROBE": "1"}, 4) == (0, '{"guard":"installed"}\n')
    assert calls == [(["/synthetic/hermes", "--version"],
        {"HOME": str(tmp_path), "PATH": "/synthetic", "LAMPWAY_HERMES_WORKER_PROBE": "1"}, 4)]
