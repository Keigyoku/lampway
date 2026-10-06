#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the canon from rotting: run its three self-tests and prove the committed goldens are exactly what the generators write.

    python3 docs/canon/check_canon.py              # the check (CI: .github/workflows/canon.yml); exit 1 on any failure
    python3 docs/canon/check_canon.py --self-test  # plant a hand-edited golden in a scratch copy and prove the check refuses it

Legs, each a line `<leg>: PASS|FAIL <detail>`:
  goldens       goldens/selftest.py      (C01-C14: expected values reproduced by reference.py; every falsifier fails)
  rig-goldens   goldens/rig_selftest.py  (R01-R07, the same with rig_reference.py)
  schema        normalization/selftest_schema.py (needs jsonschema)
Dependencies: docs/canon/requirements.txt (numpy, jsonschema): python3 -m pip install -r docs/canon/requirements.txt
  determinism   gen_goldens.py + gen_rig_goldens.py into a scratch directory, byte-compared with every committed case file
Needs numpy and jsonschema. Scratch space comes from tempfile (honours TMPDIR); nothing in the tree is written."""
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDENS = HERE / "goldens"


def run(script: Path, *args) -> tuple:
    r = subprocess.run([sys.executable, str(script), *map(str, args)], cwd=script.parent, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    tail = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else "")


def regenerate(out: Path) -> tuple:
    for gen in ("gen_goldens.py", "gen_rig_goldens.py"):
        ok, tail = run(GOLDENS / gen, out)
        if not ok:
            return False, f"{gen} failed: {tail}"
    return True, ""


def drift(committed: Path, generated: Path) -> list:
    """Every case file that differs, or exists on one side only (a case the generator no longer writes is drift too)."""
    out = []
    cases = sorted({p.name for p in generated.iterdir() if p.is_dir()} | {p.name for p in committed.iterdir() if p.is_dir() and p.name[:1] in "CR" and p.name[1:3].isdigit()})
    for case in cases:
        a, b = committed / case, generated / case
        if not a.is_dir() or not b.is_dir():
            out.append(f"{case}: only {'generated' if b.is_dir() else 'committed'}")
            continue
        names = sorted({p.name for p in a.iterdir()} | {p.name for p in b.iterdir()})
        out += [f"{case}/{n}" for n in names if not ((a / n).is_file() and (b / n).is_file() and filecmp.cmp(a / n, b / n, shallow=False))]
    return out


def check(goldens: Path = GOLDENS) -> list:
    rows = []
    for leg, script in (("goldens", goldens / "selftest.py"), ("rig-goldens", goldens / "rig_selftest.py"),
                        ("schema", HERE / "normalization" / "selftest_schema.py")):
        ok, tail = run(script, *([goldens] if leg != "schema" else []))
        rows.append((leg, ok, tail))
    with tempfile.TemporaryDirectory(prefix="canon-goldens-") as tmp:
        ok, why = regenerate(Path(tmp))
        bad = drift(goldens, Path(tmp)) if ok else [why]
        rows.append(("determinism", not bad, f"{len(bad)} differing: {', '.join(bad[:5])}" if bad else "every committed case file is byte-identical to a fresh run"))
    return rows


def self_test() -> int:
    """The check is an assertion only if it can fail: hand-edit one committed golden in a scratch copy and require two legs to refuse it."""
    with tempfile.TemporaryDirectory(prefix="canon-plant-") as tmp:
        copy = Path(tmp) / "goldens"
        shutil.copytree(GOLDENS, copy, ignore=shutil.ignore_patterns("__pycache__"))
        target = copy / "C02_inverse_lbs" / "expected.json"
        target.write_text(target.read_text().replace("0", "1", 1))
        rows = {leg: ok for leg, ok, _ in check(copy)}
    caught = rows["determinism"] is False and rows["goldens"] is False
    print(f"self-test: {'ok' if caught else 'FAIL'} (a hand-edited C02 expected.json: determinism {'refused' if not rows['determinism'] else 'MISSED'}, "
          f"goldens {'refused' if not rows['goldens'] else 'MISSED'})")
    return 0 if caught else 1


def main(argv) -> int:
    if "--self-test" in argv:
        return self_test()
    rows = check()
    for leg, ok, detail in rows:
        print(f"{leg}: {'PASS' if ok else 'FAIL'} {detail}")
    verdict = all(ok for _, ok, _ in rows)
    print(f"canon: {'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
