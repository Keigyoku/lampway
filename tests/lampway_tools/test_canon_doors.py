# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The normalization door's CI checks (specs/canon/normalization DOOR.md section 5, contract canon_door.md), standalone (no bpy).

Closed by construction, not by a list: each check derives its subject from the code itself (the AST of every module, the
decorator, the registries). The only hand-kept number is the LEGACY ratchet, which may only fall."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LT = ROOT / "src/scripts/mixar/modules/lampway_tools"
SRV = ROOT / "server/lampway_server"
CANON_IO = LT / "canon_io.py"
OP_NAME = re.compile(r"^(import_\w+\.\w+|wm\.\w+_import)$")                   # an importer named in a string, called dynamically
IMPORTER = re.compile(r"^bpy\.ops\.import_\w+\.\w+$|^bpy\.ops\.wm\.\w+_import$|^bpy\.data\.libraries\.load$|^bpy\.data\.images\.load$")


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _modules():
    for p in sorted(LT.rglob("*.py")):
        yield p
    for p in sorted(SRV.rglob("*.py")):
        if "bpy" in p.read_text(encoding="utf-8", errors="replace"):
            yield p


def _foreign(tree):
    """A module that runs in a FOREIGN Blender (a rented box's PyPI bpy, where canon_io is not shipped) says so at module level:
    CANON_FOREIGN_BLENDER = "<why>" (a non-empty reason). Its imports never land in a Lampway scene."""
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CANON_FOREIGN_BLENDER" for t in n.targets):
            return isinstance(n.value, ast.Constant) and isinstance(n.value.value, str) and len(n.value.value.strip()) >= 20
    return False


def importer_calls():
    out = []
    for p in _modules():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if _foreign(tree):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute):                                       # any mention, called or not: (a if b else c)(...) too
                name = _dotted(n)
                if name and IMPORTER.match(name):
                    out.append((p, n.lineno, name))
            elif isinstance(n, ast.Call):
                name = _dotted(n.func)
                if name == "getattr" and n.args and (_dotted(n.args[0]) or "").startswith("bpy.ops"):
                    out.append((p, n.lineno, f"getattr({_dotted(n.args[0])}, ...) (a dynamic operator: an importer cannot hide behind it)"))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and OP_NAME.match(n.value):
                out.append((p, n.lineno, f"operator name {n.value!r}"))
    return out


def test_one_importer_only_canon_io_calls_blenders_importers():
    stray = [f"{p.relative_to(ROOT)}:{line} {name}" for p, line, name in importer_calls() if p != CANON_IO]
    assert not stray, "importer calls outside canon_io (route them through canon_io.import_raw / load_image):\n" + "\n".join(stray)


# ------------------------------------------------------------------ N2: every tool declares what it consumes
def _decorated_tools():
    """(path, line, function, decorator node) for every function decorated with `tool` / `api.tool` / `tool(...)`."""
    out = []
    for p in sorted(LT.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for f in ast.walk(tree):
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in f.decorator_list:
                    target = d.func if isinstance(d, ast.Call) else d
                    if (_dotted(target) or "").split(".")[-1] == "tool":
                        out.append((p, f.lineno, f.name, d))
    return out


def test_every_tool_declares_what_it_consumes():
    tools = _decorated_tools()
    assert len(tools) >= 80, f"the scan found only {len(tools)} tools: it is not looking where the tools are"
    bare = [f"{p.relative_to(ROOT)}:{line} {name}" for p, line, name, d in tools
            if not (isinstance(d, ast.Call) and any(k.arg == "consumes" for k in d.keywords))]
    assert not bare, "tools without consumes= (declare Need(...), NONE('why') or, during migration, LEGACY('issue')):\n" + "\n".join(bare)


def _in_blender(body):
    import sys as _s
    _s.path.insert(0, str(Path(__file__).parent))
    from blender_run import run_script
    r = run_script("import bpy, json\nfrom mixar.modules.lampway_tools import api\n" + body, timeout=120)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_a_tool_without_consumes_cannot_be_registered():
    d = _in_blender("""
out = {}
for name, f in (("bare", lambda: api.tool(lambda: {})), ("empty", lambda: api.tool()(lambda: {})), ("none_why", lambda: api.tool(consumes=api.NONE(""))(lambda: {})),
                ("dict_not_need", lambda: api.tool(consumes={"object": "mesh"})(lambda: {}))):
    try:
        f(); out[name] = None
    except TypeError as e:
        out[name] = str(e)
print("RESULT", json.dumps(out))
""")
    assert d["bare"] and "consumes" in d["bare"] and d["empty"] and "consumes" in d["empty"]
    assert d["none_why"] and "why" in d["none_why"] and d["dict_not_need"] and "consumes" in d["dict_not_need"]


def test_the_doors_are_derived_from_the_same_decorator_as_the_functions():
    d = _in_blender("""print("RESULT", json.dumps({"doors": sorted(api.TOOL_DOORS), "funcs": sorted(api.TOOL_FUNCS)}))""")
    assert d["doors"] and set(d["doors"]) == set(d["funcs"])


def test_runner_tools_declare_too():
    from mixar.modules.lampway_tools import canon_door as CD
    from mixar.modules.lampway_tools import runner
    with pytest.raises(TypeError):
        runner.Tool("x", "blender", "x.py", "summary")
    assert all(isinstance(t.consumes, (CD.Declared, dict)) for t in runner.TOOLS.values())


RATCHET = LT / "canon_legacy_count.txt"


def _legacy_calls():
    n = 0
    for p in sorted(LT.rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        n += sum(1 for c in ast.walk(tree) if isinstance(c, ast.Call) and (_dotted(c.func) or "").split(".")[-1] == "LEGACY")
    return n


def test_the_legacy_ratchet_matches_the_code_and_only_falls():
    import sys as _s
    _s.path.insert(0, str(Path(__file__).parent))
    from canon_ratchet import violations
    text = RATCHET.read_text()
    want = int(text.split()[0])
    assert _legacy_calls() == want, f"LEGACY( calls: {_legacy_calls()}, the ratchet file says {want}: lower the file when you migrate a tool (never raise it)"
    bad = violations(ROOT, str(RATCHET.relative_to(ROOT)), worktree_text=text)
    assert not bad, "\n".join(bad)


def test_the_door_refuses_raw_unstamped_and_changed_assets_and_opens_for_a_canonical_one():
    d = _in_blender("""
import bmesh, copy
from mixar.modules.lampway_tools import canon_asset as CA, canon_io
probe = api.tool(consumes={"object": api.Need(kind=("mesh",), scale=CA.ANY_SCALE)})(lambda object: {"ran": object})
def cube(name):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob
raw = cube("raw"); raw["lw_raw"] = json.dumps({"sha256": "0" * 64})
plain = cube("plain")
good = cube("good")
ex = json.load(open(EXAMPLES))["valid"][0]["doc"]
doc = copy.deepcopy(ex); f = canon_io.facts(good)
doc["body"]["bbox_min_m"], doc["body"]["bbox_max_m"], doc["body"]["geometry_sha256"] = f["bbox_min_m"], f["bbox_max_m"], f["geometry_sha256"]
good["lw_canon"] = json.dumps(doc)
out = {"raw": probe(object="raw"), "plain": probe(object="plain"), "good": probe(object="good")}
good.data.vertices[0].co.x += 0.1; good.data.update()
out["changed"] = probe(object="good")
print("RESULT", json.dumps(out))
""".replace("EXAMPLES", repr(str(Path(__file__).parent / "canon_goldens/normalization/canonical-asset.examples.json"))))
    assert d["good"] == {"ok": True, "ran": "good"}, d["good"]
    for k, word in (("raw", "RAW"), ("plain", "no canonical stamp"), ("changed", "changed since it was normalized")):
        assert d[k]["ok"] is False and d[k]["error"].startswith("normalize first") and word in d[k]["error"], (k, d[k])
        assert d[k]["help"][0].startswith("lampway_normalize_mesh"), d[k]


def test_red_team_every_door_that_names_a_kind_refuses_a_raw_asset():
    d = _in_blender("""
from mixar.modules.lampway_tools import canon_door as CD
import bmesh
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); me = bpy.data.meshes.new("raw_rt"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("raw_rt", me); bpy.context.scene.collection.objects.link(ob); ob["lw_raw"] = json.dumps({"sha256": "0" * 64})
rows = []
for name, (consumes, _p) in sorted(api.TOOL_DOORS.items()):
    if isinstance(consumes, dict):
        for arg, need in consumes.items():
            if need.accept_raw or "mesh" not in need.kind:
                continue
            r = getattr(api, name)(**{arg: "raw_rt"})
            rows.append({"tool": name, "arg": arg, "refused": (not r.get("ok")) and str(r.get("error", "")).startswith("normalize first")})
print("RESULT", json.dumps({"rows": rows, "legacy": sum(1 for c, _p in api.TOOL_DOORS.values() if isinstance(c, CD.LEGACY))}))
""")
    assert all(r["refused"] for r in d["rows"]), [r for r in d["rows"] if not r["refused"]]
    assert d["rows"] or d["legacy"] > 0, "no door names a kind and none is LEGACY: the check would be empty for no reason"


# ------------------------------------------------------------------ the ratchet's recorded rebaseline (coordinator ruling A)
def _repo(tmp_path):
    import os
    r = tmp_path / "repo"
    r.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@users.noreply.github.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@users.noreply.github.com", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")

    def git(*a):
        out = subprocess.run(["git", *a], cwd=r, capture_output=True, text=True, env=env)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    def commit(text, msg):
        (r / "count.txt").write_text(text)
        git("add", "count.txt")
        git("commit", "-q", "-m", msg)
        return git("rev-parse", "HEAD")
    git("init", "-q", "-b", "main")
    return r, git, commit


import sys as _sys  # noqa: E402
_sys.path.insert(0, str(Path(__file__).parent))


def test_ratchet_a_plain_commit_that_raises_the_count_is_refused(tmp_path):
    from canon_ratchet import violations
    r, git, commit = _repo(tmp_path)
    commit("110\n", "baseline")
    commit("108\n", "two tools migrated")
    commit("140\n", "raised in a plain commit")
    assert any("108 -> 140" in v for v in violations(r, "count.txt")), violations(r, "count.txt")


def test_ratchet_a_plain_commit_cannot_borrow_a_rebaseline_record(tmp_path):
    from canon_ratchet import violations
    r, git, commit = _repo(tmp_path)
    commit("110\n", "baseline")
    side = commit("110\n# side\n", "x")
    commit(f"140\nrebaseline 140 merged={side} reason=a plain commit pretending to merge\n", "raised")
    assert violations(r, "count.txt")


def _merge(r, git, count, record):
    base = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "orphans", base + "~0")
    (r / "tool.py").write_text("LEGACY\n" * 30)
    git("add", "tool.py")
    git("commit", "-q", "-m", "pre-door tools")
    tip = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "--no-commit", "orphans")
    text = f"{count}\n" + (record.format(tip=tip) if record else "")
    (r / "count.txt").write_text(text)
    git("add", "count.txt")
    git("commit", "-q", "-m", "merge orphans")
    return tip


def test_ratchet_a_merge_commit_that_records_the_number_the_merged_sha_and_a_reason_is_accepted(tmp_path):
    from canon_ratchet import violations
    r, git, commit = _repo(tmp_path)
    commit("110\n", "baseline")
    rec = "rebaseline 140 merged={tip} reason=lane orphans: 30 tools written before the door\n"
    tip = _merge(r, git, 140, rec)
    assert violations(r, "count.txt") == []
    commit("139\n" + rec.format(tip=tip), "one tool migrated: the count falls again, the record stays")
    assert violations(r, "count.txt") == []
    commit("140\n" + rec.format(tip=tip), "a plain commit cannot re-use the merge's record to rise again")
    assert violations(r, "count.txt") == ["the ratchet rose 139 -> 140 in a plain commit (a rise is accepted only in a merge commit that records it)"]


@pytest.mark.parametrize("record", ["", "rebaseline 141 merged={tip} reason=wrong number\n", "rebaseline 140 merged=0000000 reason=not the merged sha\n",
                                    "rebaseline 140 merged={tip} reason=\n"])
def test_ratchet_a_merge_that_raises_without_a_whole_record_is_refused(tmp_path, record):
    from canon_ratchet import violations
    r, git, commit = _repo(tmp_path)
    commit("110\n", "baseline")
    _merge(r, git, 140, record)
    assert violations(r, "count.txt"), record


def test_ratchet_in_the_working_tree_a_rise_needs_a_merge_in_progress_and_its_record(tmp_path):
    from canon_ratchet import violations
    r, git, commit = _repo(tmp_path)
    commit("110\n", "baseline")
    assert violations(r, "count.txt", worktree_text="140\n")                                   # no merge in progress
    git("checkout", "-q", "-b", "orphans")
    (r / "tool.py").write_text("x\n")
    git("add", "tool.py")
    git("commit", "-q", "-m", "pre-door tools")
    tip = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    commit("109\n", "a tool migrated on main")
    git("merge", "-q", "--no-ff", "--no-commit", "orphans")
    assert violations(r, "count.txt", worktree_text="140\n")                                   # merging, but no record
    assert violations(r, "count.txt", worktree_text=f"140\nrebaseline 140 merged={tip} reason=lane orphans\n") == []


def test_the_door_checks_each_element_of_a_list_and_names_the_index_of_the_first_bad_one():
    """coordinator ruling C: a tool taking a LIST of objects passes its door only when every element does; the refusal names the
    index of the first element that fails, and its help normalizes that element."""
    d = _in_blender("""
import bmesh, copy
from mixar.modules.lampway_tools import canon_asset as CA, canon_io
probe = api.tool(consumes={"objects": api.Need(kind=("mesh",), scale=CA.ANY_SCALE)})(lambda objects: {"ran": list(objects)})
ex = json.load(open(EXAMPLES))["valid"][0]["doc"]
def cube(name, canon):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    if canon:
        doc = copy.deepcopy(ex); f = canon_io.facts(ob)
        doc["body"]["bbox_min_m"], doc["body"]["bbox_max_m"], doc["body"]["geometry_sha256"] = f["bbox_min_m"], f["bbox_max_m"], f["geometry_sha256"]
        ob["lw_canon"] = json.dumps(doc)
    return ob
cube("g1", True); cube("g2", True); r = cube("rawp", False); r["lw_raw"] = json.dumps({"sha256": "0" * 64}); cube("plainp", False)
out = {"good": probe(objects=["g1", "g2"]), "tuple": probe(objects=("g1", "rawp")), "bad": probe(objects=["g1", "g2", "rawp", "plainp"]),
       "empty": probe(objects=[]), "one": probe(objects="plainp")}
print("RESULT", json.dumps(out))
""".replace("EXAMPLES", repr(str(Path(__file__).parent / "canon_goldens/normalization/canonical-asset.examples.json"))))
    assert d["good"] == {"ok": True, "ran": ["g1", "g2"]} and d["empty"] == {"ok": True, "ran": []}
    for k, i in (("tuple", 1), ("bad", 2)):
        e = d[k]
        assert e["ok"] is False and e["error"].startswith(f"normalize first: objects[{i}] 'rawp'") and "RAW" in e["error"], e
        assert "plainp" not in e["error"] and e["help"][0] == "lampway_normalize_mesh input=rawp", e
    assert d["one"]["ok"] is False and d["one"]["error"].startswith("normalize first: objects 'plainp'")
