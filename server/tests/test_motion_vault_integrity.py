# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Causal plants for immutable filing and replayable motion relationships."""
import json
import hashlib
import asyncio
import threading
from pathlib import Path

import pytest

from lampway_server import motion as M
from lampway_server.agent import motion_tools as MT
from lampway_server.library import curate as CU
from lampway_server.library import provenance as PV
from lampway_server.library.store import LibraryError
from lampway_server.motion import receipt as R
from lampway_server.motion import frames as F
from lampway_server.motion.cancellation import Cancellation, MotionCancelled

from .fake_motion import FakeCapture
from .test_motion_graphics import SMALL, a_vault, put_scene, tool


@pytest.mark.parametrize("target", ["mp4", "webm", "receipt", "contact"])
def test_handoff_never_imports_swapped_or_corrupt_artifacts(tmp_path, monkeypatch, target):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    original = M.render
    expected = {}

    def swapped(*args, **kwargs):
        out = original(*args, **kwargs)
        receipt = json.loads((project / out["out_dir"] / "receipt.json").read_text())
        for fmt, path in receipt["files"].items():
            if fmt in ("mp4", "webm", "receipt", "contact"):
                expected[fmt] = hashlib.sha256((project / path).read_bytes()).hexdigest()
        path = project / receipt["files"][target]
        path.unlink()
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"unchecked outside bytes")
        path.symlink_to(outside)
        return out

    monkeypatch.setattr(M, "render", swapped)
    out, error = tool(project, {"scene": put_scene(project, "sealed", "<!doctype html>"), **SMALL}, vault=vault, capture=FakeCapture)
    assert not error, out
    assert out["vault"]["filed"], out
    for asset in out["vault"]["assets"]:
        assert vault.lib.get(asset["id"])["files"][0]["sha256"] == expected[asset["format"]]


class ClosedVault:
    def __init__(self, spool):
        self.spool = spool

    @property
    def lib(self):
        raise LibraryError("closed for test")


@pytest.mark.parametrize("formats", [["mp4", "webm"], ["webm"], ["mp4"]])
def test_spool_replay_restores_motion_relationships_exactly_once(tmp_path, formats):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    closed = ClosedVault(tmp_path / "state" / "motion-spool.jsonl")
    out, error = tool(project, {"scene": put_scene(project, "spooled", "<!doctype html>"), **SMALL, "formats": formats},
                      vault=closed, capture=FakeCapture)
    assert not error and out["vault"]["spooled"], out
    assert PV.replay_spool(vault.lib, closed.spool) == {"replayed": 1, "still_failing": 0}
    assert PV.replay_spool(vault.lib, closed.spool) == {"replayed": 0, "still_failing": 0}
    relationships = list(vault.lib._reader().execute("SELECT type,src,dst FROM relation"))
    assert len(relationships) == 2 + (len(formats) - 1)
    assert sum(r["type"] == "derived_from" for r in relationships) == 2
    assert sum(r["type"] == "variant_of" for r in relationships) == len(formats) - 1
    assert vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0] == len(formats) + 2


def test_relation_failure_reports_committed_assets_and_replay_recovers(tmp_path, monkeypatch):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    original = CU.relate

    def broken(*args, **kwargs):
        raise LibraryError("planted edge failure")

    monkeypatch.setattr(CU, "relate", broken)
    out, error = tool(project, {"scene": put_scene(project, "partial", "<!doctype html>"), **SMALL}, vault=vault, capture=FakeCapture)
    assert not error and out["ok"], out
    status = out["vault"]
    assert not status["filed"] and status["partial"] and status["spooled"], status
    assert len(status["assets"]) == 4 and "planted edge failure" in status["error"]
    monkeypatch.setattr(CU, "relate", original)
    assert PV.replay_spool(vault.lib, vault.spool) == {"replayed": 1, "still_failing": 0}
    assert vault.lib._reader().execute("SELECT count(*) FROM relation").fetchone()[0] == 3


def test_corrupted_spool_blob_cannot_be_imported(tmp_path):
    vault = a_vault(tmp_path)
    closed = ClosedVault(tmp_path / "state" / "motion-spool.jsonl")
    result = PV.capture(None, closed.spool, {"generation": {"action": "motion_graphics", "job_id": "sealed-spool", "params": {"fps": 10}},
                                           "outputs": [{"kind": "video", "subtype": "render", "name": "sealed.mp4", "bytes": b"checked capture bytes"}]})
    assert result["spooled"], result
    payload = json.loads(closed.spool.read_text())["payload"]
    Path(payload["outputs"][0]["path"]).write_bytes(b"changed after checked capture")
    assert PV.replay_spool(vault.lib, closed.spool) == {"replayed": 0, "still_failing": 1}
    assert vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0] == 0


def test_contact_corruption_before_sealing_is_refused(tmp_path, monkeypatch):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    original = R.seal

    def corrupt(receipt, out, root, **kwargs):
        (out / "contact.png").write_bytes(b"changed after generation before seal")
        return original(receipt, out, root, **kwargs)

    monkeypatch.setattr(R, "seal", corrupt)
    result, error = tool(project, {"scene": put_scene(project, "bad-contact", "<!doctype html>"), **SMALL},
                         vault=vault, capture=FakeCapture)
    assert error and "contact" in result["error"], result
    assert vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0] == 0


def test_cancellation_during_first_vault_commit_reports_only_that_asset(tmp_path, monkeypatch):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    scene = put_scene(project, "cancel-filing", "<!doctype html>")
    entered, release = threading.Event(), threading.Event()
    original = vault.lib.put
    committed = []

    def blocked(spec):
        result = original(spec)
        committed.append(result["id"])
        entered.set()
        assert release.wait(10), "test must release the admitted Vault commit"
        return result

    monkeypatch.setattr(vault.lib, "put", blocked)

    async def run():
        task = asyncio.create_task(MT.call(vault, project, MT.NAME, {"scene": scene, **SMALL}, capture=FakeCapture))
        assert await asyncio.to_thread(entered.wait, 10), "render must reach the first Vault commit"
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        text, error = await task
        result = json.loads(text)
        assert error and result["cancelled"], result
        assert len(committed) == 1
        assert [a["id"] for a in result["vault"]["assets"]] == committed
        assert result["vault"]["partial"] and not result["vault"]["filed"] and not result["vault"]["spooled"]
        assert vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0] == 1
        assert vault.lib._reader().execute("SELECT count(*) FROM relation").fetchone()[0] == 0

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_two_identical_closed_vault_runs_replay_shared_blobs_and_exact_edges(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    scene = put_scene(project, "shared-spool", "<!doctype html>")
    closed = ClosedVault(tmp_path / "state" / "motion-spool.jsonl")
    for _ in range(2):
        out, error = tool(project, {"scene": scene, **SMALL, "formats": ["mp4"]}, vault=closed, capture=FakeCapture)
        assert not error and out["vault"]["spooled"], out
    rows = [json.loads(line) for line in closed.spool.read_text().splitlines()]
    assert rows[0]["payload"]["outputs"][0]["path"] == rows[1]["payload"]["outputs"][0]["path"]
    assert PV.replay_spool(vault.lib, closed.spool) == {"replayed": 2, "still_failing": 0}
    assert PV.replay_spool(vault.lib, closed.spool) == {"replayed": 0, "still_failing": 0}
    relations = list(vault.lib._reader().execute("SELECT type,src,dst FROM relation"))
    assert len(relations) == 3 and all(r["type"] == "derived_from" for r in relations)
    assert len({r["dst"] for r in relations}) == 1
    assert vault.lib._reader().execute("SELECT count(*) FROM asset WHERE kind='receipt'").fetchone()[0] == 2
    assert not list((closed.spool.parent / "spool_blobs").iterdir())


@pytest.mark.parametrize("failure", ["corrupt_blob", "torn_row"])
def test_spool_cleanup_preserves_bytes_referenced_by_retained_evidence(tmp_path, failure):
    vault = a_vault(tmp_path)
    spool = tmp_path / "state" / "retained-spool.jsonl"
    first = {"generation": {"action": "motion_graphics", "job_id": "shared-first", "params": {"fps": 10}},
             "outputs": [{"kind": "video", "name": "shared.mp4", "bytes": b"shared checked bytes"}]}
    assert PV.capture(None, spool, first)["spooled"]
    shared = Path(json.loads(spool.read_text())["payload"]["outputs"][0]["path"])
    if failure == "torn_row":
        with spool.open("a") as stream:
            stream.write('{"payload":')
    else:
        second = {"generation": {"action": "motion_graphics", "job_id": "shared-second", "params": {"fps": 10}},
                  "outputs": [first["outputs"][0], {"kind": "receipt", "subtype": "qa", "name": "unique receipt", "bytes": b"expected unique bytes"}]}
        assert PV.capture(None, spool, second)["spooled"]
        second_row = json.loads(spool.read_text().splitlines()[1])
        Path(second_row["payload"]["outputs"][1]["path"]).write_bytes(b"corrupt evidence")
    assert PV.replay_spool(vault.lib, spool) == {"replayed": 1, "still_failing": 1}
    assert shared.read_bytes() == b"shared checked bytes"
    assert spool.read_text().strip()


def _dedup_payload(job):
    return {"generation": {"action": "motion_graphics", "job_id": job, "params": {"fps": 10}},
            "outputs": [{"kind": "video", "subtype": "render", "name": "dedup.mp4", "bytes": b"real dedup bytes"}],
            "output_relations": []}


def test_dedup_generation_failure_reports_asset_and_spools_reconciliation(tmp_path, monkeypatch):
    vault = a_vault(tmp_path)
    seed = PV.record(vault.lib, _dedup_payload("dedup-seed"))["assets"][0]["id"]
    original = vault.lib.add_generation

    def fail(*args, **kwargs):
        raise LibraryError("planted dedup bookkeeping failure")

    monkeypatch.setattr(vault.lib, "add_generation", fail)
    result = PV.capture(vault.lib, vault.spool, _dedup_payload("dedup-second"))
    assert not result["ok"] and result["spooled"] and result.get("partial"), result
    assert [asset["id"] for asset in result["assets"]] == [seed]
    monkeypatch.setattr(vault.lib, "add_generation", original)
    assert PV.replay_spool(vault.lib, vault.spool) == {"replayed": 1, "still_failing": 0}
    assert vault.lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0] == 1
    assert vault.lib._reader().execute("SELECT count(*) FROM generation WHERE job_id='dedup-second'").fetchone()[0] == 1


def test_cancel_after_dedup_put_does_not_admit_generation_mutation(tmp_path, monkeypatch):
    vault = a_vault(tmp_path)
    seed = PV.record(vault.lib, _dedup_payload("dedup-seed"))["assets"][0]["id"]
    cancel = Cancellation()
    original = vault.lib.put

    def cancel_after_put(spec):
        result = original(spec)
        assert result["deduped"]
        cancel.cancel()
        return result

    monkeypatch.setattr(vault.lib, "put", cancel_after_put)
    with pytest.raises(MotionCancelled):
        PV.capture(vault.lib, vault.spool, _dedup_payload("dedup-cancelled"), cancel=cancel)
    assert cancel.snapshot_assets() == [{"id": seed, "kind": "video"}]
    assert vault.lib._reader().execute("SELECT count(*) FROM generation WHERE job_id='dedup-cancelled'").fetchone()[0] == 0
    assert not vault.spool.exists()


def test_cancelled_direct_filing_does_not_open_artifacts(tmp_path, monkeypatch):
    cancel = Cancellation()
    cancel.cancel()

    def forbidden_open(*args, **kwargs):
        pytest.fail("cancelled direct filing must not open artifact files")

    monkeypatch.setattr(F, "_open_scene_file", forbidden_open)
    with pytest.raises(MotionCancelled):
        R.file_in_vault(a_vault(tmp_path), tmp_path, {"out_dir": "motion/out/direct", "files": {"mp4": "direct.mp4"}}, cancel=cancel)
