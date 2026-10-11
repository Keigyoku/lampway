#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""THE full test run of the repository: the server suite and the whole client suite (every pytest.ini testpath: tests/, tests/lampway,
tests/lampway_tools on the real binary, the module test folders), with failures attributed through ``tests/known_red.tsv``.

    scripts/lampway/test_all.sh                    # both suites, in parallel; exit 0 only with zero failures/errors and verified baseline reconciliation
    scripts/lampway/test_all.sh --only server      # one suite
    scripts/lampway/test_all.sh --shrink-baseline  # also drop baseline lines whose test now passes (the list never grows here)

Green means: no new or known failure/error, no unverified baseline entry, and no baseline entry with a recorded PASS left in the list.
The baseline attributes inherited failures; it never exempts them from RED.
Baseline shrinking requires affirmative exact pytest PASS node IDs; skipped or uncollected entries are never removed.
Environment: LAMPWAY_BIN (the real binary; without one the tool tests SKIP, which the summary counts), LAMPWAY_TEST_PYTHON (default: this
interpreter), TMPDIR (the run's temp root), LAMPWAY_TEST_OUT (logs; default $TMPDIR/lampway-test-all)."""
import argparse
import ast
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests" / "known_red.tsv"
ID = re.compile(r"^(FAILED|ERROR) (.+)")
COUNT = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
WARNING = re.compile(r"⚠\s+\[WARNING\]")


def node_identity(text: str, failure_reason=False) -> str:
    """Keep parameter delimiters inside balanced brackets; reject uncertain syntax as PASS evidence."""
    depth = 0
    for i, char in enumerate(text):
        if depth == 0 and WARNING.match(text, i):
            return text[:i].strip()
        if failure_reason and depth == 0 and text.startswith(" - ", i):
            return text[:i].strip()
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                return ""
    return text.strip() if depth == 0 else ""


def load_baseline(path=BASELINE) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            tid, cls, reason = (line.split("\t") + ["", ""])[:3]
            out[tid] = (cls, reason)
    return out


def parse(log: str, prefix: str = "") -> tuple:
    log = ANSI.sub("", log)
    ids, counts = set(), {}
    for line in log.splitlines():
        m = ID.match(line)
        if m:
            node = node_identity(m.group(2), failure_reason=True) or m.group(2).strip()
            if "::" in node or node.endswith(".py"):
                ids.add(prefix + node)
    tail = [l for l in log.splitlines() if re.search(r"\d+ (passed|failed)", l) and " in " in l]
    if tail:
        for n, what in COUNT.findall(tail[-1]):
            counts[what.rstrip("s") if what.startswith("error") else what] = int(n)
    env = [l for l in log.splitlines() if l.startswith("ENV-SKIPPED ")]
    counts["env_skipped"] = int(env[-1].split()[1].rstrip(":")) if env else 0
    return ids, counts


NATIVE_PATHS = ("src/source", "src/intern", "src/CMakeLists.txt", "src/build_files", "src/release/datafiles", "native", "cmake", "upstream")


def binary_gate(root, binary) -> tuple:
    """("gated", sha) when <Prod>/BUILT_FROM names a commit whose native sources equal HEAD's; ("refused", why) when they differ;
    ("ungated", why) when the binary records no BUILT_FROM (or there is none). A gated client run tests exactly the batch's native code."""
    if not binary:
        return "ungated", "UNGATED binary: no LAMPWAY_BIN, the real-binary tool tests skip"
    built = Path(binary).resolve().parent.parent / "BUILT_FROM"
    if not built.is_file():
        return "ungated", f"UNGATED binary: {built} is absent, so the binary's native sources are unknown"
    stamp = built.read_text().strip()
    if stamp.startswith("UNCLEAN "):           # build_linux.sh's mark for a tree that was not the commit (built_from.sh)
        return "refused", f"the binary was built from an unclean tree: {stamp[:400]}"
    words = stamp.split()
    sha = words[1] if words[:1] == ["UNPUSHED"] and len(words) > 1 else words[0]
    paths = [p for p in NATIVE_PATHS if (Path(root) / p).exists()]
    known = subprocess.run(["git", "-C", str(root), "cat-file", "-e", sha + "^{commit}"], capture_output=True)
    if known.returncode != 0:
        return "refused", f"the binary was built from {sha}, which this repository does not have: its native sources cannot be compared"
    diff = subprocess.run(["git", "-C", str(root), "diff", "--quiet", sha, "HEAD", "--", *paths], capture_output=True)
    if diff.returncode != 0:
        return "refused", f"the binary was built from {sha[:12]}, whose native sources differ from HEAD's ({', '.join(paths)}): build at this batch, or a sha with the same native sources"
    return "gated", sha


# The reference test environment (scripts/lampway/test_env.sh builds it): upstream/ at its pin, and these importable (module -> distribution).
I18N_TEMPLATE = "src/scripts/mixar/modules/common/i18n/locale/mixar.pot"      # git-ignored, generated by scripts/i18n/extract_messages.py
UPSTREAM_FILES = ("upstream/release/datafiles/userdef/userdef_default_theme.c", "upstream/scripts/presets/keyconfig/keymap_data/blender_default.py")
TEST_PACKAGES = {"pytest": "pytest", "pytest_timeout": "pytest-timeout", "numpy": "numpy", "PIL": "pillow", "requests": "requests", "jsonschema": "jsonschema",
                 "mcp": "mcp", "onnxruntime": "onnxruntime", "starlette": "starlette", "httpx": "httpx", "websocket": "websocket-client"}


# The shelf (the owner's recorded fixtures: the MetaHuman-sized body and self-test pieces) is part of the reference environment: the
# placement pins and original chest/plate/palette acceptances measure real recorded cases. Its location is the
# machine's, never the repository's: LAMPWAY_SHELF_DIR (and LAMPWAY_SHELF_SCRATCH when its scratch lives elsewhere). Read only: the run
# is refused as RED when it changed any file there.
SHELF_FILES = ("proportion/audit/body.npz", "proportion/piece_selftest/helmet.npz",
               "parts_transfer/r1/islands.json", "parts_transfer/r1/transfer.json", "parts_transfer/recipe_r7_with_dropped.json",
               "tripo_texture/palette_A_to_albedo.json", "relief_proj/p17_albedo_4k/v3_colour_atlas.png",
               *(f"relief_proj/p17_albedo_4k/mask_{kind}.png" for kind in ("gold", "plate", "red", "linen", "leather", "embroidery")),
               "tripo_img/chest_front_4k_g1/fidelity.json",
               *(f"tripo_img/chest_front_4k_g1/{i}.jpg" for i in (1, 2, 3, 4)))     # under the shelf's scratch: the pins' REAL condition


def suite_environment(env):
    """Do not let a launcher's private keyring choice replace tests' system-keyring contract."""
    clean = dict(env, LAMPWAY_TEST_ALL="1")
    if clean.get("LAMPWAY_SHELF_DIR") and not clean.get("LAMPWAY_SHELF_SCRATCH"):
        clean["LAMPWAY_SHELF_SCRATCH"] = str(shelf_scratch(clean))
    for key in ("PYTHON_KEYRING_BACKEND", "LAMPWAY_KEYRING_FILE"):
        clean.pop(key, None)
    return clean


def reference_fixtures(env):
    """Require explicit private original inputs; never discover them in the person's home."""
    plate = env.get("LAMPWAY_V3_PLATES_DIR")
    if not plate or not (Path(plate) / "Chest1/Front.png").is_file():
        return ["LAMPWAY_V3_PLATES_DIR must name the authentic approved V3 plates directory containing Chest1/Front.png; do not substitute synthetic plates"]
    scratch = shelf_scratch(env) if env.get("LAMPWAY_SHELF_DIR") else None
    if scratch and not any((scratch / "tripo_texture/pbrA").glob("pbrA_BaseColor_*.png")):
        return ["private shelf scratch lacks tripo_texture/pbrA/pbrA_BaseColor_*.png"]
    return []


def browser_startup_probe(root, browser, env):
    """Launch a blank page with maintained production flags and the sandbox enabled, in disposable private state."""
    try:
        tree = ast.parse((Path(root) / "server/lampway_server/motion/frames.py").read_text())
        flags = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "CHROME_FLAGS" for target in node.targets))
        if not isinstance(flags, list) or not all(isinstance(value, str) for value in flags) or "--no-sandbox" in flags:
            return "default-flags sandbox startup probe refused invalid production flags"
        with tempfile.TemporaryDirectory(prefix="lampway-browser-preflight-", dir=env.get("TMPDIR") or "/tmp") as directory:
            home = Path(directory)
            isolated = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
                        "XDG_DATA_HOME": str(home / ".local/share"), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "FONTCONFIG_PATH": "/etc/fonts"}
            proc = subprocess.Popen([browser, *flags, f"--user-data-dir={home / 'profile'}", "--dump-dom", "about:blank"],
                                    env=isolated, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, _stderr = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)  # only this probe's recorded, newly created process group
                proc.communicate()
                return "default-flags sandbox startup probe failed: browser timed out; qualify the isolated host environment without disabling its sandbox"
            if proc.returncode or b"<html" not in stdout.lower():
                return "default-flags sandbox startup probe failed: browser could not render a blank page; qualify its sandbox and runtime libraries without disabling the sandbox"
    except (OSError, ValueError, StopIteration, SyntaxError):
        return "default-flags sandbox startup probe failed: production flags or isolated runtime unavailable"
    return None


def reference_tools(root, env):
    """Complete-suite admission: qualified shell and actual authored SVG rendering, not tool names alone."""
    problems = []
    browser = env.get("LAMPWAY_CHROMIUM", "")
    if not browser or Path(browser).resolve().name != "chrome-headless-shell" or not os.access(browser, os.X_OK):
        problems.append("LAMPWAY_CHROMIUM must name an executable chrome-headless-shell; full Chrome's bundled service workers are unsupported; scene-worker containment remains enforced")
    else:
        try:
            result = subprocess.run([browser, "--version"], capture_output=True, timeout=15)
            if result.returncode or not result.stdout.strip():
                problems.append("chrome-headless-shell --version failed")
            elif (failure := browser_startup_probe(root, browser, env)):
                problems.append(failure)
        except (OSError, subprocess.TimeoutExpired):
            problems.append("chrome-headless-shell --version failed")
    if not shutil.which("magick") or not shutil.which("fc-match"):
        problems.append("actual SVG rendering requires ImageMagick magick with a working SVG delegate, plus fontconfig fc-match")
    else:
        # The maintained generator uses both its real SVG delegate and vendored FreeType faces.
        # Probe the actual splash, whose failure was hidden by an executable-only prerequisite.
        art = Path(root) / "scripts/dev/lampway_placeholder_art.py"
        if not art.is_file():
            problems.append("actual SVG rendering probe is unavailable: maintained brand generator is missing")
        else:
            code = "import importlib.util,sys; s=importlib.util.spec_from_file_location('art',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.render_splash().size == (1672,941)"
            try:
                result = subprocess.run([env.get("LAMPWAY_TEST_PYTHON") or sys.executable, "-c", code, str(art)],
                                        capture_output=True, timeout=60, env=dict(env))
                if result.returncode:
                    problems.append("actual authored SVG splash rendering failed: verify ImageMagick's SVG delegate (rsvg-convert on PATH) and vendored font support")
            except (OSError, subprocess.TimeoutExpired):
                problems.append("actual authored SVG splash rendering failed or timed out")
    return problems


def shelf_scratch(shelf) -> Path:
    return Path(shelf.get("LAMPWAY_SHELF_SCRATCH") or Path(shelf["LAMPWAY_SHELF_DIR"]) / "scratch")


def shelf_snapshot(shelf) -> dict:
    """Snapshot shelf, external scratch and explicitly supplied original V3 inputs; names are root-qualified."""
    roots = [Path(shelf["LAMPWAY_SHELF_DIR"])]
    if shelf.get("LAMPWAY_V3_PLATES_DIR"):
        roots.append(Path(shelf["LAMPWAY_V3_PLATES_DIR"]))
    scr = shelf_scratch(shelf)
    if not str(scr.resolve()).startswith(str(roots[0].resolve()) + os.sep):
        roots.append(scr)
    out = {}
    for i, r in enumerate(roots):
        for d, _dirs, files in os.walk(r):
            for f in files:
                p = Path(d) / f
                try:
                    st = p.lstat()
                except OSError:
                    continue
                out[(f"root{i}@" if i else "") + p.relative_to(r).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def shelf_writes(before, after) -> list:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def verify_env(root, packages=None, python=None, shelf=None) -> list:
    """What the test environment lacks (empty = ready). ``python`` checks another interpreter's imports; None checks this one. ``shelf``
    is the environment holding LAMPWAY_SHELF_DIR / LAMPWAY_SHELF_SCRATCH (None: this process's)."""
    problems = [f"{rel} is missing (upstream/ not checked out at its pin)" for rel in UPSTREAM_FILES if not (Path(root) / rel).is_file()]
    if not (Path(root) / I18N_TEMPLATE).is_file():       # git-ignored: a fresh worktree has none, and tests/i18n then fails or skips
        problems.append(f"{I18N_TEMPLATE} is missing: test_env.sh writes it (scripts/i18n/extract_messages.py, after upstream/)")
    shelf = os.environ if shelf is None else shelf
    problems += reference_fixtures(shelf) + reference_tools(root, dict(shelf, LAMPWAY_TEST_PYTHON=python or sys.executable))
    if not shelf.get("LAMPWAY_SHELF_DIR"):
        problems.append("LAMPWAY_SHELF_DIR is not set: the shelf (read only) is part of the reference environment (the placement pins)")
    elif not Path(shelf["LAMPWAY_SHELF_DIR"]).is_dir():
        problems.append(f"LAMPWAY_SHELF_DIR={shelf['LAMPWAY_SHELF_DIR']} is not a directory")
    else:
        problems += [f"the shelf lacks {rel} under its scratch {shelf_scratch(shelf)} (set LAMPWAY_SHELF_SCRATCH if it lives elsewhere)"
                     for rel in SHELF_FILES if not (shelf_scratch(shelf) / rel).is_file()]
    packages = TEST_PACKAGES if packages is None else packages
    code = "import importlib, sys\nbad = []\nfor m in sys.argv[1:]:\n    try:\n        importlib.import_module(m)\n    except Exception:\n        bad.append(m)\nprint(' '.join(bad))\n"
    if python:
        result = subprocess.run([python, "-c", code, *packages], capture_output=True, text=True)
        missing = result.stdout.split() if result.returncode == 0 else list(packages)
        if result.returncode:
            problems.append("test interpreter package import probe failed")
    else:
        import importlib
        missing = []
        for m in packages:
            try:
                importlib.import_module(m)
            except Exception:  # noqa: BLE001
                missing.append(m)
    if "mcp" in packages and "mcp" not in missing and python:
        if subprocess.run([python, "-c", "from mcp import Client"], capture_output=True).returncode:
            missing.append("mcp")
    problems += [f"python package {packages[m]} does not import" for m in missing]
    return problems


def parse_passed(log: str, prefix: str = "") -> set:
    """Read affirmative pytest -rA PASS receipts, preserving class and parameter node IDs."""
    log = ANSI.sub("", log)
    return {prefix + node for line in log.splitlines() if line.startswith("PASSED ") and "::" in line
            if (node := node_identity(line[len("PASSED "):]))}


def judge(failing: set, baseline: dict, passing=None) -> dict:
    passing = set(passing or ()) - failing  # a later failure always beats an earlier PASS (e.g. teardown)
    known = set(baseline)
    return {"new": sorted(failing - known), "fixed": sorted(known & passing), "known": sorted(failing & known),
            "unverified": sorted(known - failing - passing)}


def head_sha(root) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=("server", "client"))
    ap.add_argument("--shrink-baseline", action="store_true")
    ap.add_argument("--verify-env", action="store_true", help="only check the test environment (test_env.sh calls this)")
    ap.add_argument("--ungated", action="store_true", help="run on a binary whose native sources differ from HEAD (the result is not a gate)")
    a = ap.parse_args(argv)
    py = os.environ.get("LAMPWAY_TEST_PYTHON") or sys.executable
    problems = verify_env(ROOT, python=py)
    if problems or a.verify_env:
        for p in problems:
            print("env: " + p, file=sys.stderr)
        if problems:
            print("the test environment is not the reference one: run scripts/lampway/test_env.sh", file=sys.stderr)
            return 6
        print("env: ready (upstream at its pin; every test package imports; private shelf/V3 fixtures present; qualified headless shell and actual SVG rendering checked)")
        return 0
    # inside the reference environment an environment skip would be a defect, so the suites' conftest does not skip; the flag goes to
    # the suites only, never into this process (called in-process by a test, it leaked into every later test)
    suite_env = suite_environment(os.environ)
    tmp = Path(os.environ.get("TMPDIR") or "/tmp").resolve()
    out = Path(os.environ.get("LAMPWAY_TEST_OUT") or tmp / "lampway-test-all")
    out.mkdir(parents=True, exist_ok=True)
    # the server's pyproject already adds -q (a second -q hides the summary line the counts are read from)
    suites = {"server": ([py, "-m", "pytest", "tests", "-rA", "-p", "no:cacheprovider", "-W", "ignore", "--tb=short", "--basetemp", str(tmp / "lw-test-server")], ROOT / "server", "server/"),
              "client": ([py, "-m", "pytest", "-rA", "-p", "no:cacheprovider", "--continue-on-collection-errors", "-q", "-W", "ignore", "--tb=short", "--basetemp", str(tmp / "lw-test-client")], ROOT, "")}
    run = {k: v for k, v in suites.items() if not a.only or k == a.only}
    gate = binary_gate(ROOT, os.environ.get("LAMPWAY_BIN")) if "client" in run else ("n/a", "server only")
    if gate[0] == "refused" and not a.ungated:
        print("REFUSED: " + gate[1] + " (pass --ungated to run anyway; the run is then not a gate)", file=sys.stderr)
        return 4
    if gate[0] != "gated" and "client" in run:
        print(gate[1], file=sys.stderr)
    import fcntl
    lock = open(tmp / "lw-test-all.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)      # two runs on one TMPDIR share basetemps and corrupt each other (measured)
    except OSError:
        print("another test_all run holds " + str(tmp / "lw-test-all.lock") + ": wait for it, or use another TMPDIR", file=sys.stderr)
        return 3
    sha = head_sha(ROOT)                                  # what this run tests and is judged against: fixed at the start (b11/b12 read both at the end)
    baseline = {k: v for k, v in load_baseline().items() if not a.only or (k.startswith("server/") == (a.only == "server"))}
    procs = {}
    t0 = time.time()
    shelf_before = shelf_snapshot(os.environ) if "client" in run and os.environ.get("LAMPWAY_SHELF_DIR") else None
    for name, (cmd, cwd, _) in run.items():
        procs[name] = subprocess.Popen(cmd, cwd=cwd, stdout=open(out / f"{name}.log", "w"), stderr=subprocess.STDOUT, start_new_session=True, env=suite_env)
    failing, passing, report, suite_errors = set(), set(), {}, []
    for name, p in procs.items():
        rc = p.wait()
        log = (out / f"{name}.log").read_text(errors="replace")
        ids, counts = parse(log, run[name][2])
        failing |= ids
        passing |= parse_passed(log, run[name][2])
        report[name] = {"rc": rc, **counts}
        if rc not in (0, 1) or (rc == 1 and not ids):
            suite_errors.append(f"{name}: pytest exited {rc}")
    writes = shelf_writes(shelf_before, shelf_snapshot(os.environ)) if shelf_before is not None else []
    j = judge(failing, baseline, passing)
    flaky = []
    if j["new"]:                                    # a new failure is re-run once, alone: one that passes then is reported as flaky, never hidden
        for name, (cmd, cwd, prefix) in run.items():
            mine = [t[len(prefix):] for t in j["new"] if t.startswith(prefix) and (prefix or not t.startswith("server/"))]
            if not mine:
                continue
            base_cmd = [c for c in cmd if not c.startswith("--basetemp") and c != str(tmp / f"lw-test-{name}") and c != "tests"]     # only the failing ids, not the whole suite again
            rerun = subprocess.run(base_cmd + ["--basetemp", str(tmp / f"lw-test-{name}-rerun"), *mine],
                                   cwd=cwd, capture_output=True, text=True, env=suite_env)
            (out / f"{name}-rerun.log").write_text(rerun.stdout + rerun.stderr)
            retry_log = rerun.stdout + rerun.stderr
            still, _ = parse(retry_log, prefix)
            retry_passed = parse_passed(retry_log, prefix)
            if rerun.returncode == 0:
                flaky += [prefix + t for t in mine if prefix + t in retry_passed and prefix + t not in still]
        j["new"] = [t for t in j["new"] if t not in flaky]
    if a.shrink_baseline and j["fixed"]:
        keep = [l for l in BASELINE.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("#") or not l.strip() or l.split("\t")[0] not in set(j["fixed"])]
        BASELINE.write_text("".join(keep), encoding="utf-8")
    green = not j["new"] and not j["known"] and (not j["fixed"] or a.shrink_baseline) and not j["unverified"] and not writes and not suite_errors
    summary = {"verdict": ("GREEN" if gate[0] in ("gated", "n/a") else "GREEN-UNGATED") if green else "RED", "binary": {"state": gate[0], "detail": gate[1]}, "sha": sha,
               "suites": report, "baseline": len(baseline), "known_red_seen": len(j["known"]), "new_failures": j["new"], "flaky_passed_on_rerun": flaky, "baseline_now_passing": j["fixed"],
               "baseline_unverified": j["unverified"], "suite_errors": suite_errors,
               "minutes": round((time.time() - t0) / 60, 1), "logs": str(out)}
    if writes:
        summary["shelf_writes"] = writes[:50]             # the shelf is read only: a run that changed it is RED, whatever passed
    end = head_sha(ROOT)
    if end != sha:
        summary["head_at_end"] = end                    # a commit landed during the run: the run tested the tree at "sha", not this
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0 if green and gate[0] in ("gated", "n/a") else (5 if green else 1)      # 5: green, but on a binary that is not this batch's: not a gate


if __name__ == "__main__":
    sys.exit(main())
