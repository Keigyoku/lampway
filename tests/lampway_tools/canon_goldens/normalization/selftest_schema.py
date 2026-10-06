#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Self-test of canonical-asset.schema.json against canonical-asset.examples.json.

Every 'valid' example must validate and every 'invalid' one must fail. A 'patch' is deep-merged into its base example (a null value
removes the key), so each invalid case differs from a valid document in exactly the field it names. Needs the jsonschema package.

    python3 selftest_schema.py          # prints one line per case, exits 1 on any mismatch
"""
import copy
import json
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def main():
    schema = json.loads((HERE / "canonical-asset.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema)
    ex = json.loads((HERE / "canonical-asset.examples.json").read_text())
    docs, bad = [], 0
    for i, case in enumerate(ex["valid"]):
        doc = case["doc"] if "doc" in case else merge(docs[0], case["patch"])
        docs.append(doc)
        errs = sorted(e.message for e in v.iter_errors(doc))
        ok = not errs
        bad += not ok
        print(f"valid   {'PASS' if ok else 'FAIL'}  {case['name']}" + ("" if ok else f"  -> {errs[:2]}"))
    for case in ex["invalid"]:
        doc = merge(docs[case["base"]], case["patch"])
        errs = list(v.iter_errors(doc))
        ok = bool(errs)
        bad += not ok
        print(f"invalid {'PASS' if ok else 'FAIL'}  {case['name']} ({case['why']})" + (f"  -> {errs[0].message[:90]}" if errs else "  -> accepted"))
    print(f"schema {schema['$id']}: {len(ex['valid'])} valid, {len(ex['invalid'])} invalid cases, {bad} mismatches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
