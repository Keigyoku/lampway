# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/axi_common.py, sha256 713bb6f6870f), on 2026-10-06. The recipes' stdout and parser policy.
"""Small stdout/parser policy shared by knowledge tools (stdlib only)."""
import argparse
import json
from pathlib import Path
import sys


def emit(value, as_json=False):
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return
    # This boundary uses the flat scalar/primitive-array subset of TOON.
    for key, item in value.items():
        if isinstance(item, list) and all(not isinstance(x, (dict, list)) for x in item):
            print(f'{key}[{len(item)}]: ' + ','.join(json.dumps(x, ensure_ascii=False) for x in item))
        elif isinstance(item, (dict, list)):
            print(f'{key}: ' + json.dumps(json.dumps(item, ensure_ascii=False), ensure_ascii=False))
        else:
            print(f'{key}: ' + json.dumps(item, ensure_ascii=False))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        emit({'error': message, 'help': [self.format_usage().strip(),
              self.prog + ' --help for valid flags and examples']})
        raise SystemExit(2)


def publish(path, raw):
    """No-clobber immutable file publication, including symlink refusal."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlink output refused: ' + str(path))
    if path.exists():
        if path.read_bytes() == raw:
            return False
        raise ValueError('different-existing output refused: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(raw)
    return True
