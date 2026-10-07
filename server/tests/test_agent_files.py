"""agent_files (specs/mrmak/04): project instruction files and skills generated from the live tool registry, mirrored for Claude and Codex, checked, packed and verified; skills and notes read and written
safely (revision-checked, backed up, jailed). Deterministic: no model."""
import json
import os
import threading
import zipfile
from pathlib import Path

import pytest

from lampway_server.agent import tools as AT
from lampway_server.agent_files import generate as GEN
from lampway_server.agent_files import mirror as MIR
from lampway_server.agent_files import notes as NOTES
from lampway_server.agent_files import pack as PACK
from lampway_server.agent_files import roots as ROOTS
from lampway_server.agent_files import scaffold as SCAF


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


def registry_rows():
    return GEN.registry()


def test_every_offered_tool_is_in_a_generated_skill_or_excluded_with_a_reason_and_a_new_tool_turns_check_red(proj):
    rows = registry_rows()
    out = GEN.generate(proj, rows=rows)
    covered = {t for s in out["skills"] for t in s["tools_covered"]}
    excluded = {e["tool"]: e["reason"] for e in out["excluded"]}
    assert out["uncovered_tools"] == [] and covered.isdisjoint(excluded) and covered | set(excluded) == {r["name"] for r in rows}
    assert all(excluded[t] for t in excluded) and any(t.startswith("studio_") for t in excluded) and "ask_user" in excluded
    assert GEN.check(proj, rows=rows)["ok"] is True
    rows2 = rows + [{"name": "lampway_dummy_new_tool", "description": "A tool added after the skills were written.", "params": [], "offered": True}]
    chk = GEN.check(proj, rows=rows2)
    assert chk["ok"] is False and any("lampway_dummy_new_tool" in str(x) for x in chk["stale"])
    GEN.generate(proj, rows=rows2)
    assert GEN.check(proj, rows=rows2)["ok"] is True and "lampway_dummy_new_tool" in (proj / ".agents" / "skills" / "lampway-tools-misc" / "SKILL.md").read_text()


def test_scaffold_never_overwrites_a_hand_edited_file_and_is_idempotent(proj):
    (proj / "AGENTS.md").write_text("MY OWN RULES\n")
    a = SCAF.scaffold(proj)
    assert (proj / "AGENTS.md").read_text() == "MY OWN RULES\n" and "AGENTS.md" in a["skipped"] and "CLAUDE.md" in a["created"] and (proj / "context" / "preferences.md").exists()
    before = {str(p): p.read_bytes() for p in proj.rglob("*") if p.is_file()}
    b = SCAF.scaffold(proj)
    assert b["created"] == [] and {str(p): p.read_bytes() for p in proj.rglob("*") if p.is_file()} == before
    with pytest.raises(SCAF.ScaffoldError, match="exists: pass overwrite or pick another name"):
        SCAF.scaffold(proj, only=["AGENTS.md"], strict=True)
    assert not (proj / ".env").exists() and "KEY=" in (proj / ".env.example").read_text() and not any("=" in l.split("=", 1)[1].strip() and l.split("=", 1)[1].strip() for l in (proj / ".env.example").read_text().splitlines() if "=" in l and not l.startswith("#"))


def test_the_laws_text_has_a_real_source_line_for_every_sentence_and_a_wrong_line_fails(proj):
    repo = Path(__file__).resolve().parents[2]
    laws = GEN.laws()
    assert len(laws) >= 5
    for sentence, src in laws:
        f, line = src.rsplit(":", 1)
        text = (repo / f).read_text().splitlines()[int(line) - 1]
        words = [w for w in sentence.lower().replace("`", "").split() if len(w) > 4][:3]
        assert all(w in text.lower().replace("`", "") for w in words), (sentence, src, text)
    with pytest.raises(GEN.LawError):
        GEN.find_sentence("server/lampway_server/agent/prompt.py", "a sentence that is nowhere in that file")


def test_the_mirror_check_lists_a_one_byte_difference_and_sync_does_not_delete_a_destination_only_skill(proj):
    src, dst = proj / ".agents" / "skills", proj / ".claude" / "skills"
    (src / "a").mkdir(parents=True)
    (src / "a" / "SKILL.md").write_text("---\nname: a\ndescription: x\n---\nbody\n")
    (dst / "only-here").mkdir(parents=True)
    (dst / "only-here" / "SKILL.md").write_text("mine")
    assert MIR.check(proj)["ok"] is False and MIR.check(proj)["missing"] == ["a/SKILL.md"]
    MIR.sync(proj)
    assert MIR.check(proj)["ok"] is True and (dst / "only-here" / "SKILL.md").read_text() == "mine"
    (dst / "a" / "SKILL.md").write_bytes((src / "a" / "SKILL.md").read_bytes() + b"x")
    c = MIR.check(proj)
    assert c["ok"] is False and c["differing"] == ["a/SKILL.md"] and "run action=sync" in c["message"]
    (src / ".hidden").mkdir()
    (src / ".hidden" / "f.md").write_text("x")
    MIR.sync(proj)
    assert not (dst / ".hidden").exists()


def test_skill_read_refuses_credentials_dotfolders_symlink_escapes_and_pages_long_files(proj, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".codex" / "skills").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    sk = proj / ".agents" / "skills" / "demo"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: demo\ndescription: " + "d" * 300 + "\n---\n" + "x" * 30000)
    (sk / "auth.json").write_text("{}")
    (sk / ".env").write_text("K=1")
    (sk / "script.sh").write_text("echo")
    outside = home / "secret.md"
    outside.write_text("TOP SECRET")
    os.symlink(outside, sk / "escape.md")
    lst = ROOTS.list_skills(proj)
    assert lst[0]["name"] == "demo" and len(lst[0]["description"]) <= 260
    page = ROOTS.read_skill(proj, "demo")
    assert len(page["text"]) == 24000 and page["next_offset"] == 24000
    page2 = ROOTS.read_skill(proj, "demo", offset=24000)
    assert page2["next_offset"] is None
    for bad in ("demo/auth.json", "demo/.env", "demo/script.sh", "demo/escape.md", "../secret.md", "demo/../../outside.md", ".agents/skills/demo/.git/x"):
        with pytest.raises(ROOTS.ReadRefused):
            ROOTS.read_skill(proj, bad)
    big = sk / "big.md"
    big.write_bytes(b"a" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ROOTS.ReadRefused, match="2 MB"):
        ROOTS.read_skill(proj, "demo/big.md")


def _pack_dir(proj):
    GEN.generate(proj, rows=registry_rows())
    SCAF.scaffold(proj)
    return proj


def test_pack_build_then_verify_in_a_clean_directory_and_every_tamper_is_rejected(proj, tmp_path):
    _pack_dir(proj)
    z = tmp_path / "pack.zip"
    b = PACK.build(proj, z)
    assert b["ok"] and PACK.verify(z)["ok"] is True
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert "manifest.json" in names and any(n.startswith(".agents/skills/") for n in names) and any(n.startswith(".claude/skills/") for n in names)

    def rebuild(mod, name):
        out = tmp_path / name
        with zipfile.ZipFile(z) as src, zipfile.ZipFile(out, "w") as dst:
            for n in src.namelist():
                data = src.read(n)
                r = mod(n, data)
                if r is None:
                    continue
                for nn, dd in (r if isinstance(r, list) else [r]):
                    dst.writestr(nn, dd)
        return out
    first_skill = next(n for n in names if n.endswith("SKILL.md") and n.startswith(".agents/"))
    twin = first_skill.replace(".agents/", ".claude/", 1)
    cases = {
        "tampered": lambda n, d: (n, d + b"x") if n in (first_skill, twin) else (n, d),                     # both layouts agree with each other: only the manifest checksum can catch it
        "dotdot": lambda n, d: [(n, d)] + ([("../evil.md", b"x")] if n == "manifest.json" else []),
        "backslash": lambda n, d: [(n, d)] + ([("a\\b.md", b"x")] if n == "manifest.json" else []),
        "forbidden": lambda n, d: [(n, d)] + ([(".agents/skills/x/auth.json", b"{}")] if n == "manifest.json" else []),
        "broken_link": lambda n, d: None if n.endswith("lampway-laws/SKILL.md") and False else (n, d),
    }
    for name, fn in list(cases.items())[:4]:
        v = PACK.verify(rebuild(fn, name + ".zip"))
        assert v["ok"] is False and v["problems"], name
    assert any("checksum mismatch" in p for p in PACK.verify(rebuild(cases["tampered"], "t2.zip"))["problems"])
    dup = tmp_path / "dup.zip"
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(dup, "w") as dst:
        for n in names:
            dst.writestr(n, src.read(n))
        dst.writestr(first_skill, src.read(first_skill))
    assert PACK.verify(dup)["ok"] is False and any("duplicate" in p for p in PACK.verify(dup)["problems"])


def test_a_skill_with_a_relative_link_to_a_missing_file_fails_the_pack_and_a_symlink_refuses_the_build(proj, tmp_path):
    sk = proj / ".agents" / "skills" / "linky"
    (sk / "references").mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: linky\ndescription: d\n---\nSee [ref](references/a.md).\n")
    (sk / "references" / "a.md").write_text("ref")
    MIR.sync(proj)
    z = tmp_path / "p.zip"
    assert PACK.build(proj, z)["ok"] and PACK.verify(z)["ok"]
    (sk / "references" / "a.md").unlink()
    MIR.sync(proj)
    bad = tmp_path / "bad.zip"
    PACK.build(proj, bad, check_links=False)
    v = PACK.verify(bad)
    assert v["ok"] is False and any("references/a.md" in p for p in v["problems"])
    os.symlink(proj / "AGENTS.md", sk / "link.md")
    with pytest.raises(PACK.PackError, match="real files"):
        PACK.build(proj, tmp_path / "s.zip")


def test_note_write_refuses_a_stale_revision_keeps_the_draft_and_backs_up_the_previous_bytes(proj, tmp_path):
    state = tmp_path / "state"
    r1 = NOTES.write(proj, "knowledge/method.md", "first", None, state)
    assert r1["created"] is True
    rev = r1["revision"]
    r2 = NOTES.write(proj, "knowledge/method.md", "second", rev, state)
    assert (proj / "knowledge" / "method.md").read_text() == "second" and r2["revision"] != rev
    backups = list((state / "note-backups").glob("*.md"))
    assert len(backups) == 1 and backups[0].read_text() == "first" and json.loads(backups[0].with_suffix(".json").read_text())["revision"] == rev
    with pytest.raises(NOTES.Stale, match="this file changed on disk; your draft is kept; read it again"):
        NOTES.write(proj, "knowledge/method.md", "third", rev, state)
    assert (proj / "knowledge" / "method.md").read_text() == "second"
    for bad in ("../x.md", "other/x.md", "knowledge/../../x.md", "/etc/x.md"):
        with pytest.raises(NOTES.NoteRefused):
            NOTES.write(proj, bad, "t", None, state)
    with pytest.raises(NOTES.NoteRefused, match="2 MB"):
        NOTES.write(proj, "knowledge/big.md", "a" * (2 * 1024 * 1024 + 1), None, state)


def test_two_concurrent_writers_do_not_lose_a_write(proj, tmp_path):
    state = tmp_path / "state"
    rev = NOTES.write(proj, "notes_a", "x", None, state) if False else NOTES.write(proj, "knowledge/shared.md", "base", None, state)["revision"]
    results = []
    def go(text):
        try:
            results.append(("ok", NOTES.write(proj, "knowledge/shared.md", text, rev, state)["revision"]))
        except NOTES.Stale:
            results.append(("stale", None))
    ts = [threading.Thread(target=go, args=(f"writer-{i}",)) for i in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert [r[0] for r in results].count("ok") == 1 and [r[0] for r in results].count("stale") == 5
    assert (proj / "knowledge" / "shared.md").read_text().startswith("writer-")


def test_mcp_instructions_are_under_2kb_and_name_agents_md():
    text = GEN.mcp_instructions()
    assert len(text.encode()) <= 2048 and "Project instructions: AGENTS.md in the project root" in text and "plan, never confirm" in text.lower()


def test_status_reports_missing_stale_ok_and_user_owned(proj):
    assert {r["path"]: r["state"] for r in SCAF.status(proj, rows=registry_rows())}["AGENTS.md"] == "missing"
    SCAF.scaffold(proj)
    GEN.generate(proj, rows=registry_rows())
    st = {r["path"]: r["state"] for r in SCAF.status(proj, rows=registry_rows())}
    assert st["AGENTS.md"] == "ok" and st[".agents/skills/lampway-laws/SKILL.md"] == "ok"
    (proj / "AGENTS.md").write_text("no marker any more\n")
    assert {r["path"]: r["state"] for r in SCAF.status(proj, rows=registry_rows())}["AGENTS.md"] == "differs-user-owned"


def test_generate_never_regenerates_over_a_file_the_user_took_over(proj):
    GEN.generate(proj, rows=registry_rows())
    (proj / "AGENTS.md").write_text("MINE: the marker is gone\n")
    out = GEN.generate(proj, rows=registry_rows())
    assert (proj / "AGENTS.md").read_text() == "MINE: the marker is gone\n" and "AGENTS.md" in out["skipped_user_owned"]
    forced = GEN.generate(proj, rows=registry_rows(), overwrite=True)
    assert "AGENTS.md" in forced["written"] and (proj / "AGENTS.md").read_text().startswith("<!-- generated by lampway_agent_files")


def test_mcp_guide_first_step_is_selected_from_offered_registry(monkeypatch):
    import re
    from types import SimpleNamespace
    from lampway_server import mcp
    monkeypatch.setattr(mcp, 'offered_tools', lambda: [SimpleNamespace(name='lampway_inspect')])
    text = GEN.mcp_instructions()
    assert text.splitlines()[1] == 'First call lampway_inspect with no arguments to inspect the scene.'
    assert set(re.findall(r'[a-z]+(?:_[a-z0-9]+)+', text)) == {'lampway_inspect'}
    monkeypatch.setattr(mcp, 'offered_tools', lambda: [SimpleNamespace(name='scene_summary')])
    text = GEN.mcp_instructions()
    assert 'First call scene_summary' in text and 'lampway_inspect' not in text


def test_launcher_fallback_is_generated_from_current_instructions():
    target = GEN.REPO / "src/scripts/mixar/modules/mcp_bridge/core/generated_guide.py"
    assert target.read_text() == GEN.mcp_fallback_source()
    import ast
    guide = ast.literal_eval(ast.parse(target.read_text()).body[0].value)
    import re
    from lampway_server.mcp import offered_tools
    names = {tool.name for tool in offered_tools()} | GEN.mcp_local_tool_names()
    assert set(re.findall(r"[a-z]+(?:_[a-z0-9]+)+", guide)) <= names


def test_runtime_mcp_instructions_need_no_client_checkout(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from lampway_server import mcp
    monkeypatch.setattr(GEN, "REPO", tmp_path)
    monkeypatch.setattr(mcp, "offered_tools", lambda: [SimpleNamespace(name="lampway_inspect")])
    text = GEN.mcp_instructions()
    assert "First call lampway_inspect" in text
    assert "lampway_scene_new" not in text
