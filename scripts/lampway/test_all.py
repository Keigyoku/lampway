#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""THE full test run of the repository: the server suite and the whole client suite (every pytest.ini testpath: tests/, tests/lampway,
tests/lampway_tools on the real binary, the module test folders), held to the known-red baseline ``tests/known_red.tsv``.

    scripts/lampway/test_all.sh                    # both suites, in parallel; exit 0 only when green against the baseline
    scripts/lampway/test_all.sh --only server      # one suite
    scripts/lampway/test_all.sh --shrink-baseline  # also drop baseline lines whose test now passes (the list never grows here)

Green means: no failure or error that is not in the baseline, and no baseline entry that now passes (the list only shrinks: remove it).
Environment: LAMPWAY_BIN (the real binary; without one the tool tests SKIP, which the summary counts), LAMPWAY_TEST_PYTHON (default: this
interpreter), TMPDIR (the run's temp root), LAMPWAY_TEST_OUT (logs; default $TMPDIR/lampway-test-all)."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests" / "known_red.tsv"
ID = re.compile(r"^(FAILED|ERROR) (\S+)")
COUNT = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed)")


def load_baseline(path=BASELINE) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            tid, cls, reason = (line.split("\t") + ["", ""])[:3]
            out[tid] = (cls, reason)
    return out


def parse(log: str, prefix: str = "") -> tuple:
    ids, counts = set(), {}
    for line in log.splitlines():
        m = ID.match(line)
        if m and ("::" in m.group(2) or m.group(2).endswith(".py")):
            ids.add(prefix + m.group(2))
    tail = [l for l in log.splitlines() if re.search(r"\d+ (passed|failed)", l) and " in " in l]
    if tail:
        for n, what in COUNT.findall(tail[-1]):
            counts[what.rstrip("s") if what.startswith("error") else what] = int(n)
    return ids, counts


def judge(failing: set, baseline: dict) -> dict:
    return {"new": sorted(failing - set(baseline)), "fixed": sorted(set(baseline) - failing), "known": sorted(failing & set(baseline))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=("server", "client"))
    ap.add_argument("--shrink-baseline", action="store_true")
    a = ap.parse_args(argv)
    py = os.environ.get("LAMPWAY_TEST_PYTHON") or sys.executable
    tmp = Path(os.environ.get("TMPDIR") or "/tmp").resolve()
    out = Path(os.environ.get("LAMPWAY_TEST_OUT") or tmp / "lampway-test-all")
    out.mkdir(parents=True, exist_ok=True)
    # the server's pyproject already adds -q (a second -q hides the summary line the counts are read from)
    suites = {"server": ([py, "-m", "pytest", "tests", "-p", "no:cacheprovider", "-W", "ignore", "--tb=short", "--basetemp", str(tmp / "lw-test-server")], ROOT / "server", "server/"),
              "client": ([py, "-m", "pytest", "-p", "no:cacheprovider", "--continue-on-collection-errors", "-q", "-W", "ignore", "--tb=short", "--basetemp", str(tmp / "lw-test-client")], ROOT, "")}
    run = {k: v for k, v in suites.items() if not a.only or k == a.only}
    procs = {}
    t0 = time.time()
    for name, (cmd, cwd, _) in run.items():
        procs[name] = subprocess.Popen(cmd, cwd=cwd, stdout=open(out / f"{name}.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    failing, report = set(), {}
    for name, p in procs.items():
        rc = p.wait()
        ids, counts = parse((out / f"{name}.log").read_text(errors="replace"), run[name][2])
        failing |= ids
        report[name] = {"rc": rc, **counts}
    baseline = {k: v for k, v in load_baseline().items() if not a.only or (k.startswith("server/") == (a.only == "server"))}
    j = judge(failing, baseline)
    flaky = []
    if j["new"]:                                    # a new failure is re-run once, alone: one that passes then is reported as flaky, never hidden
        for name, (cmd, cwd, prefix) in run.items():
            mine = [t[len(prefix):] for t in j["new"] if t.startswith(prefix) and (prefix or not t.startswith("server/"))]
            if not mine:
                continue
            rerun = subprocess.run([c for c in cmd if not c.startswith("--basetemp") and c != str(tmp / f"lw-test-{name}")] + ["--basetemp", str(tmp / f"lw-test-{name}-rerun"), *mine],
                                   cwd=cwd, capture_output=True, text=True)
            (out / f"{name}-rerun.log").write_text(rerun.stdout + rerun.stderr)
            still, _ = parse(rerun.stdout, prefix)
            flaky += [prefix + t for t in mine if prefix + t not in still]
        j["new"] = [t for t in j["new"] if t not in flaky]
    if a.shrink_baseline and j["fixed"]:
        keep = [l for l in BASELINE.read_text(encoding="utf-8").splitlines(keepends=True) if l.startswith("#") or not l.strip() or l.split("\t")[0] not in set(j["fixed"])]
        BASELINE.write_text("".join(keep), encoding="utf-8")
    green = not j["new"] and (not j["fixed"] or a.shrink_baseline)
    summary = {"verdict": "GREEN" if green else "RED", "sha": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
               "suites": report, "baseline": len(baseline), "known_red_seen": len(j["known"]), "new_failures": j["new"], "flaky_passed_on_rerun": flaky, "baseline_now_passing": j["fixed"],
               "minutes": round((time.time() - t0) / 60, 1), "logs": str(out)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
