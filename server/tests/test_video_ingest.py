"""video_ingest_url (specs/mrmak/13): one clip from a link the USER pasted, with provenance, caps checked from the metadata BEFORE any download, video-only by default, an atomic rename.
A fake ``yt-dlp`` executable stands in for the downloader (it records every call, so 'no download happened' is a fact the test can read)."""
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lampway_server import videoingest as VI
from lampway_server.ledger import Ledger

FAKE = r'''#!__PY__
import json, os, shutil, sys, time
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "fake.json")))
args = sys.argv[1:]
with open(os.path.join(here, "calls.log"), "a") as fh:
    fh.write(json.dumps(args) + "\n")
if "--version" in args:
    print("2026.01.01"); sys.exit(0)
if "--dump-single-json" in args:
    print(json.dumps(cfg["info"])); sys.exit(0)
out = args[args.index("-o") + 1]
fmt = args[args.index("-f") + 1]
src = os.path.join(here, "with_audio.mp4" if "bestaudio" in fmt else "video_only.mp4")
dest = out.replace("%(ext)s", "mp4")
if cfg.get("hang"):
    open(dest + ".part", "wb").write(b"half"); open(os.path.join(here, "started"), "w").write("1"); time.sleep(5)
shutil.copy(src, dest)
'''


def _ffmpeg(path, audio):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + [str(path)]
    subprocess.run(cmd, check=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    _ffmpeg(d / "video_only.mp4", False)
    _ffmpeg(d / "with_audio.mp4", True)
    return d


@pytest.fixture
def env(tmp_path, clips):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "yt-dlp"
    exe.write_text(FAKE.replace("__PY__", sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    for n in ("video_only.mp4", "with_audio.mp4"):
        (bindir / n).write_bytes((clips / n).read_bytes())
    info = {"title": "A walk cycle", "uploader": "someone", "duration": 12, "extractor_key": "Generic", "filesize_approx": 40000, "license": None, "_type": "video"}

    def cfg(**kw):
        (bindir / "fake.json").write_text(json.dumps({"info": {**info, **kw.pop("info", {})}, **kw}))

    cfg()
    root = tmp_path / "proj"
    root.mkdir()
    calls = lambda: [json.loads(l) for l in (bindir / "calls.log").read_text().splitlines()] if (bindir / "calls.log").exists() else []  # noqa: E731
    return type("E", (), {"root": root, "exe": str(exe), "cfg": staticmethod(cfg), "calls": staticmethod(calls), "bindir": bindir, "ledger": Ledger(root / "ledger" / "runs.jsonl")})


def go(e, url="https://example.com/watch?v=abc", **kw):
    return VI.ingest(e.root, url, origin=kw.pop("origin", "user"), confirmed=kw.pop("confirmed", True), ytdlp=e.exe, ledger=e.ledger, **kw)


@pytest.mark.parametrize("bad", ["file:///x", "ftp://h/x", "https://user:pw@h/x", "-o /etc/passwd", "https://h/a b", "https://h/x\n--exec id", "", "javascript:alert(1)", "https:///nohost"])
def test_url_validation_refuses_every_other_scheme_userinfo_leading_dash_and_whitespace(env, bad):
    with pytest.raises(VI.IngestError):
        go(env, bad)
    assert env.calls() == []


def test_a_shell_metacharacter_url_is_one_argument_never_a_command(env, tmp_path):
    marker = tmp_path / "pwned"
    go(env, f"https://example.com/v?x=$(touch${{IFS}}{marker})")
    assert not marker.exists() and all(isinstance(a, str) for c in env.calls() for a in c)
    assert any(a.startswith("https://example.com/v?x=$(touch") for c in env.calls() for a in c)           # passed through verbatim as one argv entry


def test_an_agent_origin_or_an_unconfirmed_call_gets_the_card_and_nothing_runs(env):
    for kw in ({"origin": "agent", "confirmed": True}, {"origin": "user", "confirmed": False}):
        out = go(env, **kw)
        assert out["state"] == "needs_approval" and out["card"]["host"] == "example.com" and out["card"]["max_height"] == 720 and out["card"]["audio"] is False
        assert "you confirm the download" in out["message"]
    assert env.calls() == [] and not (env.root / "video").exists()


def test_caps_are_checked_from_the_metadata_before_any_download(env):
    env.cfg(info={"duration": 4000})
    with pytest.raises(VI.IngestError, match="4000 s: over the 600 s cap"):
        go(env)
    env.cfg(info={"duration": 10, "filesize_approx": 900_000_000})
    with pytest.raises(VI.IngestError, match="over the .* byte cap"):
        go(env)
    assert all("--dump-single-json" in c for c in env.calls())                                       # metadata only: zero download calls


def test_a_playlist_is_refused_one_clip_per_call(env):
    env.cfg(info={"_type": "playlist", "entries": [{}, {}]})
    with pytest.raises(VI.IngestError, match="one clip per call"):
        go(env)
    assert all("--dump-single-json" in c for c in env.calls())
    assert "--no-playlist" in env.calls()[0]


def test_a_missing_downloader_says_how_to_fix_it(env, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(VI.IngestError, match="install yt-dlp on the server: the downloader is not bundled"):
        VI.ingest(env.root, "https://example.com/v", origin="user", confirmed=True, ledger=env.ledger)


def test_bounds_are_enforced(env):
    for kw in ({"max_height": 100}, {"max_height": 2000}, {"max_seconds": 0}, {"max_seconds": 4000}, {"max_bytes": 3 * 1024 ** 3}):
        with pytest.raises(VI.IngestError):
            go(env, **kw)


def test_video_only_is_the_default_and_the_file_has_no_audio_stream_and_audio_true_changes_the_selector(env):
    a = go(env)
    assert a["has_audio"] is False and a["path"].endswith("/source.mp4") and a["width"] == 160 and a["height"] == 120 and abs(a["duration_s"] - 1.0) < 0.2 and abs(a["container_fps"] - 10.0) < 0.1
    sel = [c[c.index("-f") + 1] for c in env.calls() if "-f" in c][0]
    assert "avc1" in sel and "height<=720" in sel and "bestaudio" not in sel
    b = go(env, "https://example.com/other", audio=True)
    sel2 = [c[c.index("-f") + 1] for c in env.calls() if "-f" in c][-1]
    assert "bestaudio" in sel2 and b["has_audio"] is True


def test_the_second_ingest_reuses_the_asset_and_every_ingest_leaves_a_ledger_row(env):
    a = go(env)
    b = go(env)
    assert a["reused"] is False and b["reused"] is True and a["asset_id"] == b["asset_id"] and a["sha256"] == b["sha256"]
    assert len([c for c in env.calls() if "-f" in c]) == 1
    files = [p for p in (env.root / "video" / "ingest").rglob("source.*")]
    assert len(files) == 1 and files[0].parent.name == a["sha256"][:16]
    rows = env.ledger.rows()
    assert len(rows) == 2 and rows[0]["stage"] == "other" and rows[0]["studio"] == "local" and rows[1]["settings"]["reused"] is True and rows[0]["output_hashes"] == [a["sha256"]]


def test_provenance_redacts_query_secrets_and_userinfo(env):
    url = "https://example.com/v?id=1&token=SECRETTOKEN&Sig=SIGVAL&key=KEYVAL&auth=AUTHVAL&signature=S2&keep=yes"
    out = go(env, url)
    p = out["provenance"]
    assert "keep=yes" in p["url_redacted"] and "id=1" in p["url_redacted"]
    for secret in ("SECRETTOKEN", "SIGVAL", "KEYVAL", "AUTHVAL", "S2"):
        assert secret not in json.dumps(out) and secret not in (env.root / "ledger" / "runs.jsonl").read_text()
        assert all(secret not in f.read_text() for f in (env.root / "video" / "ingest").rglob("*.json"))
    assert p["extractor"] == "Generic" and p["title"] == "A walk cycle" and p["uploader"] == "someone" and p["tool"] == "yt-dlp@2026.01.01" and p["retrieved_at"]
    assert VI.redact("https://u:pw@h/p?token=1&a=2") == "https://h/p?a=2"


def test_a_kill_mid_download_leaves_no_final_file(env):
    env.cfg(hang=True)
    import multiprocessing
    ctx = multiprocessing.get_context("fork")
    proc = ctx.Process(target=lambda: go(env))
    proc.start()
    for _ in range(100):
        if (env.bindir / "started").exists():
            break
        time.sleep(0.1)
    assert (env.bindir / "started").exists()
    proc.kill()
    proc.join()
    ing = env.root / "video" / "ingest"
    finals = [f for f in ing.rglob("source.*") if not any(x.startswith(".part") for x in f.relative_to(ing).parts)] if ing.exists() else []
    assert finals == [] and env.ledger.rows() == []


# ------------------------------------------------------------------------------------------------ route and agent tool
from starlette.testclient import TestClient  # noqa: E402

from lampway_server.app import create_app  # noqa: E402


def test_the_route_needs_the_bearer_and_the_agent_tool_only_proposes(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        assert http.post("/app/video/ingest", json={"url": "https://example.com/v"}).status_code == 401
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        r = http.post("/app/video/ingest", headers=fake.rest_headers(), json={"url": "file:///etc/passwd", "confirmed": True})
        assert r.status_code == 422 and "http or https" in r.json()["detail"]
        card = http.post("/app/video/ingest", headers=fake.rest_headers(), json={"url": "https://example.com/v"}).json()
        assert card["state"] == "needs_approval"
    import asyncio
    from lampway_server.agent import video_tools as VT
    class Sys:                              # noqa: E301
        root = tmp_path
    out, err = asyncio.run(VT.call(Sys(), "lampway_video_ingest_url", {"url": "https://example.com/v"}))
    assert err is False and json.loads(out)["state"] == "needs_approval" and "lampway_video_ingest_url" in VT.NAMES
