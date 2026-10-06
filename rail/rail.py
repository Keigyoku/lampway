#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway's DOE x DOX rail: check the AGENTS.md tree and the canonical skills, regenerate the harness registrations, and hold
the anneal rule over history. AXI output: `key: value` lines and tables on stdout, errors on stdout with next steps; exit 0 clean,
1 findings or failure, 2 a usage error.

    python3 rail/rail.py                     # status: what the rail holds, and the next commands
    python3 rail/rail.py check               # the gate: inventory + registrations + the anneal rule over every commit since adoption
    python3 rail/rail.py check --quick       # the pre-push form: only the commits no remote holds yet; no worktree, no generated docs
    python3 rail/rail.py sync                # regenerate .agents/skills and .claude/skills from rail/skills
    python3 rail/rail.py selftest            # plant one violation per finding code in a scratch repo and prove each is caught
    python3 rail/rail.py closeout --tag T    # the root rail's DOX closeout row for a planned tag
    python3 rail/rail.py codes               # every finding code and what it means
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import railcore as R  # noqa: E402

VERBS = {
    "status": "what the rail holds (default)",
    "check": "the gate: exit 1 on any finding",
    "sync": "regenerate the harness registrations from rail/skills",
    "selftest": "prove every finding code fires on a planted violation",
    "closeout": "read the DOX closeout row for --tag",
    "codes": "list the finding codes",
    "help": "this usage",
}
HELP = ["python3 rail/rail.py check", "python3 rail/rail.py sync", "python3 rail/rail.py selftest", "python3 rail/rail.py closeout --tag <tag>"]


def _value(v):
    s = json.dumps(v) if not isinstance(v, str) else v
    return s if s and not any(c in s for c in ",:\n") else json.dumps(s)


def emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for key, value in result.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            fields = []
            for row in value:
                fields += [k for k in row if k not in fields]
            print(f"{key}[{len(value)}]{{{','.join(fields)}}}:")
            for row in value:
                print("  " + ",".join(_value(row.get(f, "")) for f in fields))
        elif isinstance(value, list):
            print(f"{key}[{len(value)}]:" + ("" if value else " (none)"))
            for item in value:
                print(f"  {item}")
        else:
            print(f"{key}: {value}")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if args == ["--version"]:
        print(f"rail {R.VERSION}")
        return 0
    repo, tag, verb, quick = Path.cwd(), None, "status", False
    try:
        if args and not args[0].startswith("-"):
            verb = args.pop(0)
        if verb not in VERBS:
            raise ValueError(f"unknown verb {verb!r}")
        while args:
            key = args.pop(0)
            if key == "--repo" and args:
                repo = Path(args.pop(0))
            elif key == "--tag" and args:
                tag = args.pop(0)
            elif key == "--quick":
                quick = True
            elif key == "--help":
                verb = "help"
            else:
                raise ValueError(f"unknown or incomplete flag {key!r}")
        repo = Path(R.git(repo, "rev-parse", "--show-toplevel").decode().strip())
    except (ValueError, R.GitError) as exc:
        emit({"error": str(exc), "help": HELP}, as_json)
        return 2
    try:
        if verb == "help":
            emit({"verbs": [f"{k}: {v}" for k, v in VERBS.items()], "flags": ["--repo <dir>", "--tag <tag>", "--quick", "--json", "--version"], "help": HELP}, as_json)
            return 0
        if verb == "codes":
            emit({"codes": [{"code": c, "means": m} for c, m in R.CODES.items()]}, as_json)
            return 0
        if verb == "sync":
            result = R.sync(repo)
            emit({**result, "help": ["python3 rail/rail.py check"]}, as_json)
            return 1 if result.get("refused") else 0
        if verb == "selftest":
            import selftest
            result = selftest.run()
            emit(result, as_json)
            return 0 if result["verdict"] == "PASS" else 1
        if verb == "closeout":
            emit(R.closeout(repo, tag), as_json)
            return 0
        result = R.check(repo, quick=quick and verb == "check")
        if verb == "status":
            result = {"skills": result["skills"], "rails": result["rails"], "baseline": result["baseline"], "commits_judged": result["commits"],
                      "findings": len(result["findings"]), "exempted": len(result["exempted"]), "help": HELP}
            emit(result, as_json)
            return 0
        result["help"] = (["python3 rail/rail.py sync   # RAIL-001/002", "python3 rail/rail.py codes  # what each code means",
                           "docs/rail.md: the rule and how to repair each finding"] if result["findings"] else ["python3 rail/rail.py selftest"])
        emit(result, as_json)
        return 1 if result["findings"] else 0
    except (ValueError, OSError, R.GitError) as exc:
        emit({"error": str(exc), "help": HELP}, as_json)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
