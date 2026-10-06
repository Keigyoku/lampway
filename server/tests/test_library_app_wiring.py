"""The production server wires the Vault: a generation the job queue finishes lands in the library with its lineage (the hook exists in library/hooks.py; this proves
create_app passes it). A second server on the same state dir cannot take the writer lock, so its generations are spooled, never lost."""
import pytest

from lampway_server.app import create_app
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.jobqueue import ImageOutput
from lampway_server.library.store import AssetLibrary

pytestmark = pytest.mark.anyio
PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 32


def image_backend(model, payload):
    return ImageOutput(images=[(PNG, "image/png")], image_name="")


async def test_a_finished_generation_lands_in_the_vault_with_its_prompt(settings):
    app = create_app(settings, provider=ScriptedProvider(), job_backends={"image_gen": image_backend})
    job = app.state.jobs.submit("image_gen", "openai/gpt-image-2.5", {"prompt": "a brass lamp on slate"})
    await job.task
    assert job.status == "DONE"
    lib = app.state.library
    assert lib.root == settings.state_dir / "library"
    img = [r[0] for r in lib._db.execute("select id from asset where kind='image'")]
    assert len(img) == 1
    g = lib.get(img[0])["generation"][0]
    assert (g["action"], g["model"], g["job_id"]) == ("image_gen", "openai/gpt-image-2.5", job.job_id)
    prompt = lib.get(g["prompt_asset"])                                   # the lineage: the image's generation row names its prompt asset
    assert prompt["kind"] == "prompt" and open(prompt["files"][0]["locations"][0]["path"], "rb").read() == b"a brass lamp on slate"


async def test_with_the_vault_locked_by_another_writer_generations_are_spooled(settings):
    other = AssetLibrary(settings.state_dir / "library")                  # another server process holds the one writer lock
    try:
        app = create_app(settings, provider=ScriptedProvider(), job_backends={"image_gen": image_backend})
        assert app.state.library is None
        job = app.state.jobs.submit("image_gen", "m", {"prompt": "x"})
        await job.task
        assert job.status == "DONE"
        assert len((settings.state_dir / "library-spool.jsonl").read_text().splitlines()) == 1
    finally:
        other.close()


async def test_a_spool_left_by_a_locked_period_is_replayed_when_the_server_opens_the_vault(settings):
    other = AssetLibrary(settings.state_dir / "library")
    try:
        locked = create_app(settings, provider=ScriptedProvider(), job_backends={"image_gen": image_backend})
        job = locked.state.jobs.submit("image_gen", "m", {"prompt": "spooled lamp"})
        await job.task
    finally:
        other.close()
    app = create_app(settings, provider=ScriptedProvider(), job_backends={})
    lib = app.state.library
    assert [r[0] for r in lib._db.execute("select g.job_id from generation g join version v on v.id=g.version_id join asset a on a.id=v.asset_id where a.kind='image'")] == [job.job_id]


def test_a_torn_spool_line_never_stops_the_server_starting(settings):
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    (settings.state_dir / "library-spool.jsonl").write_text('{"payload": {"outp')                # a crash mid-write
    app = create_app(settings, provider=ScriptedProvider(), job_backends={})
    assert app.state.library is not None
