"""Facelift contract 16, live and opt-in (LAMPWAY_LIVE_TERMINAL=1): the one real download of the pinned WezTerm release,
into a scratch Lampway home, through the github route. Free; nothing is spent. The GUI half (a real window on a virtual
display) is driven by the lane's report, inside the build box, with Lampway's own socket and class."""
import json
import os
from pathlib import Path

import pytest

from lampway_server import egress as E
from lampway_server.addons import wezterm as W

pytestmark = pytest.mark.skipif(os.environ.get("LAMPWAY_LIVE_TERMINAL") != "1", reason="live download: set LAMPWAY_LIVE_TERMINAL=1")


@pytest.mark.timeout(900)
def test_the_pinned_release_downloads_verifies_and_installs(tmp_path):
    home = Path(os.environ.get("LAMPWAY_LIVE_TERMINAL_HOME") or tmp_path / "home")
    home.mkdir(parents=True, exist_ok=True)
    eg = E.Egress(tmp_path / "egress")
    E.set_active(eg)
    E.install()
    try:
        eg.set_route("github", True)
        out = W.get(home, W.pin_for("linux-x86_64"))
    finally:
        E.set_active(None)
    prov = json.loads((Path(out["dir"]) / "PROVENANCE.json").read_text())
    assert prov["verified"] and prov["bytes"] == 49505472 and prov["sha256"] == W.pin_for("linux-x86_64")["sha256"]
    assert (Path(out["dir"]) / "LICENSE.md").read_text().startswith("MIT License")
    rows = [r for r in eg.log() if r.get("route") == "github"]
    assert rows and {r["event"] for r in rows} == {"send"}
    print("LIVE", json.dumps({"binary": out["binary"], "hosts": sorted({r["provider"] for r in rows})}))
