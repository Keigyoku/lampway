"""engine_project adapters (specs/mrmak/11-engine-project-adapter.md): which engine project an asset belongs to, in what version, and what may be offered about it. Read-only, no command is ever run."""
import json
import os
from pathlib import Path

import pytest

from lampway_server.engine_projects import registry as R
from lampway_server.engine_projects.contracts import ProjectError
from lampway_server.engine_projects import unreal, godot, generic


def uproject(root: Path, name="Titan", assoc="5.8", modules=("TitanCore",), plugins=("GameplayAbilities",)):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.uproject").write_text(json.dumps({"FileVersion": 3, "EngineAssociation": assoc, "Modules": [{"Name": m} for m in modules],
                                                      "Plugins": [{"Name": p, "Enabled": True} for p in plugins] + [{"Name": "Off", "Enabled": False}]}))
    (root / "Config").mkdir(exist_ok=True)
    (root / "Config" / "DefaultEngine.ini").write_text("[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Game/Maps/Entry.Entry\nOther=1\n")
    return root


def test_unreal_detection_walks_up_and_parses_the_uproject(tmp_path):
    proj = uproject(tmp_path / "Titan")
    start = proj / "Content" / "Chars" / "Boots"
    start.mkdir(parents=True)
    ms = R.detect(start, roots=[tmp_path])
    top = ms[0]
    assert top["adapter_id"] == "unreal" and top["root"] == str(proj) and top["name"] == "Titan" and top["confidence"] >= 0.9
    md = top["metadata"]
    assert md["engine_association"] == "5.8" and md["default_map"] == "/Game/Maps/Entry.Entry" and md["modules"] == ["TitanCore"] and md["plugins_enabled"] == ["GameplayAbilities"]
    assert ms[-1]["adapter_id"] == "generic" and ms[-1]["confidence"] == 0.01


def test_two_uprojects_in_one_folder_are_two_matches_and_no_project_is_only_the_generic_fallback(tmp_path):
    both = tmp_path / "both"
    uproject(both, "A")
    (both / "B.uproject").write_text(json.dumps({"EngineAssociation": "5.8"}))
    unreal_matches = [m for m in R.detect(both, roots=[tmp_path]) if m["adapter_id"] == "unreal"]
    assert len(unreal_matches) == 2 and all(m["confidence"] == 0.5 and "two .uproject files here" in m["reason"] for m in unreal_matches)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert [m["adapter_id"] for m in R.detect(empty, roots=[tmp_path])] == ["generic"]


def test_the_ancestor_walk_is_bounded_at_twelve_levels(tmp_path):
    proj = uproject(tmp_path / "Titan")
    near = proj
    for i in range(12):
        near = near / f"d{i}"
    near.mkdir(parents=True)
    far = near / "one_more"
    far.mkdir()
    assert any(m["adapter_id"] == "unreal" for m in R.detect(near, roots=[tmp_path]))               # 12 levels up: found
    assert not any(m["adapter_id"] == "unreal" for m in R.detect(far, roots=[tmp_path]))            # 13: not found, never a walk to the filesystem root


def test_the_engine_dir_resolves_by_version_string_and_a_guid_association_is_unresolved(tmp_path):
    eng = tmp_path / "UE_5.8"
    (eng / "Engine" / "Build").mkdir(parents=True)
    (eng / "Engine" / "Build" / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 1}))
    other = tmp_path / "UE_5.7"
    (other / "Engine" / "Build").mkdir(parents=True)
    (other / "Engine" / "Build" / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 0}))
    p1 = uproject(tmp_path / "P1", assoc="5.8")
    p2 = uproject(tmp_path / "P2", assoc="{12345678-1234-1234-1234-123456789ABC}")
    m1 = R.detect(p1, roots=[tmp_path], ue_engine_dirs=[str(other), str(eng)])[0]["metadata"]
    m2 = R.detect(p2, roots=[tmp_path], ue_engine_dirs=[str(other), str(eng)])[0]["metadata"]
    assert m1["engine_dir"] == str(eng) and m2["engine_dir"] is None and m2["engine_association_kind"] == "guid" and "unresolved" in m2["engine_note"]


def test_files_are_capped_content_is_counted_not_listed_and_junk_folders_are_skipped(tmp_path):
    proj = uproject(tmp_path / "Titan")
    for d in ("Intermediate", "Saved", "Binaries", "DerivedDataCache", ".git"):
        (proj / d).mkdir()
        (proj / d / "junk.ini").write_text("x")
    (proj / "Config" / "Saved").mkdir()
    (proj / "Config" / "Saved" / "junk2.ini").write_text("x")                  # a skipped folder INSIDE a scanned one
    (proj / "Source" / "TitanCore").mkdir(parents=True)
    (proj / "Source" / "TitanCore" / "TitanCore.Build.cs").write_text("// build")
    (proj / "Content" / "Chars").mkdir(parents=True)
    for i in range(5):
        (proj / "Content" / "Chars" / f"a{i}.uasset").write_text("x")
    (proj / "Content" / "Chars" / "m.umap").write_text("x")
    caps = R.capabilities(proj, "unreal", roots=[tmp_path])
    names = [f["path"] for f in caps["files"]]
    assert "Titan.uproject" in names and "Config/DefaultEngine.ini" in names and "Source/TitanCore/TitanCore.Build.cs" in names
    assert not any("junk" in n or n.endswith(".uasset") for n in names)
    counts = {c["path"]: c for c in caps["content_counts"]}
    assert counts["Content/Chars"]["uasset"] == 5 and counts["Content/Chars"]["umap"] == 1
    big = uproject(tmp_path / "Big")
    (big / "Config" / "gen").mkdir()
    for i in range(2100):
        (big / "Config" / "gen" / f"g{i}.ini").write_text("x")
    assert len(R.capabilities(big, "unreal", roots=[tmp_path])["files"]) == 2000


def test_commands_are_descriptions_that_exist_only_when_the_executable_exists_and_nothing_runs_them(tmp_path):
    proj = uproject(tmp_path / "Titan")
    eng = tmp_path / "UE_5.8"
    (eng / "Engine" / "Build").mkdir(parents=True)
    (eng / "Engine" / "Build" / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 8}))
    (eng / "Engine" / "Binaries" / "Linux").mkdir(parents=True)
    exe = eng / "Engine" / "Binaries" / "Linux" / "UnrealEditor"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    caps = R.capabilities(proj, "unreal", roots=[tmp_path], ue_engine_dirs=[str(eng)])
    cmds = {c["id"]: c for c in caps["commands"]}
    assert cmds["ue-editor"]["safety"] == "open" and cmds["ue-editor"]["executable"] == str(exe) and str(proj / "Titan.uproject") in cmds["ue-editor"]["args"]
    no_engine = R.capabilities(proj, "unreal", roots=[tmp_path], ue_engine_dirs=[])
    assert no_engine["commands"] == []
    headless = R.capabilities(proj, "unreal", roots=[tmp_path], ue_engine_dirs=[str(eng)], run_script="Scripts/import.py")
    assert next(c for c in headless["commands"] if c["id"] == "ue-run-script")["safety"] == "run" and "reason" in next(c for c in headless["commands"] if c["id"] == "ue-run-script")["metadata"]
    assert not any(hasattr(R, n) for n in ("run", "execute", "launch", "spawn"))


def test_godot_adapter_matches_the_upstream_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(godot.shutil, "which", lambda n: None)
    g = tmp_path / "game"
    (g / "scenes" / "deep").mkdir(parents=True)
    (g / "project.godot").write_text('config_version=5\n\n[application]\nconfig/name="Sky Game"\nrun/main_scene="res://scenes/main.tscn"\nconfig/features=PackedStringArray("4.3", "Forward Plus")\nconfig/icon="res://icon.svg"\n\n[display]\nwindow/size/viewport_width=640\n')
    (g / "scenes" / "main.tscn").write_text("[gd_scene]")
    (g / ".godot").mkdir()
    (g / ".godot" / "cache.tmp").write_text("x")
    ms = R.detect(g / "scenes" / "deep", roots=[tmp_path])
    top = ms[0]
    assert top["adapter_id"] == "godot" and top["name"] == "Sky Game" and top["metadata"]["main_scene"] == "res://scenes/main.tscn" and top["metadata"]["features"] == ["4.3", "Forward Plus"]
    caps = R.capabilities(g, "godot", roots=[tmp_path])
    assert "scenes/main.tscn" in [f["path"] for f in caps["files"]] and not any(f["path"].startswith(".godot") for f in caps["files"]) and caps["commands"] == []     # no godot executable: no commands


def test_a_path_outside_the_enrolled_roots_and_a_symlink_escape_are_refused(tmp_path):
    inside = tmp_path / "in"
    outside = tmp_path / "out"
    uproject(outside / "Secret")
    inside.mkdir()
    with pytest.raises(ProjectError, match="enrol the folder first: engine_project_roots"):
        R.detect(outside / "Secret", roots=[inside])
    os.symlink(outside / "Secret", inside / "link")
    with pytest.raises(ProjectError, match="enrol the folder first"):
        R.detect(inside / "link", roots=[inside])
    with pytest.raises(ProjectError, match="Unknown project adapter"):
        R.capabilities(inside, "nope", roots=[inside])


def test_the_registry_sorts_by_confidence_then_id_and_drops_a_failing_adapter(tmp_path, monkeypatch):
    proj = uproject(tmp_path / "Titan")
    def boom(*a, **k):
        raise RuntimeError("adapter bug")
    monkeypatch.setattr(godot, "detect", boom)
    ms = R.detect(proj, roots=[tmp_path])
    ids = [(m["confidence"], m["adapter_id"]) for m in ms]
    assert ids == sorted(ids, key=lambda x: (-x[0], x[1])) and "godot" not in [m["adapter_id"] for m in ms] and ms[0]["adapter_id"] == "unreal"


@pytest.mark.anyio
async def test_the_agent_tool_detects_describes_and_refuses_outside_the_roots(tmp_path, monkeypatch):
    from lampway_server.agent import engine_tools as ET
    from lampway_server.agent import tools as T
    proj = uproject(tmp_path / "project" / "Titan")
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "project"))
    out, err = await ET.call("lampway_engine_project", {"action": "detect", "path": "Titan/Content"} if (proj / "Content").exists() else {"action": "detect", "path": "Titan"})
    assert not err and json.loads(out)["matches"][0]["adapter_id"] == "unreal"
    caps, err = await ET.call("lampway_engine_project", {"action": "capabilities", "path": "Titan", "adapter": "unreal"})
    assert not err and json.loads(caps)["project"]["name"] == "Titan"
    bad, err = await ET.call("lampway_engine_project", {"action": "detect", "path": str(tmp_path)})
    assert err and "enrol the folder first" in bad
    assert "lampway_engine_project" in {t.name for t in T.TOOLS}
