"""Asset Vault render (specs/asset_library/asset_render.md section 10): deterministic previews, off the user's live Blender, cached by recipe."""
import io
import itertools
import json
import shutil
import struct
import subprocess

import numpy as np
import pytest
from PIL import Image

from lampway_server.library import render as R
from lampway_server.library.store import AssetLibrary, LibraryError
from tests.test_library_vectors import box, glb_from_mesh, torus

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def glb(pos, idx, uv=None, color=None, texture=None):
    """A GLB with one primitive: positions, triangle indices, optional TEXCOORD_0, a material with an optional baseColorFactor and an optional embedded PNG texture."""
    pos, ib = np.asarray(pos, "<f4"), np.asarray(idx, "<u4").reshape(-1)
    chunks, views, accessors = [], [], []

    def add(data, acc):
        off = sum(len(c) for c in chunks)
        chunks.append(data + b"\0" * (-len(data) % 4))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
        if acc is not None:
            accessors.append({"bufferView": len(views) - 1, **acc})
        return len(views) - 1

    add(pos.tobytes(), {"componentType": 5126, "count": len(pos), "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
    attrs = {"POSITION": 0}
    if uv is not None:
        uv = np.asarray(uv, "<f4")
        add(uv.tobytes(), {"componentType": 5126, "count": len(uv), "type": "VEC2"})
        attrs["TEXCOORD_0"] = len(accessors) - 1
    add(ib.tobytes(), {"componentType": 5125, "count": len(ib), "type": "SCALAR"})
    prim = {"attributes": attrs, "indices": len(accessors) - 1, "mode": 4, "material": 0}
    pbr = {}
    if color is not None:
        pbr["baseColorFactor"] = list(color) + [1.0]
    doc = {"asset": {"version": "2.0"}, "meshes": [{"primitives": [prim]}], "accessors": accessors, "bufferViews": views, "materials": [{"pbrMetallicRoughness": pbr}],
           "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    if texture is not None:
        b = io.BytesIO()
        texture.save(b, "PNG")
        v = add(b.getvalue(), None)
        doc.update(images=[{"bufferView": v, "mimeType": "image/png"}], textures=[{"source": 0}])
        pbr["baseColorTexture"] = {"index": 0}
    bin_ = b"".join(chunks)
    doc["buffers"] = [{"byteLength": len(bin_)}]
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def uv_cube():
    """24 vertices (4 per face), each face its own UV square: six islands."""
    faces = [((-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)), ((.5, -.5, -.5), (-.5, -.5, -.5), (-.5, .5, -.5), (.5, .5, -.5)),
             ((-.5, -.5, -.5), (-.5, -.5, .5), (-.5, .5, .5), (-.5, .5, -.5)), ((.5, -.5, .5), (.5, -.5, -.5), (.5, .5, -.5), (.5, .5, .5)),
             ((-.5, .5, .5), (.5, .5, .5), (.5, .5, -.5), (-.5, .5, -.5)), ((-.5, -.5, -.5), (.5, -.5, -.5), (.5, -.5, .5), (-.5, -.5, .5))]
    cells = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]
    pos, uv, idx = [], [], []
    for f, (cx, cy) in zip(faces, cells):
        base = len(pos)
        pos += list(f)
        uv += [((cx + u) / 3, (cy + v) / 2) for u, v in ((0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95))]
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return pos, idx, uv


def gradient_png(path, size=(64, 48)):
    a = np.zeros((size[1], size[0], 3), "uint8")
    a[:, :, 0] = np.linspace(0, 255, size[0])[None, :]
    a[:, :, 1] = np.linspace(255, 0, size[1])[:, None]
    Image.fromarray(a).save(path)


def put(lib, kind, name, path):
    return lib.put({"kind": kind, "name": name, "source": {"kind": "t", "key": name}, "files": [{"role": "main", "path": str(path), "storage": "external"}]})["id"]


def files_of(lib, aid, role):
    return [f for f in lib.get(aid)["files"] if f["role"] == role]


class Fake:
    """A stand-in for the headless Blender process: records every launch and answers with ``rc``."""

    def __init__(self, rc=0, stderr=""):
        self.calls, self.rc, self.stderr = [], rc, stderr

    def __call__(self, argv, env=None, **kw):
        self.calls.append((list(argv), dict(env or {})))
        return subprocess.CompletedProcess(argv, self.rc, "", self.stderr)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def renderer(lib, **kw):
    kw.setdefault("blender", "/fake/blender")
    kw.setdefault("runner", Fake())
    kw.setdefault("loadavg", lambda: (0.0, 0.0, 0.0))
    kw.setdefault("cpus", 8)
    kw.setdefault("live_window_cpu", lambda: 0.0)
    kw.setdefault("now", Clock())
    return R.Renderer(lib, **kw)


def mesh_asset(tmp_path, lib, data=None, name="torus"):
    p = tmp_path / f"{name}.glb"
    p.write_bytes(data if data is not None else glb_from_mesh(*torus()))
    return put(lib, "mesh", name, p), p


# 1 -------------------------------------------------------------------------------------------------------------------------------
def test_software_thumb_of_a_known_cube_has_expected_silhouette_area():
    img, mask = R.render_mesh(R.glb_mesh(glb_from_mesh(*box())), size=256)
    assert img.shape == (256, 256, 3) and img.dtype == np.uint8
    assert 0.40 <= mask.mean() <= 0.60
    assert (img[~mask] == 128).all()                          # the neutral grey #808080 background, nothing else outside the silhouette
    again, _ = R.render_mesh(R.glb_mesh(glb_from_mesh(*box())), size=256)
    assert R.encode_jpeg(img) == R.encode_jpeg(again)


def test_a_torus_shows_a_hole_and_shading():
    img, mask = R.render_mesh(R.glb_mesh(glb_from_mesh(*torus())), size=256)
    assert mask.any() and not mask.all()
    assert not mask[128, 128]                                 # the camera looks through the hole at the centre
    assert img[mask].mean(1).std() > 8                        # lit, not flat


def test_the_material_colour_and_the_base_colour_texture_reach_the_thumbnail():
    pos, idx, uv = uv_cube()
    red, rmask = R.render_mesh(R.glb_mesh(glb(pos, idx, color=(0.9, 0.05, 0.05))), size=64)
    m = red[rmask].astype(int)
    assert (m[:, 0] > m[:, 1] + 40).all()
    tex = Image.new("RGB", (8, 8), (20, 200, 30))
    img, mask = R.render_mesh(R.glb_mesh(glb(pos, idx, uv=uv, texture=tex)), size=64)
    g = img[mask].astype(int)
    assert (g[:, 1] > g[:, 0] + 40).all() and (g[:, 1] > g[:, 2] + 40).all()


# 2 -------------------------------------------------------------------------------------------------------------------------------
def test_same_recipe_same_bytes_and_recipe_change_regenerates(tmp_path, monkeypatch):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    rr = renderer(lib)
    assert rr.enqueue(aid, ["thumb"])["queued"] == 1
    rr.drain()
    path = files_of(lib, aid, "thumb")[0]["locations"][0]["path"]
    assert path.endswith("/thumb_256.jpg") and "/derived/" in path
    before = open(path, "rb").read()
    again = rr.enqueue(aid, ["thumb"])
    assert again["queued"] == 0 and again["cached"] == ["thumb"]            # same recipe: nothing to do
    rr.drain()
    assert open(path, "rb").read() == before
    monkeypatch.setitem(R.RECIPE, "margin", 0.12)                           # a camera/rig change is a new recipe hash
    assert rr.enqueue(aid, ["thumb"])["queued"] == 1
    rr.drain()
    assert open(path, "rb").read() != before
    assert len(files_of(lib, aid, "thumb")) == 1                            # replaced, not added beside
    assert lib.get(aid)["attrs"]["render_recipe"]["thumb"] == R.recipe_hash("thumb")


def test_a_512_thumbnail_is_on_demand_and_kept_beside_the_256(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    rr = renderer(lib)
    rr.enqueue(aid, ["thumb"])
    rr.enqueue(aid, ["thumb"], size=512)
    rr.drain()
    big = files_of(lib, aid, "thumb:512")
    assert big and Image.open(big[0]["locations"][0]["path"]).size == (512, 512)
    assert Image.open(files_of(lib, aid, "thumb")[0]["locations"][0]["path"]).size == (256, 256)


# 3 -------------------------------------------------------------------------------------------------------------------------------
@needs_ffmpeg
def test_thumbnail_coverage_on_the_corpus(tmp_path):
    lib = make_lib(tmp_path)
    png = tmp_path / "g.png"
    gradient_png(png)
    mp4 = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12", "-t", "2", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    ids = [mesh_asset(tmp_path, lib)[0], put(lib, "image", "grad", png), put(lib, "video", "clip", mp4)]
    rr = renderer(lib)
    for a in ids:
        rr.enqueue(a, ["thumb"])
    rr.drain()
    for a in ids:
        f = files_of(lib, a, "thumb")
        assert f, a
        im = np.asarray(Image.open(f[0]["locations"][0]["path"]).convert("L"), dtype=float)
        assert max(im.shape) <= 256 and im.std() > 3, (a, im.std())
    assert rr.runner.calls == []                                            # none of this needed the headless Blender


def test_a_missing_file_keeps_the_last_good_thumbnail(tmp_path):
    lib = make_lib(tmp_path)
    png = tmp_path / "g.png"
    gradient_png(png)
    aid = put(lib, "image", "grad", png)
    rr = renderer(lib)
    rr.enqueue(aid, ["thumb"])
    rr.drain()
    png.unlink()
    rr.regenerate(aid, ["thumb"])
    rr.drain()
    st = rr.status(aid)["products"]["thumb"]
    assert st["state"] == "failed" and f"file missing: {png}" in st["error"] and "last good" in st["error"]
    assert files_of(lib, aid, "thumb")


def test_refusals_name_the_fix(tmp_path):
    lib = make_lib(tmp_path)
    png = tmp_path / "g.png"
    gradient_png(png)
    aid = put(lib, "image", "grad", png)
    rr = renderer(lib)
    with pytest.raises(LibraryError, match="turntable is for meshes: use ball for materials"):
        rr.enqueue(aid, ["turntable"])
    with pytest.raises(LibraryError, match="size max 1024: previews, not renders"):
        rr.enqueue(aid, ["thumb"], size=2048)
    with pytest.raises(LibraryError, match="frames 8..72"):
        rr.enqueue(aid, ["thumb"], frames=200)
    with pytest.raises(LibraryError, match="never Cycles"):
        rr.enqueue(aid, ["thumb"], engine="cycles")
    with pytest.raises(LibraryError, match="unknown product"):
        rr.enqueue(aid, ["beauty"])


def test_an_empty_mesh_is_flagged_not_rendered(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib, glb_from_mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0)], []), name="empty")
    rr = renderer(lib)
    rr.enqueue(aid, ["thumb"])
    rr.drain()
    st = rr.status(aid)["products"]["thumb"]
    assert st["state"] == "failed" and "empty mesh: nothing to render" in st["error"]
    assert "defect:empty" in lib.get(aid)["tags"]


def test_a_software_turntable_writes_n_rotating_frames_and_a_contact_sheet(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib, glb_from_mesh(*box(1.0, 0.3, 0.6)), name="slab")
    rr = renderer(lib)
    rr.enqueue(aid, ["turntable", "contact_sheet"], frames=12, size=128)
    rr.drain()
    frames = sorted(files_of(lib, aid, "turntable"), key=lambda f: f["ord"])
    assert len(frames) == 12 and frames[0]["locations"][0]["path"].endswith("turn_000.jpg")
    a, b = (np.asarray(Image.open(f["locations"][0]["path"]).convert("L"), dtype=float) for f in frames[:2])
    assert np.abs(a - b).mean() > 1                                          # the object turned between frames
    sheet = files_of(lib, aid, "sheet")
    assert sheet and Image.open(sheet[0]["locations"][0]["path"]).size == (4 * 128, 3 * 128)
    assert rr.status(aid)["products"]["turntable"]["engine"] == "software"


# 4 -------------------------------------------------------------------------------------------------------------------------------
def test_idle_guard_defers_workbench_and_not_software(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    fake, clock = Fake(), Clock()
    rr = renderer(lib, runner=fake, loadavg=lambda: (9.0, 9.0, 9.0), cpus=8, now=clock)   # 9.0 > 0.6 x 8
    rr.enqueue(aid, ["thumb"], engine="software")
    rr.enqueue(aid, ["turntable"], engine="workbench", frames=8)
    rr.drain()
    assert fake.calls == []                                                 # the Blender job waited
    st = rr.status(aid)["products"]
    assert st["thumb"]["state"] == "done"                                   # the software path ran regardless
    assert st["turntable"]["state"] == "deferred" and st["turntable"]["retry_in_s"] == 30
    rr.drain()
    assert rr.status(aid)["products"]["turntable"]["retry_in_s"] == 30      # not due yet: nothing re-checked, no backoff step
    clock.t += 31
    rr.drain()
    assert rr.status(aid)["products"]["turntable"]["retry_in_s"] == 120
    clock.t += 121
    rr.drain()
    assert rr.status(aid)["products"]["turntable"]["retry_in_s"] == 600
    clock.t += 601
    rr.drain()
    assert rr.status(aid)["products"]["turntable"]["retry_in_s"] == 600     # the backoff stops growing at 10 min
    assert fake.calls == []


def test_a_live_blender_window_above_25_percent_defers_too(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    fake = Fake()
    rr = renderer(lib, runner=fake, live_window_cpu=lambda: 31.0)
    rr.enqueue(aid, ["turntable"], engine="workbench", frames=8)
    rr.drain()
    assert fake.calls == [] and rr.status(aid)["products"]["turntable"]["state"] == "deferred"


def test_live_window_cpu_reads_proc_and_ignores_background_blenders(tmp_path):
    proc = tmp_path / "proc"
    for pid, cmd, ticks in ((101, ["/opt/lampway/mixar"], 900), (102, ["/opt/lampway/mixar", "-b", "x.blend"], 5000), (103, ["/usr/bin/python3"], 9000)):
        d = proc / str(pid)
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(b"\0".join(c.encode() for c in cmd) + b"\0")
        (d / "stat").write_text(f"{pid} (x) S 1 1 1 0 -1 0 0 0 0 0 {ticks} 0 0 0 20 0 1 0 0 0 0\n")
    first = R.blender_cpu_sample(proc, now=10.0)
    for pid, add in ((101, 30), (102, 100), (103, 100)):
        st = proc / str(pid) / "stat"
        parts = st.read_text().split()
        parts[13] = str(int(parts[13]) + add)
        st.write_text(" ".join(parts) + "\n")
    second = R.blender_cpu_sample(proc, now=11.0)
    assert R.cpu_percent(first, second, hz=100) == pytest.approx(30.0)      # 30 ticks in 1 s at 100 Hz; only the windowed Blender (no -b) counts
    assert R.cpu_percent(first, first, hz=100) == 0.0


# 6 / 7 --------------------------------------------------------------------------------------------------------------------------
def test_uv_overlay_has_one_polyline_per_island_edge_loop():
    pos, idx, uv = uv_cube()
    mesh = R.glb_mesh(glb(pos, idx, uv=uv))
    loops = R.uv_loops(mesh)
    assert len(loops) == 6 and all(len(l) == 4 for l in loops)              # each island is a square: 4 boundary edges, the diagonal is interior
    im = Image.open(io.BytesIO(R.uv_overlay(mesh, size=256)))
    assert im.size == (256, 256)
    a = np.asarray(im.convert("RGB")).astype(int)
    r, c = int(256 * 0.75), int(256 * 0.5 / 3)                               # the centre of island (0, 1) lies on its diagonal: an interior wire edge
    assert ((a[r - 1:r + 2, c - 1:c + 2] == (230, 230, 230)).all(2)).any()
    assert ((a == (255, 170, 0)).all(2)).sum() > 6 * 4 * 50                   # the island boundaries in the heavier colour


def test_a_torus_without_uvs_refuses_the_overlay_and_says_why():
    mesh = R.glb_mesh(glb_from_mesh(*torus()))
    with pytest.raises(LibraryError, match="no UV set"):
        R.uv_overlay(mesh, size=256)


def test_map_sheet_stamps_normal_convention(tmp_path):
    base, nrm = tmp_path / "b.png", tmp_path / "n.png"
    gradient_png(base)
    Image.new("RGB", (32, 32), (128, 128, 255)).save(nrm)
    gl = R.map_sheet([{"channel": "basecolor", "path": str(base)}, {"channel": "normal", "path": str(nrm), "convention": "GL"}], cell=64)
    dx = R.map_sheet([{"channel": "basecolor", "path": str(base)}, {"channel": "normal", "path": str(nrm), "convention": "DX"}], cell=64)
    assert [c["stamp"] for c in gl["cells"]] == [None, "GL"] and [c["stamp"] for c in dx["cells"]] == [None, "DX"]
    assert gl["bytes"] != dx["bytes"]
    a, b = (np.asarray(Image.open(io.BytesIO(x["bytes"])).convert("RGB")).astype(int) for x in (gl, dx))
    diff = np.argwhere(np.abs(a - b).sum(2) > 0)
    assert diff.size and diff[:, 0].max() < R.LABEL_H                        # only the label strip differs, the pixels of the map are the same


def test_map_sheet_refuses_a_normal_with_no_convention(tmp_path):
    nrm = tmp_path / "n.png"
    Image.new("RGB", (8, 8), (128, 128, 255)).save(nrm)
    with pytest.raises(LibraryError, match="normal map convention"):
        R.map_sheet([{"channel": "normal", "path": str(nrm)}], cell=64)


def test_contact_sheet_is_4_by_3_of_the_frames(tmp_path):
    frames = []
    for i in range(12):
        p = tmp_path / f"f{i}.png"
        Image.new("RGB", (32, 32), (i * 20, 10, 10)).save(p)
        frames.append(str(p))
    img = Image.open(io.BytesIO(R.contact_sheet(frames, cell=32)))
    assert img.size == (4 * 32, 3 * 32)
    a = np.asarray(img.convert("RGB")).astype(int)
    assert abs(a[16, 16, 0] - 0) <= 3 and abs(a[2 * 32 + 16, 3 * 32 + 16, 0] - 220) <= 3     # row-major: frame 11 sits bottom right


# 8 -------------------------------------------------------------------------------------------------------------------------------
def test_worker_is_batch_mode_and_niced(tmp_path):
    argv, env = R.blender_command("/opt/blender/blender", tmp_path / "job.json", tmp_path / "scratch")
    assert argv[:3] == ["nice", "-n", "15"]
    assert "-b" in argv and "--factory-startup" in argv and argv[argv.index("--python") + 1].endswith("render_worker.py")
    assert argv[-2:] == ["--", str(tmp_path / "job.json")]
    assert env["BLENDER_USER_CONFIG"].startswith(str(tmp_path / "scratch")) and env["BLENDER_USER_SCRIPTS"].startswith(str(tmp_path / "scratch"))


def test_live_blender_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_BRIDGE_PORT", "9876")
    monkeypatch.setenv("BLENDER_MCP_PORT", "9876")
    _, env = R.blender_command("/opt/blender/blender", tmp_path / "job.json", tmp_path / "scratch")
    assert env["LAMPWAY_BRIDGE_PORT"] == "0" and "BLENDER_MCP_PORT" not in env      # 0 disables the bridge: the worker can never be the user's live session


def test_a_workbench_job_launches_the_worker_with_a_job_file(tmp_path):
    lib = make_lib(tmp_path)
    aid, p = mesh_asset(tmp_path, lib)
    fake = Fake()
    rr = renderer(lib, runner=fake)
    rr.enqueue(aid, ["turntable"], engine="workbench", frames=8, size=128)
    rr.drain()
    assert len(fake.calls) == 1
    argv, env = fake.calls[0]
    job = json.loads(open(argv[-1]).read())
    assert job["product"] == "turntable" and job["frames"] == 8 and job["size"] == 128 and job["engine"] == "workbench" and job["input"] == str(p)
    assert job["recipe"] == R.RECIPE
    assert rr.status(aid)["products"]["turntable"]["state"] == "failed"      # the fake wrote no frames: never reported done
    assert "no frames" in rr.status(aid)["products"]["turntable"]["error"]


def test_a_crashed_worker_is_restarted_once_then_failed_with_the_stderr_tail(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    fake = Fake(rc=139, stderr="lots of noise\n" * 50 + "Segmentation fault in EEVEE")
    rr = renderer(lib, runner=fake)
    rr.enqueue(aid, ["turntable"], engine="workbench", frames=8)
    rr.drain()
    assert len(fake.calls) == 2
    st = rr.status(aid)["products"]["turntable"]
    assert st["state"] == "failed" and st["error"].endswith("Segmentation fault in EEVEE") and len(st["error"]) < 600


def test_big_meshes_go_to_workbench_and_huge_ones_are_decimated_for_the_preview(tmp_path, monkeypatch):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)                                      # 576 triangles
    monkeypatch.setattr(R, "SOFT_TURNTABLE_MAX_TRIS", 100)
    monkeypatch.setattr(R, "SOFT_MAX_TRIS", 500)
    fake = Fake()
    rr = renderer(lib, runner=fake)
    rr.enqueue(aid, ["turntable", "thumb"], frames=8)
    rr.drain()
    jobs = [json.loads(open(c[0][-1]).read()) for c in fake.calls]
    assert sorted(j["product"] for j in jobs) == ["thumb", "turntable"]     # auto: over the software limits -> workbench
    assert all(j["engine"] == "workbench" and j["decimate_to"] == R.DECIMATE_TO for j in jobs)


def test_cancel_drops_a_queued_job(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    rr = renderer(lib)
    rr.enqueue(aid, ["thumb"])
    assert rr.cancel(aid, ["thumb"]) == {"cancelled": ["thumb"]}
    rr.drain()
    assert rr.status(aid)["products"]["thumb"]["state"] == "cancelled" and not files_of(lib, aid, "thumb")


# the tool surface (asset_mcp's lampway_asset_render calls this) and the background worker ----------------------------------------
def test_handle_speaks_the_contracts_shape_and_refusals_carry_help(tmp_path):
    lib = make_lib(tmp_path)
    aid, _ = mesh_asset(tmp_path, lib)
    rr = renderer(lib)
    out = rr.handle({"action": "enqueue", "asset_id": aid, "products": ["thumb"]})
    assert out["ok"] is True and out["queued"] == 1
    rr.drain()
    st = rr.handle({"action": "status", "asset_id": aid})
    assert st["ok"] is True and st["products"]["thumb"]["state"] == "done" and st["products"]["thumb"]["engine"] == "software"
    assert st["products"]["thumb"]["path"].endswith("thumb_256.jpg") and st["products"]["thumb"]["ms"] >= 0
    bad = rr.handle({"action": "enqueue", "asset_id": aid, "products": ["thumb"], "size": 4096})
    assert bad["ok"] is False and "size max 1024" in bad["error"] and bad["help"]
    assert rr.handle({"action": "explode", "asset_id": aid})["ok"] is False
    assert rr.handle({"action": "status", "asset_id": "nope"})["ok"] is False


def test_backfill_queues_a_thumbnail_for_every_asset_without_one(tmp_path):
    lib = make_lib(tmp_path)
    a, _ = mesh_asset(tmp_path, lib)
    png = tmp_path / "g.png"
    gradient_png(png)
    b = put(lib, "image", "grad", png)
    lib.put({"kind": "receipt", "name": "r", "source": {"kind": "t", "key": "r"}, "files": [{"role": "main", "bytes": b"{}", "storage": "cas"}]})
    rr = renderer(lib)
    assert rr.backfill() == 2                                                # the receipt has no thumbnail product
    rr.drain()
    assert files_of(lib, a, "thumb") and files_of(lib, b, "thumb")
    assert rr.backfill() == 0


def test_the_worker_thread_drains_and_backfills_until_stopped(tmp_path):
    import threading
    import time as _t
    lib = make_lib(tmp_path)
    a, _ = mesh_asset(tmp_path, lib)
    rr = renderer(lib)
    stop = threading.Event()
    t = rr.start(stop, idle_s=0.05)
    deadline = _t.monotonic() + 20
    while not files_of(lib, a, "thumb") and _t.monotonic() < deadline:
        _t.sleep(0.05)
    stop.set()
    t.join(5)
    assert files_of(lib, a, "thumb") and not t.is_alive()
