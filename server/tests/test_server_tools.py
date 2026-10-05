"""Server-side agent tools: the studio drivers. They never go through Blender; the agent loop runs them locally as a
subprocess under the configured browser python. Read-only and dry-run by default; a generation needs BOTH dry_run=false in
the call AND the owner's LAMPWAY_STUDIO_ARMED=1 in the server's environment (the driver refuses otherwise)."""

import pytest

from lampway_server.agent import server_tools as ST
from lampway_server.agent import tools as T
from lampway_server.agent.providers.base import Text, ToolCall
from tests.test_agent_turn import start_chat


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_PYTHON_BROWSER", "/venv/bin/python")
    return tmp_path


def test_the_studio_tools_are_listed_and_marked_local():
    names = {t.name for t in T.TOOLS}
    for n in ("studio_tripo_state", "studio_tripo_image", "studio_tripo_mesh", "studio_tripo_fetch", "studio_seed_catalog"):
        assert n in names and ST.is_local(n)
    assert not ST.is_local("lampway_qa_candidates") and not ST.is_local("run_blender_python")


def test_image_generation_is_a_dry_run_unless_the_call_says_otherwise(root):
    cmd = ST.command("studio_tripo_image", {"out_dir": "plates/g1", "prompt_file": "plates/p.txt", "refs": ["plates/v3.png"]})
    assert cmd[:3] == ["/venv/bin/python", "-m", "lampway_server.studios.tripo.tripo_image"]
    assert "--dry-run" in cmd
    assert cmd[3] == str(root / "plates/g1") and cmd[4] == str(root / "plates/p.txt")
    assert cmd[cmd.index("--ref") + 1] == str(root / "plates/v3.png")
    with pytest.raises(ST.BadToolCall, match="captain"):                  # a real run is the captain's confirm in the Client, never the agent's
        ST.command("studio_tripo_image", {"out_dir": "o", "prompt_file": "p", "dry_run": False})


def test_the_image_count_is_never_below_four(root):
    cmd = ST.command("studio_tripo_image", {"out_dir": "o", "prompt_file": "p"})
    assert cmd[cmd.index("--count") + 1] == "4"
    with pytest.raises(ST.BadToolCall):
        ST.command("studio_tripo_image", {"out_dir": "o", "prompt_file": "p", "count": "2"})


def test_mesh_generation_takes_the_four_cardinal_views_and_defaults_to_a_dry_run(root):
    cmd = ST.command("studio_tripo_mesh", {"out_dir": "m", "front": "f.png", "left": "l.png", "right": "r.png", "back": "b.png"})
    assert "--dry-run" in cmd and cmd[cmd.index("--topology") + 1] == "Quad"
    with pytest.raises(ST.BadToolCall, match="back"):
        ST.command("studio_tripo_mesh", {"out_dir": "m", "front": "f", "left": "l", "right": "r"})


def test_every_path_is_jailed_to_the_project_root(root):
    with pytest.raises(ST.BadToolCall, match="outside the project root"):
        ST.command("studio_tripo_image", {"out_dir": "/etc", "prompt_file": "p"})
    with pytest.raises(ST.BadToolCall, match="outside the project root"):
        ST.command("studio_tripo_fetch", {"out_dir": "../x", "stamp": "10-04 12:00"})


def test_the_environment_the_driver_gets_carries_the_arming_only_from_the_servers_own(root, monkeypatch):
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    assert "LAMPWAY_STUDIO_ARMED" not in ST.environment()
    monkeypatch.setenv("LAMPWAY_STUDIO_ARMED", "1")
    assert ST.environment()["LAMPWAY_STUDIO_ARMED"] == "1"            # the owner's setting, passed on; a tool call cannot set it


def test_a_tool_call_cannot_arm_the_guard(root):
    cmd = ST.command("studio_tripo_state", {"LAMPWAY_STUDIO_ARMED": "1", "env": {"LAMPWAY_STUDIO_ARMED": "1"}})
    assert "LAMPWAY_STUDIO_ARMED=1" not in " ".join(cmd)


def test_run_returns_the_drivers_output_and_marks_a_nonzero_exit_as_an_error(root, monkeypatch):
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (1, "error: studio guard is not armed\n"))
    text, is_error = ST.run("studio_tripo_state", {})
    assert is_error is True and "not armed" in text
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (0, "bin: x\ncredits: 9000\n"))
    assert ST.run("studio_tripo_state", {}) == ("bin: x\ncredits: 9000\n", False)


def test_a_studio_tool_in_a_turn_never_asks_blender_for_a_script(fake, provider, monkeypatch, root):
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (0, "credits: 9000\n"))
    provider.script.append([Text("Checking Studio."), ToolCall(id="c1", name="studio_tripo_state", arguments={})])
    provider.script.append([Text("Done.")])
    scripts = []
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, command_id = start_chat(fake, ws, "what is in Studio?")
        frames = fake.run_turn(ws, command_id, on_script=lambda p: scripts.append(p) or fake.execute_script_result(p["script"]))
    assert scripts == []
    assert any(f.get("method") == "agent.turn.ended" for f in frames)
    tool_result = [m for m in provider.requests[-1].messages[-1].content if m.get("type") == "tool_result"][0]
    assert "credits: 9000" in tool_result["content"]


# ---- the image backend as a tool (mesh-paint)

def test_the_image_generate_tool_is_listed_local_and_defaults_to_not_live(root):
    assert ST.is_local("studio_image_generate")
    spec = next(t for t in T.TOOLS if t.name == "studio_image_generate")
    assert "prompt_file" in spec.parameters["required"] and "dry run" in spec.description.lower()


def test_it_calls_the_backend_with_jailed_paths_and_reports_the_files(root, monkeypatch):
    from lampway_server import imagegen as IG
    seen = {}

    def fake(backend, prompt_file, refs, out_dir, count=4, live=False, size="", aspect_ratio=""):
        seen.update(backend=backend, prompt_file=prompt_file, refs=refs, out_dir=out_dir, count=count, live=live, size=size, aspect_ratio=aspect_ratio)
        return {"backend": backend, "files": [str(root / "runs/1.png")], "dry_run": not live, "output": "ok"}

    monkeypatch.setattr(IG, "generate", fake)
    text, is_error = ST.run("studio_image_generate", {"prompt_file": "p.txt", "refs": ["clay.png"], "out_dir": "runs/Front", "backend": "codex_cli"})
    assert is_error is False and "runs/1.png" in text and seen["live"] is False and seen["backend"] == "codex_cli"
    ST.run("studio_image_generate", {"prompt_file": "p.txt", "out_dir": "runs/Front", "live": True})
    assert seen["live"] is True


def test_a_refusal_from_the_backend_is_an_error_result(root, monkeypatch):
    from lampway_server import imagegen as IG

    def boom(*a, **k):
        raise IG.ImageGenError("the Tripo driver refused or failed: not armed")

    real = IG.generate
    monkeypatch.setattr(IG, "generate", boom)
    text, is_error = ST.run("studio_image_generate", {"prompt_file": "p.txt", "out_dir": "o"})
    assert is_error is True and "not armed" in text
    monkeypatch.setattr(IG, "generate", real)
    text, is_error = ST.run("studio_image_generate", {"prompt_file": "/etc/passwd", "out_dir": "o"})
    assert is_error is True and "outside the project root" in text


# ---- the Texture + PBR driver as server tools: no --go unless dry_run is false; the driver's own guard still needs arming

def test_the_texture_tool_sets_and_verifies_without_go_by_default(monkeypatch, tmp_path):
    from lampway_server.agent import server_tools as ST
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    cmd = ST.command("studio_tripo_texture", {"res": "8K", "remove_lighting": True, "expect_price": 30})
    assert cmd[1:3] == ["-m", "lampway_server.studios.tripo.tripo_texture"] and cmd[3] == "texture"
    assert "--res" in cmd and cmd[cmd.index("--res") + 1] == "8K" and "--remove-lighting" in cmd
    assert cmd[cmd.index("--expect-price") + 1] == "30" and "--go" not in cmd
    for tool, args in (("studio_tripo_texture", {"res": "8K", "expect_price": 30, "dry_run": False, "out_dir": "tex/run1"}),
                       ("studio_tripo_pbr", {"expect_price": 5, "dry_run": False, "out_dir": "tex/run2"}),
                       ("studio_tripo_mesh", {"out_dir": "m", "front": "f", "left": "l", "right": "r", "back": "b", "dry_run": False})):
        with pytest.raises(ST.BadToolCall, match="captain"):
            ST.command(tool, args)


def test_the_pbr_restore_refs_and_state_verbs_are_tools(monkeypatch, tmp_path):
    from lampway_server.agent import server_tools as ST
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    assert ST.command("studio_tripo_texture_state", {})[3] == "state"
    pbr = ST.command("studio_tripo_pbr", {"expect_price": 5})
    assert pbr[3] == "pbr" and pbr[pbr.index("--expect-price") + 1] == "5" and "--go" not in pbr
    restore = ST.command("studio_tripo_restore", {"stamp": "10-05 14:02"})
    assert restore[3:] == ["restore", "--stamp", "10-05 14:02"]
    for v in ("front", "left", "right", "back"):
        (tmp_path / f"{v}.png").write_bytes(b"x")
    refs = ST.command("studio_tripo_refs", {"front": "front.png", "left": "left.png", "right": "right.png", "back": "back.png"})
    assert refs[3] == "refs" and refs[refs.index("--back") + 1] == str(tmp_path / "back.png")
    assert all(ST.is_local(n) for n in ("studio_tripo_texture", "studio_tripo_pbr", "studio_tripo_restore", "studio_tripo_refs", "studio_tripo_texture_state"))
    spec = ST.BY_NAME["studio_tripo_texture"].spec()
    assert "credits" in spec.description and "dry_run" in spec.parameters["properties"]
