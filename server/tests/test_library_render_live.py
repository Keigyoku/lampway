"""asset_render against the REAL Lampway binary ($LAMPWAY_BIN): the Workbench turntable and the EEVEE ball run in a separate headless, niced process (never Cycles)."""
import os
import socket
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import render as R
from tests.test_library_render import files_of, glb, make_lib, mesh_asset
from tests.test_library_vectors import box

BIN = os.environ.get("LAMPWAY_BIN")
pytestmark = pytest.mark.skipif(not (BIN and Path(BIN).exists()), reason="needs the real binary: set LAMPWAY_BIN")


def live(lib):
    return R.Renderer(lib, blender=BIN, loadavg=lambda: (0.0, 0.0, 0.0), live_window_cpu=lambda: 0.0)


@pytest.mark.timeout(300)
def test_a_workbench_turntable_frames_the_mesh_on_grey(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib, glb(*box(1.0, 0.3, 0.6)), name="slab")
    rr = live(lib)
    rr.enqueue(aid, ["turntable"], engine="workbench", frames=8, size=128)
    rr.drain()
    st = rr.status(aid)["products"]["turntable"]
    assert st["state"] == "done", st
    frames = sorted(files_of(lib, aid, "turntable"), key=lambda f: f["ord"])
    assert len(frames) == 8
    a = [np.asarray(Image.open(f["locations"][0]["path"]).convert("RGB")).astype(int) for f in frames]
    corner = a[0][:4, :4].reshape(-1, 3)
    assert (np.abs(corner - 128) <= 3).all(), corner[:2]                    # the recipe's neutral grey background
    fg = (np.abs(a[0] - 128).sum(2) > 12).mean()
    assert 0.15 < fg < 0.8, fg                                              # framed: the slab fills a fair share of the frame
    assert np.abs(a[0] - a[2]).mean() > 1                                   # it turned


@pytest.mark.timeout(300)
def test_an_eevee_ball_of_a_red_material(tmp_path):
    blend = tmp_path / "mat.blend"
    script = ("import bpy\nm = bpy.data.materials.new('Red')\nm.use_nodes = True\nb = m.node_tree.nodes['Principled BSDF']\n"
              "b.inputs['Base Color'].default_value = (0.8, 0.02, 0.02, 1)\nm.use_fake_user = True\n"
              f"bpy.ops.wm.save_as_mainfile(filepath={str(blend)!r})\n")
    subprocess.run(["nice", "-n", "15", BIN, "-b", "--factory-startup", "--python-expr", script], check=True, capture_output=True, timeout=120,
                   env={**os.environ, "LAMPWAY_BRIDGE_PORT": "0"})
    lib = make_lib(tmp_path)
    aid = lib.put({"kind": "material", "name": "red", "source": {"kind": "t", "key": "red"}, "files": [{"role": "blend", "path": str(blend), "storage": "external"}]})["id"]
    rr = live(lib)
    rr.enqueue(aid, ["ball"])
    rr.drain()
    st = rr.status(aid)["products"]["ball"]
    assert st["state"] == "done" and st["engine"] == "eevee", st
    img = np.asarray(Image.open(files_of(lib, aid, "ball")[0]["locations"][0]["path"]).convert("RGB")).astype(int)
    centre = img[96:160, 96:160].reshape(-1, 3).mean(0)
    assert centre[0] > centre[1] + 30 and centre[0] > centre[2] + 30, centre   # red, lit, not black
    assert (np.abs(img[:4, :4].reshape(-1, 3) - 128) <= 3).all(), img[0, 0]    # on the same neutral grey as every other preview


@pytest.mark.timeout(300)
def test_the_worker_never_reaches_a_live_bridge(tmp_path, monkeypatch):
    """Two ways a worker could become a "live session": connect to the user's bridge, or take a bridge port itself (an agent would then drive the worker).
    A listener stands in for the user's session on one port; a second, free port is probed all through the render. Neither may see the worker."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(0.2)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    free = probe.getsockname()[1]
    probe.close()
    monkeypatch.setenv("BLENDER_MCP_PORT", str(srv.getsockname()[1]))
    monkeypatch.setenv("LAMPWAY_BRIDGE_PORT", str(free))
    hits, taken, stop = [], [], threading.Event()

    def accept():
        while not stop.is_set():
            try:
                c, _ = srv.accept()
                hits.append(1)
                c.close()
            except OSError:
                continue

    def poll():
        while not stop.is_set():
            try:
                socket.create_connection(("127.0.0.1", free), timeout=0.05).close()
                taken.append(1)
            except OSError:
                pass
            stop.wait(0.05)

    ts = [threading.Thread(target=f, daemon=True) for f in (accept, poll)]
    for t in ts:
        t.start()
    try:
        lib = make_lib(tmp_path)
        aid, _ = mesh_asset(tmp_path, lib, glb(*box()), name="cube")
        rr = live(lib)
        rr.enqueue(aid, ["turntable"], engine="workbench", frames=24, size=128)
        rr.drain()
        assert rr.status(aid)["products"]["turntable"]["state"] == "done"
    finally:
        stop.set()
        for t in ts:
            t.join(2)
        srv.close()
    assert hits == [] and taken == []
