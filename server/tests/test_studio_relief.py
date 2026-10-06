"""tripo.relief (specs/shelf/relief_map.md): Tripo's free 3D Relief Generator as a Studio action: a free job (no credits, no approval) that runs the bundled
relief_gen driver on 1-16 plate images inside the project root and writes <stem>.relief.png (+ .json) into a fresh job directory. Its label says the plates
are uploaded to tripo3d.ai."""

import asyncio

import pytest

from lampway_server.studios.actions import ACTIONS, ActionError

from tests.test_studio_service import svc

pytestmark = pytest.mark.anyio


def test_the_relief_action_is_a_free_job_that_names_the_upload():
    a = ACTIONS["tripo.relief"]
    assert a.needs_approval is False and a.driver == "relief_gen" and a.needs_out_dir is True
    assert "uploads" in a.label and "tripo3d.ai" in a.label


def test_a_plan_runs_the_driver_at_once_on_the_jailed_images(tmp_path):
    s, ex, root = svc(tmp_path, {"relief_gen": "files: 2\n"}, shelf=False)
    out = asyncio.run(s.plan("tripo.relief", {"images": ["plates/front.png", "plates/back.png"], "adjust": "0.1,0,-0.2"}, "agent"))
    assert out["state"] == "running", out
    argv = ex.calls[-1]["argv"]
    assert argv[-2].endswith("plates/front.png") and argv[-1].endswith("plates/back.png") and "--adjust" in argv and "0.1,0,-0.2" in argv, argv
    assert "/studio/job-" in argv[argv.index("--adjust") + 2], "the outputs land in a fresh job directory, never overwritten"


def test_refusals_before_any_driver_runs():
    v = ACTIONS["tripo.relief"].validate
    jail = lambda p: (_ for _ in ()).throw(ActionError(f"{p} is outside the project root")) if p.startswith("/") else p  # noqa: E731
    with pytest.raises(ActionError, match="1 to 16"):
        v({"images": []}, jail)
    with pytest.raises(ActionError, match="outside the project root"):
        v({"images": ["/etc/hostname"]}, jail)
    with pytest.raises(ActionError, match="C,B,S"):
        v({"images": ["a.png"], "adjust": "2,0"}, jail)
