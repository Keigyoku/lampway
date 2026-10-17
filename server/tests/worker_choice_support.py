# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline installation facts for played harness fixtures; no vendor process runs."""
import os

from lampway_server.herdr import harnesses as HN


def install_worker_harness(tmp_path, monkeypatch, harness):
    """A fixture executable that the real adapter's local PATH lookup can find."""
    directory = tmp_path / "worker-harness-fixture-bin"
    directory.mkdir(exist_ok=True)
    executable = directory / HN.get(harness).binary
    license_line = "# SPDX-" + "License-Identifier: GPL-3.0-or-later"
    executable.write_text("#!/bin/sh\n# SPDX-FileCopyrightText: 2026 Lampway contributors\n" +
                          license_line + "\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))
    return executable
