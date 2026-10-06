"""egress_consent's coverage audit, by construction: EVERY process the server starts is accounted for.

The transport hook sees every httpx call; it cannot see a process (yt-dlp, a studio driver, a CLI, a cloud box CLI). So each process launch in the server package must be
  (a) lexically inside a ``with ...guard(route)`` block, or
  (b) listed in ``egress.LAUNCHES`` as ``local`` (the program it starts sends nothing of ours off the machine) with the reason, or
  (c) listed as ``callers_guard``: a launch helper whose every call in its module is itself inside ``guard`` (or in another ``callers_guard`` helper).
A new launch that is none of these fails here, so a bypass cannot be added silently (video ingest from a pasted link was one: it ran yt-dlp with no gate)."""
import ast
from pathlib import Path

from lampway_server import egress as EG

ROOT = Path(__file__).resolve().parents[1] / "lampway_server"
LAUNCH_ATTRS = {("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "check_output"), ("subprocess", "check_call"), ("subprocess", "call"),
                ("asyncio", "create_subprocess_exec"), ("asyncio", "create_subprocess_shell"), ("os", "system"), ("os", "popen")}


def _is_launch(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        if (f.value.id, f.attr) in LAUNCH_ATTRS:
            return True
        if f.value.id == "os" and (f.attr.startswith("exec") or f.attr.startswith("spawn")):
            return True
    return False


def _is_guard_with(node) -> bool:
    if not isinstance(node, (ast.With, ast.AsyncWith)):
        return False
    for item in node.items:
        c = item.context_expr
        if isinstance(c, ast.Call):
            f = c.func
            if (isinstance(f, ast.Attribute) and f.attr == "guard") or (isinstance(f, ast.Name) and f.id == "guard"):
                return True
    return False


def _walk(tree):
    """(call node, enclosing function qualname, inside a guard block) for every Call in the module."""
    out = []

    def visit(node, qual, guarded):
        for child in ast.iter_child_nodes(node):
            q, g = qual, guarded
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{qual}.{child.name}" if qual else child.name
                g = False
            elif isinstance(child, ast.ClassDef):
                q = f"{qual}.{child.name}" if qual else child.name
            elif _is_guard_with(child):
                g = True
            if isinstance(child, ast.Call):
                out.append((child, q, guarded or g))
            visit(child, q, g)
    visit(tree, "", False)
    return out


def _sites(root=ROOT):
    sites = []
    for p in sorted(root.rglob("*.py")):
        rel = str(p.relative_to(root))
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for call, qual, guarded in _walk(tree):
            if _is_launch(call):
                sites.append((rel, qual, call.lineno, guarded, tree))
    return sites


def test_every_process_launch_is_gated_or_declared():
    bad = []
    for rel, qual, line, guarded, _ in _sites():
        key = f"{rel}:{qual}"
        if guarded or key in EG.LAUNCHES:
            continue
        bad.append(f"{key} (line {line})")
    assert not bad, "process launches the egress gate cannot see (wrap them in egress.guard(route), or declare them in egress.LAUNCHES with the reason):\n  " + "\n  ".join(bad)


def test_every_declaration_has_a_kind_and_a_reason_and_names_a_real_launch():
    real = {f"{rel}:{qual}" for rel, qual, *_ in _sites()}
    for key, (kind, reason) in EG.LAUNCHES.items():
        assert kind in ("local", "callers_guard", "wrapped", "driver"), key
        if kind == "driver":
            assert key.startswith("studios/"), f"{key}: only a studio driver script runs inside a gated driver process"
        assert len(reason) > 20, f"{key}: say why"
        assert key in real, f"{key} is declared but launches nothing: remove the stale entry"


def test_a_callers_guard_helper_is_only_ever_called_inside_a_guard():
    bad = []
    helpers = {k: v for k, v in EG.LAUNCHES.items() if v[0] == "callers_guard"}
    for key in helpers:
        rel, qual = key.split(":", 1)
        name = qual.rsplit(".", 1)[-1]
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for call, caller, guarded in _walk(tree):
            f = call.func
            called = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if called != name or caller == qual:
                continue
            if guarded or EG.LAUNCHES.get(f"{rel}:{caller}", ("",))[0] == "callers_guard":
                continue
            bad.append(f"{rel}:{caller} calls {name} (line {call.lineno}) outside a guard")
        refs = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)]
        calls = [c.func for c, *_ in _walk(tree) if isinstance(c.func, ast.Name) and c.func.id == name]
        assert len(refs) == len(calls), f"{key} is passed around as a value: a caller could launch it without the gate"
    assert not bad, "\n".join(bad)


def test_the_audit_sees_a_planted_bypass(tmp_path):
    """The instrument is not blind: an unguarded yt-dlp launch is reported, and the same launch inside guard is not."""
    (tmp_path / "bad.py").write_text("import subprocess\n\ndef fetch(url):\n    return subprocess.run(['yt-dlp', url])\n")
    (tmp_path / "good.py").write_text("import subprocess\nfrom lampway_server import egress as EG\n\ndef fetch(url):\n    with EG.guard('video_link'):\n        return subprocess.run(['yt-dlp', url])\n")
    got = {(rel, qual): guarded for rel, qual, _, guarded, _ in _sites(tmp_path)}
    assert got == {("bad.py", "fetch"): False, ("good.py", "fetch"): True}


def test_a_wrapped_launcher_is_only_used_through_its_guarded_wrapper():
    for key, (kind, _) in EG.LAUNCHES.items():
        if kind != "wrapped":
            continue
        rel, qual = key.split(":", 1)
        name = qual.rsplit(".", 1)[-1]
        wrapper, attr = EG.WRAPPERS[key]
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        calls = _walk(tree)
        assert any(q == wrapper and g for _, q, g in calls), f"{wrapper} holds no guard"
        for node in ast.walk(tree):                                           # the launcher itself is never called directly
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
                raise AssertionError(f"{key} is called directly (line {node.lineno}): go through {wrapper}")
        for call, q, guarded in calls:                                        # the injected attribute is called only inside the guarded wrapper, or handed to it
            f = call.func
            if isinstance(f, ast.Attribute) and f.attr == attr and isinstance(f.value, ast.Name) and f.value.id == "self":
                assert q == wrapper and guarded, f"{rel}:{q} calls self.{attr} outside {wrapper}'s guard (line {call.lineno})"
            if any(isinstance(a, ast.Attribute) and a.attr == attr for a in call.args):
                fn = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
                assert fn in (wrapper.rsplit(".", 1)[-1], "to_thread"), f"{rel}:{q} hands self.{attr} to {fn} (line {call.lineno})"
                if fn == "to_thread":
                    assert isinstance(call.args[0], ast.Name) and call.args[0].id == wrapper.rsplit(".", 1)[-1], f"{rel}:{q} runs self.{attr} in a thread without {wrapper}"


# ---- behaviour behind the audit: the launches it made gated refuse with the route off, and log before they start with it on
import pytest  # noqa: E402


@pytest.fixture
def strict(tmp_path):
    m = EG.Egress(tmp_path / "state")
    EG.install()
    prev = EG.ACTIVE
    EG.set_active(m)
    yield m
    EG.set_active(prev)


def test_every_boat_cli_call_is_gated_not_only_provision_upload_and_run(strict):
    from lampway_server.compute.boat import BoatCliBackend
    calls = []
    be = BoatCliBackend(binary="/nonexistent/boat", runner=lambda argv, timeout: (calls.append(argv), (0, '{"status": "running"}', ""))[1])
    with pytest.raises(EG.EgressRefused, match="compute:boat is off"):
        be._cli("status", "box-1")
    assert calls == []
    strict.set_route("compute:boat", True)
    with EG.context(asset_ids=["abc123"], content_class="private"):        # the runner declares; the backend's guard inherits it
        be._cli("status", "box-1")
    row = [r for r in strict.log() if r.get("route") == "compute:boat" and r.get("event") not in ("route", "refused")][-1]
    assert calls and row["asset_ids"] == ["abc123"] and row["content_class"] == "private"


def test_a_tripo_driver_tool_is_refused_with_its_route_off_and_never_starts(strict, monkeypatch):
    from lampway_server.agent import server_tools as ST
    started = []
    monkeypatch.setattr(ST.subprocess, "run", lambda *a, **k: (started.append(a), type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})())[1])
    text, is_error = ST.run("studio_tripo_state", {})
    assert is_error and "studio:tripo is off" in text and started == []
    text, is_error = ST.run("studio_seed_catalog", {})                      # the local catalog read is not a route
    assert started and "is off" not in text
